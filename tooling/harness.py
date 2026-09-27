#!/usr/bin/env python3
"""Minimal agent harness: vLLM tool-calling loop + Docker sandbox execution.

Usage: harness.py <run_name> <task_file> [--max-iters N] [--model NAME] [--port P]
"""
import argparse, json, os, subprocess, sys, time, hashlib, uuid
from datetime import datetime, timezone
from pathlib import Path
import urllib.request, urllib.error
from urllib.parse import urlparse

SANDBOX = "bench-sandbox-run"  # default; overridden per-run in main() so parallel runs can coexist
IMAGE = "bench-sandbox:latest"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def prepare_log_dir(log_dir, run_name):
    """Create a clean run directory without ever appending to prior evidence.

    Complete cells fail closed. Incomplete/nonterminal attempts are atomically
    moved under ``logs/_invalid`` before the same canonical run name is retried.
    """
    log_dir = Path(log_dir)
    if not log_dir.exists():
        log_dir.mkdir(parents=True)
        return None

    entries = list(log_dir.iterdir())
    if not entries:
        return None

    if ((log_dir / "summary.json").exists()
            and (log_dir / "workspace_final.tar.gz").exists()):
        raise RuntimeError(
            f"refusing to overwrite completed benchmark evidence: {log_dir}"
        )

    invalid_root = log_dir.parent / "_invalid"
    invalid_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = invalid_root / f"{run_name}_retry-{stamp}-{uuid.uuid4().hex[:8]}"
    log_dir.rename(archive)
    log_dir.mkdir(parents=True)
    print(f"ARCHIVED_INCOMPLETE_LOG_DIR: {archive}")
    return archive


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def docker_inspect(name, fmt=None):
    cmd = ["docker", "inspect", name]
    if fmt:
        cmd = ["docker", "inspect", "--format", fmt, name]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def _redact_argv(argv):
    """Return process arguments without accidentally persisting credentials."""
    redacted = []
    hide_next = False
    secret_flags = {"--api-key", "--api-key-file", "--token", "--auth-token"}
    for arg in argv:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        lowered = arg.lower()
        if lowered in secret_flags:
            redacted.append(arg)
            hide_next = True
        elif any(lowered.startswith(f"{flag}=") for flag in secret_flags):
            redacted.append(arg.split("=", 1)[0] + "=<redacted>")
        else:
            redacted.append(arg)
    return redacted


def _host_server_processes(api_url):
    """Capture host-native llama-server provenance for the request endpoint."""
    port = urlparse(api_url).port
    processes = []
    proc_root = Path("/proc")
    if not proc_root.exists():
        return processes
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
            argv = [part.decode("utf-8", "replace") for part in argv if part]
        except (OSError, PermissionError):
            continue
        if not argv or not any("llama-server" in part for part in argv):
            continue
        port_matches = any(
            arg == str(port) and i > 0 and argv[i - 1] in ("--port", "-p")
            for i, arg in enumerate(argv)
        ) or any(arg == f"--port={port}" for arg in argv)
        if not port_matches:
            continue
        exe_path = None
        exe_sha256 = None
        try:
            exe_path = str((entry / "exe").resolve(strict=True))
            exe_sha256 = file_sha256(exe_path)
        except (OSError, PermissionError):
            pass
        processes.append({
            "pid": int(entry.name),
            "exe": exe_path,
            "exe_sha256": exe_sha256,
            "argv": _redact_argv(argv),
        })
    return processes


def _endpoint_models(api_url):
    models_url = api_url.rsplit("/chat/completions", 1)[0] + "/models"
    try:
        with urllib.request.urlopen(models_url, timeout=10) as response:
            return {
                "url": models_url,
                "http_status": response.status,
                "payload": json.loads(response.read().decode("utf-8")),
            }
    except Exception as exc:
        return {"url": models_url, "error": f"{type(exc).__name__}: {exc}"}


def _manifest_lane_provenance(manifest_payload, api_url):
    """Resolve a coordinator endpoint port to its remote inference lane.

    External-engine campaigns commonly expose remote llama.cpp servers through
    Tower2-local SSH tunnels.  In that topology local process and nvidia-smi
    inspection describe the coordinator, not the inference node.  Accept either
    a top-level ``lanes`` list or ``topology.lanes`` and copy the matching lane
    into every run receipt so host attribution remains explicit and auditable.
    """
    port = urlparse(api_url).port
    result = {"coordinator_port": port, "matched": False, "lane": None}
    if not isinstance(manifest_payload, dict):
        return result
    topology = manifest_payload.get("topology")
    lane_sets = [manifest_payload.get("lanes")]
    if isinstance(topology, dict):
        lane_sets.insert(0, topology.get("lanes"))
    port_fields = ("coordinator_port", "local_port", "tunnel_local_port", "port")
    for lanes in lane_sets:
        if not isinstance(lanes, list):
            continue
        for lane in lanes:
            if not isinstance(lane, dict):
                continue
            candidate = next((lane.get(key) for key in port_fields if lane.get(key) is not None), None)
            try:
                matches = int(candidate) == int(port)
            except (TypeError, ValueError):
                matches = False
            if matches:
                result.update(matched=True, lane=lane)
                return result
    return result


def record_environment(run_name, model, api_url, task_file, log_dir, *,
                       sandbox_runtime=None, temperature=0.0, stuck_threshold=30,
                       max_iters=10000, reasoning_effort=None, enable_thinking=None,
                       max_model_len=262144, max_output_tokens_cap=180000,
                       top_p=None, top_k=None, min_p=None, presence_penalty=None,
                       repeat_penalty=None, seed=42, preserve_thinking=None,
                       reasoning_effort_location="chat_template_kwargs",
                       serving_manifest=None):
    """Capture everything needed to reproduce the run. Written before the loop starts.

    sandbox_runtime: dict of per-run sandbox flags (gh_token_set, docker_socket,
    gpus, input_mount). The token value itself is never recorded — only whether
    one was set.

    temperature, top_p, top_k, stuck_threshold, max_iters: actual loop config — receipt fields
    reflect these exact values (used to be hardcoded constants). Default values
    here match the historical hardcoded ones for back-compat with prior receipts."""
    receipt = {
        "schema_version": 1,
        "run_name": run_name,
        "captured_at": now_iso(),
        "host": {
            "hostname": subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip(),
            "kernel": subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip(),
            "os": subprocess.run(["lsb_release", "-d"], capture_output=True, text=True).stdout.strip() or "unknown",
        },
        "harness": {
            "path": str(Path(__file__).resolve()),
            "git_sha": subprocess.run(
                ["git", "-C", str(Path(__file__).resolve().parent.parent), "rev-parse", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip() or None,
            "git_dirty": bool(subprocess.run(
                ["git", "-C", str(Path(__file__).resolve().parent.parent), "status", "--porcelain"],
                capture_output=True, text=True,
            ).stdout.strip()),
            "file_sha256": file_sha256(__file__),
        },
        "task": {
            "path": str(Path(task_file).resolve()),
            "sha256": file_sha256(task_file),
            "byte_size": os.path.getsize(task_file),
        },
        "vllm": {
            "served_model_name": model,
            "api_url": api_url,
        },
        "sandbox": {
            "image": IMAGE,
        },
    }

    # The benchmark may use a host-native systemd service rather than a Docker
    # inference container. Record the immutable deployment manifest, live model
    # identity, and exact host process/binary serving this endpoint.
    receipt["serving"] = {
        "manifest": None,
        "endpoint_models": _endpoint_models(api_url),
        "host_processes": _host_server_processes(api_url),
        "host_processes_scope": "coordinator",
        "inference_lane": _manifest_lane_provenance(None, api_url),
    }
    if serving_manifest:
        manifest_path = Path(serving_manifest).resolve()
        manifest = {
            "path": str(manifest_path),
            "sha256": file_sha256(manifest_path),
            "byte_size": manifest_path.stat().st_size,
        }
        try:
            manifest["payload"] = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            manifest["read_error"] = f"{type(exc).__name__}: {exc}"
        receipt["serving"]["manifest"] = manifest
        receipt["serving"]["inference_lane"] = _manifest_lane_provenance(
            manifest.get("payload"), api_url
        )

    # Best-effort: identify running vLLM containers either by the historical
    # ``vllm-*`` naming convention or by the exact served model name in the
    # container name/arguments.  Production deployments often use host
    # networking and a model-specific name, so filtering only on ``vllm-*``
    # silently produced empty provenance receipts for those deployments.
    p = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    receipt["vllm"]["containers"] = []
    for cname in p.stdout.split():
        raw_info = docker_inspect(cname)
        if not raw_info:
            continue
        try:
            info = json.loads(raw_info)[0]
        except (json.JSONDecodeError, IndexError, TypeError):
            continue

        args = info.get("Args") or []
        cmd = (info.get("Config") or {}).get("Cmd") or []
        runtime_identity = json.dumps([args, cmd], ensure_ascii=False).lower()
        normalized_name = "".join(ch for ch in cname.lower() if ch.isalnum())
        normalized_model = "".join(ch for ch in model.lower() if ch.isalnum())
        if not (
            cname.lower().startswith("vllm-")
            or normalized_name == normalized_model
            or model.lower() in runtime_identity
        ):
            continue

        image_ref = info.get("Image")
        image_name = (info.get("Config") or {}).get("Image")
        cid = info.get("Id")
        started_at = (info.get("State") or {}).get("StartedAt")
        host_config = info.get("HostConfig") or {}
        mounts = [
            {
                "type": mount.get("Type"),
                "source": mount.get("Source"),
                "destination": mount.get("Destination"),
                "mode": mount.get("Mode"),
                "rw": mount.get("RW"),
            }
            for mount in (info.get("Mounts") or [])
        ]
        model_mount = next(
            (mount for mount in mounts if mount.get("destination") == "/model"),
            None,
        )
        model_revision = None
        if model_mount and model_mount.get("source"):
            revision_file = (
                Path(model_mount["source"])
                / ".cache/huggingface/download/config.json.metadata"
            )
            try:
                model_revision = revision_file.read_text().splitlines()[0].strip()
            except (OSError, IndexError):
                pass

        # Resolve image digest
        image_digest = docker_inspect(
            image_name or image_ref, fmt='{{index .RepoDigests 0}}'
        ) or "unknown"
        receipt["vllm"]["containers"].append({
            "name": cname,
            "image_name": image_name,
            "image_ref": image_ref,
            "image_digest": image_digest,
            "container_id": cid,
            "started_at": started_at,
            "args": args,
            "cmd": cmd,
            "network_mode": host_config.get("NetworkMode"),
            "port_bindings": host_config.get("PortBindings") or {},
            "mounts": mounts,
            "model_revision": model_revision,
        })

    # Sandbox image digest
    sandbox_img_id = docker_inspect(IMAGE, fmt='{{.Id}}')
    receipt["sandbox"]["image_id"] = sandbox_img_id
    if sandbox_runtime is not None:
        receipt["sandbox"]["runtime"] = sandbox_runtime

    # nvidia-smi snapshot
    nvs = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,driver_version,power.limit,power.draw,temperature.gpu,memory.used,memory.total,clocks.current.graphics",
         "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    receipt["hardware"] = {
        "scope": "coordinator_host_snapshot",
        "nvidia_smi": nvs.stdout.strip().splitlines(),
    }

    # Inference request defaults (the constants used in the loop body)
    receipt["inference_request_defaults"] = {
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "min_p": min_p,
        "presence_penalty": presence_penalty,
        "repeat_penalty": repeat_penalty,
        "seed": seed,
        "max_tokens_strategy": (
            f"min({max_output_tokens_cap}, max(2048, max_model_len - "
            "max(last_prompt_tokens + 12000, 8000) - 2048))"
        ),
        "prompt_growth_reserve_tokens": 12000,
        "minimum_estimated_prompt_tokens": 8000,
        "context_safety_tokens": 2048,
        "minimum_request_max_tokens": 2048,
        "max_model_len": max_model_len,
        "max_output_tokens_cap": max_output_tokens_cap,
        "stream": False,
        "tool_choice": "auto",
        "tools": [t["function"]["name"] for t in TOOLS],
        "reasoning_effort": reasoning_effort,
        "reasoning_effort_location": reasoning_effort_location,
        "enable_thinking": enable_thinking,
        "preserve_thinking": preserve_thinking,
    }

    receipt["harness_loop_config"] = {
        "stuck_threshold_iters": stuck_threshold,
        "max_iters": max_iters,
        "max_completion_total_default": 10**12,
    }

    out = Path(log_dir) / "receipt.json"
    out.write_text(json.dumps(receipt, indent=2))
    return receipt


WORKSPACE_HASH_COMMAND = (
    "find /workspace "
    "\\( -path '*/.git/objects' -o -path '*/__pycache__' "
    "-o -path '*/.pytest_cache' \\) -prune -o "
    "-type f ! -name '*.pyc' ! -name '*.pyo' "
    "! -name '.coverage' ! -name '.coverage.*' -print0 2>/dev/null "
    "| sort -z | xargs -0 -r sha1sum 2>/dev/null "
    "| sha1sum | awk '{print $1}'"
)


def workspace_state_hash():
    """Hash meaningful workspace state while ignoring test-runtime churn.

    Python bytecode, pytest's cache, and coverage databases are execution
    byproducts rather than model-authored progress.  Including them lets an
    otherwise read-only pytest loop reset the no-progress detector forever.
    Git metadata other than object storage and all ordinary source/artifact
    files remain covered, so edits, deletes, untracked deliverables, refs, and
    commits still advance the state hash.
    """
    p = subprocess.run(["docker", "exec", SANDBOX, "bash", "-c", WORKSPACE_HASH_COMMAND],
                       capture_output=True, text=True, timeout=30)
    return p.stdout.strip()


_EXEC_SESSION_CLEANUP = r"""
import glob
import os
import signal
import sys
import time

target_sid = int(sys.argv[1])


def session_id(pid):
    try:
        stat = open(f"/proc/{pid}/stat", encoding="utf-8").read()
        # Fields after the final ')' begin with state, ppid, pgrp, session.
        return int(stat[stat.rfind(")") + 2:].split()[3])
    except (FileNotFoundError, PermissionError, IndexError, ValueError):
        return None


def members():
    own_pid = os.getpid()
    found = []
    for path in glob.glob("/proc/[0-9]*/stat"):
        pid = int(path.split("/")[2])
        if pid != own_pid and session_id(pid) == target_sid:
            found.append(pid)
    return found


terminated = members()
for pid in terminated:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(0.5)
survivors = members()
for pid in survivors:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
print(f"session={target_sid} term={len(terminated)} kill={len(survivors)}")
"""


def cleanup_exec_session(session_id):
    """Kill processes left in one timed-out ``docker exec`` session."""
    if session_id is None:
        return "session id unavailable; descendant cleanup could not run"
    try:
        p = subprocess.run(
            ["docker", "exec", SANDBOX, "python3", "-c", _EXEC_SESSION_CLEANUP,
             str(session_id)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"session cleanup failed: {exc}"
    detail = (p.stdout or p.stderr).strip()
    if p.returncode != 0:
        return f"session cleanup rc={p.returncode}: {detail}"
    return f"session cleanup: {detail}"


def extract_exec_session(stderr, marker):
    """Remove the private SID marker from stderr and return ``(sid, text)``."""
    sid = None
    kept = []
    for line in stderr.splitlines():
        if line.startswith(marker):
            try:
                sid = int(line[len(marker):].strip())
            except ValueError:
                kept.append(line)
        else:
            kept.append(line)
    return sid, "\n".join(kept)


def docker_exec(cmd, workdir="/workspace", timeout=300):
    """Run a command in the sandbox. Returns dict with stdout/stderr/rc/duration.

    Pipes the command via stdin (`bash -s`) instead of `bash -c "..."` so we
    don't hit Linux's ~128KB argv limit on long heredocs. Hit this when a
    model emitted a 680-token python heredoc as a single bash call.

    The timeout must live *inside* the container. A host-only
    ``subprocess.run(..., timeout=N)`` kills the ``docker exec`` client but
    leaves its in-container shell and descendants running. Those orphans can
    contaminate later tool timings. Nested GNU ``timeout`` calls create their
    own process groups, so killing only the outer command is insufficient. We
    therefore record the Docker exec session ID and, only when the outer guard
    fires, terminate every remaining process in that session. The slightly
    longer host timeout remains a Docker-runtime failsafe.
    """
    t0 = time.time()
    timeout = max(1, int(timeout))
    marker = f"__MMBT_EXEC_SID_{uuid.uuid4().hex}__="
    probe = (
        f'import os,sys; print("{marker}" + str(os.getsid(0)), file=sys.stderr)'
    )
    wrapper = (
        f"python3 -c {json.dumps(probe)}; "
        f"exec timeout --signal=TERM --kill-after=5s {timeout}s bash -s"
    )
    full = [
        "docker", "exec", "-i", "-w", workdir, SANDBOX,
        "bash", "-c", wrapper,
    ]
    try:
        # Capture as bytes; decode with errors='replace' so binary outputs (e.g. curl-piping
        # gzipped content) don't raise UnicodeDecodeError. Hit this on a Coder-Next run where
        # a bash command piped \x1f\x8b… into stdout.
        p = subprocess.run(
            full,
            input=cmd.encode("utf-8"),
            capture_output=True,
            timeout=timeout + 15,
        )
        out = p.stdout.decode("utf-8", errors="replace")
        err = p.stderr.decode("utf-8", errors="replace")
        session_id, err = extract_exec_session(err, marker)
        if p.returncode == 124:
            timeout_note = f"timeout after {timeout}s"
            cleanup_note = cleanup_exec_session(session_id)
            err = f"{err.rstrip()}\n{timeout_note}\n{cleanup_note}".strip()
            return {
                "rc": -1,
                "stdout": out[-20000:],
                "stderr": err[-5000:],
                "duration_s": round(time.time() - t0, 2),
                "truncated_stdout": len(out) > 20000,
            }
        return {
            "rc": p.returncode,
            "stdout": out[-20000:],
            "stderr": err[-5000:],
            "duration_s": round(time.time() - t0, 2),
            "truncated_stdout": len(out) > 20000,
        }
    except subprocess.TimeoutExpired as exc:
        raw_err = exc.stderr or b""
        if isinstance(raw_err, bytes):
            raw_err = raw_err.decode("utf-8", errors="replace")
        session_id, raw_err = extract_exec_session(raw_err, marker)
        cleanup_note = cleanup_exec_session(session_id)
        return {
            "rc": -1,
            "stdout": "",
            "stderr": (
                f"outer docker-exec failsafe fired after {timeout + 15}s; "
                f"the in-container timeout did not return\n{raw_err.rstrip()}\n"
                f"{cleanup_note}"
            ),
            "duration_s": round(time.time() - t0, 2),
        }


# ----- Tools available to the agent --------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a bash command inside the sandbox container. Use this for shell, git, curl, python, file ops — anything you'd do at a terminal. CWD is /workspace by default. Output is truncated to last 20KB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash command to execute."},
                    "workdir": {"type": "string", "description": "Working directory. Default /workspace.", "default": "/workspace"},
                    "timeout_s": {"type": "integer", "description": "Timeout in seconds. Default 300.", "default": 300},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text content to a file at the given path inside the sandbox. Creates parent directories. Overwrites if exists. Use for any file > a few lines, or anything where heredoc escaping in bash would be painful.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path (relative to /workspace)."},
                    "content": {"type": "string", "description": "File content."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the sandbox. Returns up to 200KB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that the task is complete. Provide a short summary of what was accomplished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
    },
]


def validate_done(require_files, require_git_tag):
    """Check workspace state against done() preconditions. Returns None if all
    requirements met, or a human-readable string listing what's missing.

    File requirements are matched as bare filenames against `find /workspace
    -maxdepth 2 -name <name>` so the agent's choice of audit-repo location
    (e.g. /workspace/ vs /workspace/audit-repo/ vs /workspace/audit-pr-1057/)
    doesn't matter. The git check accepts only a clean candidate repository
    whose HEAD has an annotated tag, so a pre-existing tag in an input clone
    cannot satisfy the completion gate."""
    missing = []
    for fname in (require_files or []):
        # Strip leading slashes so we always match by basename pattern; the
        # agent's audit-repo could be at any depth-1 subdir.
        bare = fname.lstrip("/")
        r = docker_exec(f"find /workspace -maxdepth 3 -name {bare!r} -type f -print -quit", timeout=15)
        if not r['stdout'].strip():
            missing.append(fname)
    if require_git_tag:
        # Find a clean git repo under /workspace with an annotated tag at HEAD.
        # /workspace itself, /workspace/*/, and /workspace/*/*/ — covers nested
        # audit repos like /workspace/dreamserver-audit/.
        cmd = (
            "for d in /workspace /workspace/*/ /workspace/*/*/; do "
            "  [ -d \"$d/.git\" ] || continue; "
            "  git -C \"$d\" diff --quiet 2>/dev/null || continue; "
            "  git -C \"$d\" diff --cached --quiet 2>/dev/null || continue; "
            "  [ -z \"$(git -C \"$d\" ls-files --others --exclude-standard 2>/dev/null)\" ] || continue; "
            "  for t in $(git -C \"$d\" tag --points-at HEAD 2>/dev/null); do "
            "    [ \"$(git -C \"$d\" cat-file -t \"refs/tags/$t\" 2>/dev/null)\" = tag ] "
            "      && echo TAG_FOUND && break 2; "
            "  done; "
            "done"
        )
        r = docker_exec(cmd, timeout=15)
        if "TAG_FOUND" not in r['stdout']:
            missing.append("(no clean workspace repo with an annotated tag at HEAD)")
    if missing:
        return (
            "DONE_REJECTED: Required artifacts missing — task spec demands these before completion: "
            + ", ".join(missing)
            + ". Continue working — produce these (or update existing files to match the requirements) before calling done() again."
        )
    return None


def execute_tool(name, args, log_dir, require_files=None, require_git_tag=False):
    # Tool schemas declare these fields required, but a model can still emit a
    # syntactically valid call that omits one. That must become an observable
    # tool error the model can repair, never a harness exception that destroys
    # the benchmark attempt.
    if not isinstance(args, dict):
        return f"TOOL_ERROR: {name} arguments must be a JSON object"
    required = {
        "bash": ("command",),
        "write_file": ("path", "content"),
        "read_file": ("path",),
    }
    missing = [key for key in required.get(name, ()) if key not in args]
    if missing:
        return f"TOOL_ERROR: {name} missing required argument(s): {', '.join(missing)}"

    if name == "bash":
        cmd = args["command"]
        if not isinstance(cmd, str) or not cmd:
            return "TOOL_ERROR: bash argument 'command' must be a non-empty string"
        workdir = args.get("workdir") or "/workspace"
        if not isinstance(workdir, str):
            return "TOOL_ERROR: bash argument 'workdir' must be a string"
        try:
            timeout = int(args.get("timeout_s") or 300)
        except (TypeError, ValueError):
            return "TOOL_ERROR: bash argument 'timeout_s' must be a positive integer"
        if timeout <= 0:
            return "TOOL_ERROR: bash argument 'timeout_s' must be a positive integer"
        r = docker_exec(cmd, workdir=workdir, timeout=timeout)
        body = f"rc={r['rc']}  duration={r['duration_s']}s\n--- stdout ---\n{r['stdout']}"
        if r['stderr']:
            body += f"\n--- stderr ---\n{r['stderr']}"
        if r.get('truncated_stdout'):
            body += "\n[stdout truncated]"
        return body
    elif name == "write_file":
        path = args["path"]
        content = args["content"]
        if not isinstance(path, str) or not path:
            return "TOOL_ERROR: write_file argument 'path' must be a non-empty string"
        if not isinstance(content, str):
            return "TOOL_ERROR: write_file argument 'content' must be a string"
        if not path.startswith("/"):
            path = "/workspace/" + path
        # Stage via tempfile on host, docker cp into sandbox (handles binary/special chars cleanly)
        tmp = Path(log_dir) / f".write_{uuid.uuid4().hex}.tmp"
        tmp.write_text(content, encoding="utf-8")
        # Ensure parent dir exists in sandbox
        parent = os.path.dirname(path) or "/workspace"
        docker_exec(f"mkdir -p {parent!r}", timeout=10)
        cp = subprocess.run(["docker", "cp", str(tmp), f"{SANDBOX}:{path}"], capture_output=True, text=True)
        tmp.unlink(missing_ok=True)
        if cp.returncode != 0:
            return f"ERROR copying file: {cp.stderr}"
        size = len(content.encode())
        return f"wrote {size} bytes to {path}"
    elif name == "read_file":
        path = args["path"]
        if not isinstance(path, str) or not path:
            return "TOOL_ERROR: read_file argument 'path' must be a non-empty string"
        if not path.startswith("/"):
            path = "/workspace/" + path
        r = docker_exec(f"head -c 200000 {path!r}", timeout=10)
        if r["rc"] != 0:
            return f"ERROR: {r['stderr']}"
        return r["stdout"]
    elif name == "done":
        # If strict-done flags are set, validate workspace state before
        # accepting. Validation failure returns a tool-error the model sees;
        # the run continues so the model can complete the missing artifacts.
        if require_files or require_git_tag:
            err = validate_done(require_files, require_git_tag)
            if err is not None:
                return err
        return "DONE_SIGNAL:" + (args.get("summary") or "")
    else:
        return f"unknown tool {name!r}"


# ----- Agent loop --------------------------------------------------------

def build_chat_payload(model, messages, max_tokens, *, temperature=0.0,
                       top_p=None, top_k=None, min_p=None,
                       presence_penalty=None, repeat_penalty=None, seed=42,
                       reasoning_effort=None,
                       reasoning_effort_location="chat_template_kwargs",
                       enable_thinking=None, preserve_thinking=None):
    """Build one OpenAI-compatible request with explicit model-card controls."""
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": temperature,
        "seed": seed,
        "max_tokens": max_tokens,
        "stream": False,
    }
    optional_sampling = {
        "top_p": top_p,
        "top_k": top_k,
        "min_p": min_p,
        "presence_penalty": presence_penalty,
        # llama.cpp's OpenAI-compatible server names this repeat_penalty.
        "repeat_penalty": repeat_penalty,
    }
    payload.update({key: value for key, value in optional_sampling.items() if value is not None})

    ctk = {}
    if reasoning_effort:
        if reasoning_effort_location == "top_level":
            payload["reasoning_effort"] = reasoning_effort
        elif reasoning_effort_location == "chat_template_kwargs":
            ctk["reasoning_effort"] = reasoning_effort
        else:
            raise ValueError(f"unsupported reasoning_effort_location: {reasoning_effort_location}")
    if enable_thinking is not None:
        ctk["enable_thinking"] = enable_thinking
    if preserve_thinking is not None:
        ctk["preserve_thinking"] = preserve_thinking
    if ctk:
        payload["chat_template_kwargs"] = ctk
    return payload


def agent_loop(api_url, model, system_prompt, task, log_dir, max_iters=10000,
               max_completion_total=10**12, max_model_len=262144,
               stuck_threshold=30, temperature=0.0, top_p=None, top_k=None,
               min_p=None, presence_penalty=None, repeat_penalty=None, seed=42,
               require_files=None, require_git_tag=False, reasoning_effort=None,
               reasoning_effort_location="chat_template_kwargs",
               enable_thinking=None, preserve_thinking=None,
               max_output_tokens_cap=180000):
    """Run the agent until done() or limits hit. Returns final state dict."""
    log_path = Path(log_dir) / "transcript.jsonl"
    summary_path = Path(log_dir) / "summary.json"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": task})

    iter_count = 0
    total_completion_tokens = 0
    total_prompt_tokens = 0
    started = time.time()
    done_summary = None
    finish_reason = None
    last_prompt_tokens = 0
    last_workspace_hash = workspace_state_hash()
    iters_since_progress = 0

    while iter_count < max_iters:
        iter_count += 1
        # Dynamic max_tokens: leave room for the next prompt to actually fit.
        # Estimate growth: prior prompt + ~12K for the new tool result/system overhead.
        estimated_prompt = max(last_prompt_tokens + 12000, 8000)
        safety = 2048
        max_tokens_safe = max(2048, max_model_len - estimated_prompt - safety)
        max_tokens_safe = min(max_tokens_safe, max_output_tokens_cap)
        payload = build_chat_payload(
            model, messages, max_tokens_safe,
            temperature=temperature, top_p=top_p, top_k=top_k,
            min_p=min_p, presence_penalty=presence_penalty,
            repeat_penalty=repeat_penalty, seed=seed,
            reasoning_effort=reasoning_effort,
            reasoning_effort_location=reasoning_effort_location,
            enable_thinking=enable_thinking,
            preserve_thinking=preserve_thinking,
        )
        body = json.dumps(payload).encode()
        req = urllib.request.Request(api_url, data=body, headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=3600) as r:
                resp = json.loads(r.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            err_body = ""
            if isinstance(e, urllib.error.HTTPError):
                try: err_body = e.read().decode()[:500]
                except: pass
            with open(log_path, "a") as f:
                f.write(json.dumps({"t": now_iso(), "iter": iter_count, "type": "error", "error": str(e), "body": err_body}) + "\n")
            finish_reason = f"api_error: {e}"
            break
        wall = time.time() - t0
        msg = resp["choices"][0]["message"]
        usage = resp.get("usage", {})
        total_completion_tokens += usage.get("completion_tokens", 0)
        total_prompt_tokens += usage.get("prompt_tokens", 0)
        last_prompt_tokens = usage.get("prompt_tokens", last_prompt_tokens)

        # Log the model turn
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "t": now_iso(), "iter": iter_count, "type": "model",
                "wall_s": round(wall, 2),
                "completion_tokens": usage.get("completion_tokens", 0),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "tok_ps": round(usage.get("completion_tokens", 0) / max(wall, 0.01), 1),
                "content_len": len(msg.get("content") or ""),
                "tool_calls": [{"name": tc["function"]["name"], "args_len": len(tc["function"]["arguments"])} for tc in (msg.get("tool_calls") or [])],
                "finish_reason": resp["choices"][0].get("finish_reason"),
            }) + "\n")

        # If the model hit max_tokens mid-output, its tool_calls JSON arguments may be truncated.
        # Forwarding a malformed assistant message will get rejected by vLLM on the next call.
        # Detect by both finish_reason="length" AND completion_tokens at/near the cap — vLLM
        # sometimes returns finish_reason="tool_calls" when the model emits a tool call AND
        # hits the cap on the same turn (the cap-hit isn't reflected in finish_reason).
        ctok = usage.get("completion_tokens", 0)
        hit_cap = ctok >= max_tokens_safe - 100
        if resp["choices"][0].get("finish_reason") == "length" or hit_cap:
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "t": now_iso(), "iter": iter_count, "type": "abort",
                    "reason": "model hit max_tokens cap mid-emission; assistant message likely contains truncated tool-call JSON",
                    "completion_tokens": ctok,
                    "max_tokens_safe": max_tokens_safe,
                    "finish_reason": resp["choices"][0].get("finish_reason"),
                    "detected_via": "length" if resp["choices"][0].get("finish_reason") == "length" else "ctok_at_cap",
                }) + "\n")
            finish_reason = f"model_exceeded_max_tokens_{max_tokens_safe}"
            break

        # Append assistant message to history (preserve tool_calls so the model sees its own tool intents).
        # Interleaved-thinking models (e.g. MiniMax-M2, served with --reasoning-parser minimax_m2) split
        # the <think> block out into a separate reasoning_content field. The MiniMax card REQUIRES
        # retaining it across turns: "Do not remove the <think>...</think> part, otherwise the model's
        # performance will be negatively affected" (their numbers: -36% tau2, -40% BrowseComp when prior
        # thinking is stripped — state drift + weakened self-correction on long-horizon toolchains, which
        # is exactly a clean agentic run that derails on a final turn). Pass reasoning_content back so the
        # template re-renders the prior thinking. No-op for models that don't emit the field.
        assistant_msg = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("reasoning_content"):
            assistant_msg["reasoning_content"] = msg["reasoning_content"]
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # No tool call — model has finished or is just talking
            content = msg.get("content") or ""
            print(f"[iter {iter_count}] no tool call, content_len={len(content)}, finish={resp['choices'][0].get('finish_reason')}")
            if resp["choices"][0].get("finish_reason") == "stop":
                # Model believes it's done. Treat as soft-done.
                done_summary = content[:1000] if content else "(model stopped without explicit done())"
                finish_reason = "model_stopped"
                break
            # If finish_reason is "length" or other, stop too
            finish_reason = resp["choices"][0].get("finish_reason") or "no_action"
            break

        # Execute each tool call, append result
        soft_done = False
        for tc in tool_calls:
            tc_name = tc["function"]["name"]
            try:
                tc_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError as e:
                tc_args = {}
                result = f"ERROR parsing tool args: {e}\nraw: {tc['function']['arguments'][:500]}"
            else:
                t1 = time.time()
                result = execute_tool(tc_name, tc_args, log_dir,
                                       require_files=require_files,
                                       require_git_tag=require_git_tag)
                tool_wall = time.time() - t1
                with open(log_path, "a") as f:
                    f.write(json.dumps({
                        "t": now_iso(), "iter": iter_count, "type": "tool",
                        "name": tc_name, "args": tc_args if len(json.dumps(tc_args)) < 50000 else {"_truncated_at_bytes": len(json.dumps(tc_args))},
                        "wall_s": round(tool_wall, 2),
                        "result_len": len(result),
                    }) + "\n")
                if result.startswith("DONE_SIGNAL:"):
                    done_summary = result[len("DONE_SIGNAL:"):]
                    soft_done = True

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result if not result.startswith("DONE_SIGNAL:") else "task marked done",
            })

        # Stuck detector: workspace state hash unchanged for N iters → kill
        cur_hash = workspace_state_hash()
        if cur_hash == last_workspace_hash:
            iters_since_progress += 1
        else:
            iters_since_progress = 0
            last_workspace_hash = cur_hash

        print(f"[iter {iter_count}] {len(tool_calls)} tool call(s)  wall={wall:.1f}s  ctok={usage.get('completion_tokens',0)}  ptok={last_prompt_tokens}  total_ctok={total_completion_tokens}  no-progress={iters_since_progress}/{stuck_threshold}  max_tok_req={max_tokens_safe}")

        if soft_done:
            finish_reason = "done_signal"
            break
        if total_completion_tokens >= max_completion_total:
            finish_reason = "completion_token_cap"
            break
        if iters_since_progress >= stuck_threshold:
            finish_reason = f"stuck_no_workspace_change_for_{stuck_threshold}_iters"
            break

    elapsed = time.time() - started
    summary = {
        "started_at": datetime.fromtimestamp(started, tz=timezone.utc).isoformat(),
        "ended_at": now_iso(),
        "elapsed_s": round(elapsed, 1),
        "iterations": iter_count,
        "total_completion_tokens": total_completion_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "model": model,
        "finish_reason": finish_reason,
        "done_summary": done_summary,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name")
    ap.add_argument("task_file")
    ap.add_argument("--max-iters", type=int, default=10000)
    ap.add_argument("--model", default="qwen3-coder-next-awq")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "high", "xhigh"],
                    help="For models whose chat template reads a `reasoning_effort` variable "
                         "(e.g. StepFun Step-3.7-Flash, which has low/medium/high reasoning levels). "
                         "Sent at the configured wire location on every request and recorded in the "
                         "receipt. Leave unset for models that don't expose reasoning levels.")
    ap.add_argument("--reasoning-effort-location", default="chat_template_kwargs",
                    choices=["chat_template_kwargs", "top_level"],
                    help="Wire location for reasoning_effort. Historical Step campaigns use "
                         "chat_template_kwargs; Qwen3.8 requires the OpenAI top-level field.")
    ap.add_argument("--thinking", default=None, choices=["on", "off"],
                    help="For models whose chat template reads an `enable_thinking` variable "
                         "(e.g. Qwen3.5-397B-A17B, whose template auto-opens a <think> block). "
                         "'on'/'off' -> enable_thinking true/false sent as chat_template_kwargs on "
                         "every request and recorded in the receipt. Leave unset for other models.")
    ap.add_argument("--preserve-thinking", default=None, choices=["on", "off"],
                    help="Explicit preserve_thinking chat-template control. Qwen3.8 defaults to on; "
                         "passing it explicitly makes the agent-history contract reproducible.")
    ap.add_argument("--max-model-len", type=int, default=262144,
                    help="The endpoint's context window, used to size each request's max_tokens "
                         "(max_tokens = min(output cap, remaining estimated context)). Default 262144 "
                         "matches the vLLM models benched so far. Set to the served --ctx-size for "
                         "models hosted with a smaller window (e.g. 131072 for the 397B GGUF on llama.cpp) "
                         "so requests don't exceed the context and 400.")
    ap.add_argument("--max-output-tokens-cap", type=int, default=180000,
                    help="Hard cap for each request's max_tokens. Default 180000 matches the "
                         "current PR-audit and microbench harness. Use 64000 to reproduce the "
                         "historical investment-memo/board harness operating point.")
    ap.add_argument("--serving-manifest", default=None,
                    help="Path to the immutable deployment manifest for the live inference "
                         "endpoint. Its path, hash, size, and JSON payload are captured in receipt.json.")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="Sampling temperature sent on every request. Default 0.0 (deterministic). "
                         "At temp=0 with seed=42, models can fall into fixed-point loops on long-horizon "
                         "tasks (same context → same response → same tool result → same response). "
                         "0.3-0.5 is typical for agentic work and breaks these traps without much off-task drift.")
    ap.add_argument("--top-p", type=float, default=None,
                    help="Nucleus sampling top_p, sent only when set. Pair with --temperature/--top-k to "
                         "match a model's specified operating point (e.g. MiniMax-M2: temp=1.0 top_p=0.95 "
                         "top_k=40). Leave unset to use the server default.")
    ap.add_argument("--top-k", type=int, default=None,
                    help="Top-k sampling, sent only when set (vLLM extension). See --top-p.")
    ap.add_argument("--min-p", type=float, default=None,
                    help="Minimum-probability sampling threshold, sent only when set.")
    ap.add_argument("--presence-penalty", type=float, default=None,
                    help="OpenAI-compatible presence penalty, sent only when set.")
    ap.add_argument("--repeat-penalty", type=float, default=None,
                    help="llama.cpp repeat_penalty value, sent only when set.")
    ap.add_argument("--seed", type=int, default=42,
                    help="Deterministic request seed. Default 42 preserves the historical protocol.")
    ap.add_argument("--stuck-threshold", type=int, default=30,
                    help="Iterations of unchanged workspace state hash before the harness aborts the run. "
                         "Default 30 was tuned on the memo/board/code tasks (whole job fits in ~100 iters, "
                         "so 30 is a strong loop signal). Long-horizon tasks like the DreamServer PR audit "
                         "do legitimate read-only recon (ls/cat/git log) that doesn't update the workspace "
                         "hash — bump to 80-150 to give those runs room before the detector fires. "
                         "Genuine loops still die within (threshold × ~1.5s) of starting, so a higher "
                         "threshold is cheap insurance.")
    ap.add_argument("--require-files", default=None,
                    help="Comma-separated bare filenames the agent must produce before done() is accepted. "
                         "E.g. 'verdict.md,summary.md,review.md'. Each name is matched via "
                         "`find /workspace -maxdepth 3 -name <name> -type f` so the agent's choice of "
                         "audit-repo location doesn't matter. If any required file is missing when the model "
                         "calls done(), the call is rejected with a tool-error message naming the gap, and "
                         "the loop continues (the model can produce the missing file and retry). Used for "
                         "harness-equivalence ablations to test whether 'no-ship' failures are model issues "
                         "or scaffold issues.")
    ap.add_argument("--require-git-tag", action="store_true",
                    help="If set, done() is rejected unless at least one annotated git tag exists in some "
                         "git repo under /workspace (depth ≤ 2). Pairs with --require-files for full "
                         "spec-compliance enforcement.")
    ap.add_argument("--system", default=None, help="Path to system prompt file (optional).")
    ap.add_argument("--input-mount", default=None,
                    help="Host path mounted read-only at /input/repo inside the sandbox. "
                         "Useful for tasks that consume a prior agent's output (e.g. presentation built from memo repo).")
    ap.add_argument("--gh-token", default=None,
                    help="GitHub token to expose as GH_TOKEN+GITHUB_TOKEN inside the sandbox. "
                         "Pass a literal token, '@env' to read $GH_TOKEN/$GITHUB_TOKEN, "
                         "or '@gh' to call `gh auth token` on the host. "
                         "The token value is never written to receipt.json.")
    ap.add_argument("--docker-socket", action="store_true",
                    help="Bind-mount /var/run/docker.sock into the sandbox so the agent can "
                         "run sibling containers (e.g. for installer-in-a-clean-container tests). "
                         "Note: this gives the sandbox root-equivalent access to the host docker daemon.")
    ap.add_argument("--gpus", default=None,
                    help="Pass-through to `docker run --gpus`. Example: 'all', 'device=0', "
                         "'\"device=0,1\"'. Required for PRs the agent needs to test on real GPUs. "
                         "Beware: the sandbox shares GPUs with the vLLM container hosting the model.")
    args = ap.parse_args()
    enable_thinking = None if args.thinking is None else (args.thinking == "on")
    preserve_thinking = None if args.preserve_thinking is None else (args.preserve_thinking == "on")

    # Resolve --gh-token. Done early so we fail fast if @env/@gh produce nothing.
    gh_token = args.gh_token
    if gh_token == "@env":
        gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not gh_token:
            raise SystemExit("--gh-token @env: neither GH_TOKEN nor GITHUB_TOKEN set in caller env")
    elif gh_token == "@gh":
        p = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if p.returncode != 0 or not p.stdout.strip():
            raise SystemExit(f"--gh-token @gh: `gh auth token` failed ({p.stderr.strip() or 'no output'}); run `gh auth login` first")
        gh_token = p.stdout.strip()

    # Per-run sandbox name so multiple harness invocations don't collide on the same container.
    global SANDBOX
    SANDBOX = f"bench-sandbox-{args.run_name}"

    # Published benchmark artifacts live at the repository root.  Keep mutable
    # workspaces under tooling/, but write logs where the runner, graders,
    # autopilot, and reproduction docs all expect them: <repo>/logs/.
    HARNESS_DIR = Path(__file__).resolve().parent
    log_dir = HARNESS_DIR.parent / "logs" / args.run_name
    prepare_log_dir(log_dir, args.run_name)
    workspace_host = HARNESS_DIR / "workspace" / args.run_name
    if workspace_host.exists():
        subprocess.run(["rm", "-rf", str(workspace_host)], check=True)
    workspace_host.mkdir(parents=True, exist_ok=True)

    # Stop any prior sandbox, start a fresh one with the workspace mounted
    subprocess.run(["docker", "rm", "-f", SANDBOX], capture_output=True)
    docker_run = [
        # Docker's tiny init must be PID 1 so descendants killed by an
        # in-container tool timeout are reaped instead of accumulating as
        # zombies under ``sleep infinity`` during long campaigns.
        "docker", "run", "-d", "--init", "--name", SANDBOX,
        "-v", f"{workspace_host}:/workspace",
    ]
    if gh_token:
        docker_run += ["-e", f"GH_TOKEN={gh_token}", "-e", f"GITHUB_TOKEN={gh_token}"]
    if args.docker_socket:
        docker_run += ["-v", "/var/run/docker.sock:/var/run/docker.sock"]
    if args.gpus:
        docker_run += ["--gpus", args.gpus]
    if args.input_mount:
        input_src = Path(args.input_mount).resolve()
        if not input_src.exists():
            raise SystemExit(f"--input-mount path does not exist: {input_src}")
        # Copy to a per-run temp dir so we can rename _starter_git_history → .git
        # without mutating the source. (We track inputs in the outer repo with .git
        # renamed to avoid nested-repo issues; the agent expects a real .git on its
        # mount.)
        input_mount = HARNESS_DIR / "workspace" / f"_input_{args.run_name}"
        if input_mount.exists():
            subprocess.run(["sudo", "rm", "-rf", str(input_mount)], check=False)
            subprocess.run(["rm", "-rf", str(input_mount)], check=False)
        subprocess.run(["cp", "-r", str(input_src), str(input_mount)], check=True)
        # Restore .git from the renamed history dir if present
        for hidden_name in ("_starter_git_history", "_agent_git_history"):
            hidden = input_mount / hidden_name
            if hidden.is_dir():
                target = input_mount / ".git"
                if target.exists():
                    subprocess.run(["rm", "-rf", str(target)], check=False)
                hidden.rename(target)
                print(f"input mount: restored {hidden_name} → .git")
                break
        docker_run += ["-v", f"{input_mount}:/input/repo:ro"]
        print(f"input mount: {input_src} → /input/repo (read-only via {input_mount})")
    docker_run += ["--network", "bridge", IMAGE]
    subprocess.run(docker_run, check=True, capture_output=True)
    # Init git inside the sandbox; pre-allow safe.directory so agent doesn't have to
    docker_exec(
        "git config --global --add safe.directory '*' && "
        "git init -q && git commit --allow-empty -m 'initial empty repo' -q || true",
        timeout=20,
    )

    task = Path(args.task_file).read_text()
    system_prompt = Path(args.system).read_text() if args.system else None

    api_url = f"http://127.0.0.1:{args.port}/v1/chat/completions"
    print(f"=== Run {args.run_name} | model={args.model} | url={api_url} ===")
    print(f"workspace: {workspace_host}")
    print(f"logs: {log_dir}")

    require_files = [s.strip() for s in args.require_files.split(",")] if args.require_files else None

    receipt = record_environment(
        args.run_name, args.model, api_url, args.task_file, log_dir,
        sandbox_runtime={
            "docker_init": True,
            "gh_token_set": bool(gh_token),
            "docker_socket": bool(args.docker_socket),
            "gpus": args.gpus,
            "input_mount": args.input_mount,
            "require_files": require_files,
            "require_git_tag": bool(args.require_git_tag),
        },
        temperature=args.temperature,
        stuck_threshold=args.stuck_threshold,
        max_iters=args.max_iters,
        reasoning_effort=args.reasoning_effort,
        reasoning_effort_location=args.reasoning_effort_location,
        enable_thinking=enable_thinking,
        preserve_thinking=preserve_thinking,
        max_model_len=args.max_model_len,
        max_output_tokens_cap=args.max_output_tokens_cap,
        top_p=args.top_p,
        top_k=args.top_k,
        min_p=args.min_p,
        presence_penalty=args.presence_penalty,
        repeat_penalty=args.repeat_penalty,
        seed=args.seed,
        serving_manifest=args.serving_manifest,
    )
    print(f"receipt -> {log_dir / 'receipt.json'}  (vllm containers logged: {len(receipt['vllm']['containers'])})")

    summary = agent_loop(api_url, args.model, system_prompt, task, log_dir,
                         max_iters=args.max_iters, temperature=args.temperature,
                         top_p=args.top_p, top_k=args.top_k,
                         min_p=args.min_p, presence_penalty=args.presence_penalty,
                         repeat_penalty=args.repeat_penalty, seed=args.seed,
                         stuck_threshold=args.stuck_threshold,
                         require_files=require_files,
                         require_git_tag=bool(args.require_git_tag),
                         reasoning_effort=args.reasoning_effort,
                         reasoning_effort_location=args.reasoning_effort_location,
                         enable_thinking=enable_thinking,
                         preserve_thinking=preserve_thinking,
                         max_model_len=args.max_model_len,
                         max_output_tokens_cap=args.max_output_tokens_cap)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))

    # Snapshot the final workspace as a tarball for archival
    tarball = log_dir / "workspace_final.tar.gz"
    subprocess.run(["tar", "czf", str(tarball), "-C", str(workspace_host), "."], check=True)
    print(f"\nworkspace archived -> {tarball}")


if __name__ == "__main__":
    main()
