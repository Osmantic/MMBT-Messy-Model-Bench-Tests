#!/usr/bin/env python3
"""bench_autopilot_v2 — multi-model self-healing supervisor for the MMBT microbench.

Superset of bench_autopilot.py. Preserves ALL original behavior, CLI flags, and
status.json keys (additive-only). Layers on three additions:

  A) MODEL PRESETS (--preset NAME)
     A PRESETS dict selecting model/container/gguf/ctx/arms so the SAME tool can
     bench other models. "397b" reproduces DEFAULT_CONFIG exactly. Stub presets
     "step3p7" (vLLM — NotImplemented note, not llama.cpp) and "qwen3.6-27b".
     --preset composes with --target-n and --config (config still wins, additive).

  B) --publish
     On a COMPLETE run, generate a findings scorecard markdown (per-task pass/N
     for both arms + totals + deltas vs the N=10 no-think baseline) to
     /tmp/bench-autopilot/scorecard.md and `git add`+commit it to a branch named
     bench-results-<date-from-status> in ~/bench (NOT pushed). Idempotent; never
     crashes the run if git fails.

  C) ANOMALY ALERTS
     A Pushover priority-1 alert fires if >=3 consecutive freshly-graded cells
     verdict GRADER_FAILED / MISSING_OUTPUT — signalling a harness/grader break
     (distinct from model-quality fails).

This is a NEW filename so it can be swapped in for the next run without disturbing
a live one. The status.json schema is backward-compatible: only new keys/flags are
added. The original --target-n / --config / --max-passes / --once all behave as before.
"""
from __future__ import annotations
import argparse, json, os, signal, statistics, subprocess, sys, time
import re
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
# Derive the repository from this committed supervisor so a clean git worktree
# remains self-contained and receipts cannot silently come from another checkout.
BENCH = Path(__file__).resolve().parent.parent
LOGS = BENCH / "logs"
TOOLING = BENCH / "tooling"
SCRIPTS = TOOLING / "scripts"
STATE_DIR = Path("/tmp/bench-autopilot")
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATUS = STATE_DIR / "status.json"
LOG = STATE_DIR / "autopilot.log"
HEARTBEAT = STATE_DIR / "heartbeat.json"
SCORECARD = STATE_DIR / "scorecard.md"           # addition B
NOTIFY_SH = HOME / "dream-fleet-test" / "lib" / "notify.sh"
CLEANUP_IMAGE = "sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"

HEARTBEAT_FRESH_SECS = 120
SUBSTANCE_CHECK_SECS = 300
_last_substance_check: dict[str, float] = {}

TASKS = ["p1_bugfix","p1_testwrite","p1_refactor","p2_extract","p2_ci",
         "p2_hallucination","p2_triage","p3_doc","p3_business","p3_market",
         "p3_writing","p3_pm"]

# N=10 no-think per-task pass baseline (sums to 82/120) — the published Phase-A
# numbers, reused from the dashboard for the --publish scorecard deltas.
BASELINE_N10_NOTHINK = {
    "p1_bugfix": 10, "p1_testwrite": 0, "p1_refactor": 0,
    "p2_extract": 10, "p2_ci": 10, "p2_hallucination": 10, "p2_triage": 10,
    "p3_doc": 9, "p3_business": 10, "p3_market": 8, "p3_writing": 0, "p3_pm": 5,
}
BASELINE_N10_TOTAL_PASS = 82
BASELINE_N10_TOTAL_CELLS = 120
BASELINE_ARM_HINT = "nothink"

# addition C: verdicts that indicate a harness/grader break (not model quality).
HARNESS_BREAK_VERDICTS = ("GRADER_FAILED", "MISSING_OUTPUT")
ANOMALY_RUN_THRESHOLD = 3

DEFAULT_CONFIG = {
    "model": "qwen3.5-397b-a17b",
    "port": 8001,
    "max_model_len": 131072,
    "ctx_size": 131072,
    "gguf": "/models/unsloth-Qwen3.5-397B-A17B-GGUF/UD-Q3_K_XL/Qwen3.5-397B-A17B-UD-Q3_K_XL-00001-of-00005.gguf",
    "container": "llama-397b",
    "image": "ghcr.io/ggml-org/llama.cpp:server-cuda-b9014",
    "arms": [{"label": "397b-nothink", "thinking": "off"},
             {"label": "397b-think",   "thinking": "on"}],
    "stuck_secs": 1200,        # transcript frozen this long = truly hung (kill it)
    # A transcript is intentionally quiet while the harness waits for a bash
    # tool.  The harness owns that command's timeout and adds a 15 s Docker
    # cleanup guard, so the supervisor must not apply the shorter inference
    # watchdog to this phase.  3,900 s covers the documented 3,600 s ceiling
    # plus teardown/jitter while still bounding a genuinely wedged harness.
    "tool_stuck_secs": 3900,
    "endpoint_grace_secs": 180 # endpoint must load within this on (re)launch
}


# --- addition A: model presets ----------------------------------------------
# Each preset is a full config dict (same schema as DEFAULT_CONFIG). --preset
# selects one as the base; --config (if given) is still applied on top (additive
# override), so existing config-file workflows keep working. The "397b" preset is
# a byte-for-byte copy of DEFAULT_CONFIG so `--preset 397b` == legacy default.
#
# A preset may carry an "engine" key ("llamacpp" default, or "vllm"); engines
# other than llama.cpp are not yet wired into ensure_endpoint() — they raise a
# clear NotImplementedError rather than silently launching a wrong container.
PRESETS = {
    # Reproduces DEFAULT_CONFIG exactly (the current live 397b run config).
    "397b": dict(DEFAULT_CONFIG),

    # Stub: Stepfun Step-3.7 served by vLLM. vLLM's launch/probe differ from the
    # llama.cpp container (no -ngl/-sm/-fa flags, OpenAI server is native, GGUF →
    # HF weights dir). ensure_endpoint() refuses to launch this until a vLLM path
    # is implemented. Filled in here so the preset is discoverable + documented.
    "step3p7": {
        "engine": "vllm",
        "model": "step3p7",
        "port": 8002,
        "max_model_len": 65536,
        "ctx_size": 65536,
        "gguf": None,                      # vLLM loads an HF weights dir, not a GGUF
        "weights": "/models/stepfun-step3p7",   # placeholder weights path
        "container": "vllm-step3p7",
        "image": "vllm/vllm-openai:latest",     # placeholder image
        "arms": [{"label": "step3p7-nothink", "thinking": "off"},
                 {"label": "step3p7-think",   "thinking": "on"}],
        "stuck_secs": 1200,
        "endpoint_grace_secs": 600,        # vLLM cold-load is slower
        "_notimplemented": (
            "step3p7 is a vLLM model: launch + health-probe + arm flags differ "
            "from the llama.cpp container path in ensure_endpoint(). Wire a vLLM "
            "launcher (vllm serve / OpenAI server, --max-model-len, weights dir) "
            "before running this preset."),
    },

    # Stub: dense Qwen3.6-27B via the same llama.cpp container path as 397b — this
    # one IS runnable once its gguf path is confirmed on disk. Smaller ctx, single
    # arm-pair, its own container/port so it won't collide with a live 397b run.
    "qwen3.6-27b": {
        "engine": "llamacpp",
        "model": "qwen3.6-27b",
        "port": 8003,
        "max_model_len": 65536,
        "ctx_size": 65536,
        "gguf": "/models/Qwen3.6-27B-GGUF/Qwen3.6-27B-UD-Q4_K_XL.gguf",  # confirm on disk
        "container": "llama-qwen36-27b",
        "image": "ghcr.io/ggml-org/llama.cpp:server-cuda-b9014",
        "arms": [{"label": "qwen36-27b-nothink", "thinking": "off"},
                 {"label": "qwen36-27b-think",   "thinking": "on"}],
        "stuck_secs": 1200,
        "endpoint_grace_secs": 240,
    },
}


def log(msg: str):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)


def cleanup_pattern(parent: Path, pattern: str) -> None:
    """Remove root-owned benchmark scratch through a pinned, networkless helper."""
    allowed_parents = {Path("/tmp").resolve(), (TOOLING / "workspace").resolve()}
    resolved_parent = parent.resolve()
    if resolved_parent not in allowed_parents:
        raise RuntimeError(f"cleanup parent is not approved: {resolved_parent}")
    if not re.fullmatch(r"[A-Za-z0-9._*-]{1,160}", pattern) or "/" in pattern or ".." in pattern:
        raise RuntimeError("cleanup pattern is unsafe")
    result = sh([
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "-e", f"CLEANUP_PATTERN={pattern}",
        "-v", f"{resolved_parent}:/cleanup:rw",
        CLEANUP_IMAGE,
        "sh", "-c",
        'find /cleanup -mindepth 1 -maxdepth 1 -name "$CLEANUP_PATTERN" -exec rm -rf -- {} \\;',
    ])
    if result.returncode != 0:
        raise RuntimeError(f"root-owned scratch cleanup failed: {result.stderr.strip()[:300]}")


# --- pushover ---------------------------------------------------------------
def notify(title: str, msg: str, priority: int = 0):
    """Best-effort Pushover via the fleet notify.sh helper. Never raises."""
    try:
        if not NOTIFY_SH.exists():
            return
        cmd = f'source "{NOTIFY_SH}" && notify_push "$1" "$2" "$3"'
        subprocess.run(["bash", "-c", cmd, "_", title, msg, str(priority)],
                       capture_output=True, text=True, timeout=20)
    except Exception as e:
        log(f"notify failed (non-fatal): {e}")


# --- heartbeat / resume-safety ----------------------------------------------
def write_heartbeat():
    try:
        HEARTBEAT.write_text(json.dumps({
            "pid": os.getpid(),
            "ts": time.time(),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }))
    except Exception:
        pass


def fresh_heartbeat():
    """Return (age_secs, pid) if a foreign heartbeat is fresher than the threshold, else None."""
    try:
        hb = json.loads(HEARTBEAT.read_text())
    except Exception:
        return None
    pid = hb.get("pid")
    if pid == os.getpid():
        return None
    age = time.time() - float(hb.get("ts", 0))
    if age < HEARTBEAT_FRESH_SECS:
        return (age, pid)
    return None


def endpoint_up(port: int) -> bool:
    r = sh(f"curl -sf http://127.0.0.1:{port}/v1/models")
    return r.returncode == 0


def container_running(name: str) -> bool:
    if not name:
        return False
    r = sh(["docker", "ps", "--format", "{{.Names}}"])
    return name in r.stdout.split()


def configured_ports(cfg: dict) -> list[int]:
    ports = cfg.get("lane_ports") or [cfg["port"]]
    return list(dict.fromkeys(int(port) for port in ports))


def active_harnesses_by_port() -> dict[int, dict]:
    """Return exact live harness PID/run mappings for each endpoint lane."""
    active = {}
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            argv = [
                part.decode(errors="replace")
                for part in (proc_dir / "cmdline").read_bytes().split(b"\0")
                if part
            ]
            harness_index = next(
                index for index, arg in enumerate(argv)
                if Path(arg).name == "harness.py"
            )
            port_index = argv.index("--port")
            run_name = argv[harness_index + 1]
            port = int(argv[port_index + 1])
        except (OSError, StopIteration, ValueError, IndexError):
            continue
        active[port] = {"pid": int(proc_dir.name), "cell": run_name}
    return active


def slot_progress_signature(payload) -> tuple:
    """Extract active prompt/decode progress from llama.cpp's /slots payload."""
    if not isinstance(payload, list):
        return ()
    processing = []
    for slot in payload:
        if not isinstance(slot, dict) or not slot.get("is_processing"):
            continue
        next_token = slot.get("next_token") or []
        token_state = next_token[0] if next_token and isinstance(next_token[0], dict) else {}
        processing.append((
            slot.get("id"),
            slot.get("id_task"),
            slot.get("n_prompt_tokens_processed"),
            token_state.get("n_decoded"),
            token_state.get("n_remain"),
        ))
    return tuple(sorted(processing, key=lambda row: (str(row[0]), str(row[1]))))


def endpoint_slot_progress(port: int) -> tuple:
    result = sh(["curl", "-fsS", "--max-time", "5", f"http://127.0.0.1:{port}/slots"])
    if result.returncode != 0:
        return ()
    try:
        return slot_progress_signature(json.loads(result.stdout))
    except json.JSONDecodeError:
        return ()


def configured_services(cfg: dict) -> list[str]:
    return [str(service) for service in (cfg.get("services") or [])]


def service_running(name: str) -> bool:
    return sh(["systemctl", "--user", "is-active", "--quiet", name]).returncode == 0


def runtime_running(cfg: dict) -> bool:
    services = configured_services(cfg)
    if services:
        return all(service_running(service) for service in services)
    return container_running(cfg.get("container"))


def ensure_endpoint(cfg: dict) -> bool:
    engine = cfg.get("engine", "llamacpp")
    if engine == "external":
        ports = configured_ports(cfg)
        name = cfg.get("container") or ", ".join(configured_services(cfg)) or "external runtime"
        if all(endpoint_up(port) for port in ports):
            return True
        launcher = cfg.get("launcher")
        if not launcher:
            raise ValueError("external engine config requires a launcher")
        missing = [port for port in ports if not endpoint_up(port)]
        log(f"endpoint lane(s) {missing} down — invoking external launcher {launcher}")
        notify("bench: endpoint restart", f"{name} lane(s) {missing} down — invoking {launcher}", 0)
        launched = sh(["bash", launcher])
        if launched.returncode != 0:
            detail = (launched.stderr or launched.stdout).strip()[-800:]
            log(f"ERROR: external launcher failed rc={launched.returncode}: {detail}")
            notify("bench: endpoint FAILED", f"{name} launcher failed rc={launched.returncode}", 1)
            return False
        for _ in range(max(1, cfg["endpoint_grace_secs"] // 5)):
            if all(endpoint_up(port) for port in ports):
                log(f"all endpoint lanes back up: {ports}")
                return True
            if not runtime_running(cfg):
                log("ERROR: external inference runtime died during load")
                notify("bench: endpoint FAILED", f"{name} died during model load", 1)
                return False
            time.sleep(5)
        missing = [port for port in ports if not endpoint_up(port)]
        log(f"ERROR: external endpoint lane(s) {missing} did not come up within grace period")
        notify("bench: endpoint FAILED", f"{name} lane(s) {missing} did not load within grace period", 1)
        return False
    if engine != "llamacpp":
        note = cfg.get("_notimplemented", f"engine '{engine}' has no launcher")
        log(f"ERROR: ensure_endpoint not implemented for engine '{engine}': {note}")
        notify("bench: preset not runnable", note, 1)
        raise NotImplementedError(note)

    port, name = cfg["port"], cfg["container"]
    if endpoint_up(port):
        return True
    log(f"endpoint down — (re)launching {name}")
    notify("bench: endpoint restart", f"{name} down — relaunching on port {port}", 0)
    sh(["docker", "rm", "-f", name])
    sh(["docker", "run", "-d", "--name", name, "--gpus", "all", "--shm-size", "16g",
        "-v", f"{HOME}/models:/models:ro", "-p", f"127.0.0.1:{port}:8000",
        cfg["image"], "-m", cfg["gguf"], "-a", cfg["model"],
        "-ngl", "999", "-sm", "layer", "-fa", "on", "-c", str(cfg["ctx_size"]),
        "-b", "2048", "-np", "1", "--jinja", "--reasoning-format", "none",
        "--host", "0.0.0.0", "--port", "8000"])
    for _ in range(cfg["endpoint_grace_secs"] // 5):
        if endpoint_up(port):
            log("endpoint back up")
            return True
        if not container_running(name):
            log("ERROR: endpoint container died during load");
            log((sh(["docker","logs","--tail","15",name]).stdout or "")[-800:])
            notify("bench: endpoint FAILED", f"{name} died during model load", 1)
            return False
        time.sleep(5)
    log("ERROR: endpoint did not come up within grace period")
    notify("bench: endpoint FAILED", f"{name} did not load within grace period", 1)
    return False


def cell_done(run_name: str) -> bool:
    d = LOGS / run_name
    if (d / "summary.json").exists() and (d / "workspace_final.tar.gz").exists():
        return True
    # Operator-terminated pathology runs are terminal benchmark outcomes under
    # the published substance-monitoring protocol.  Their receipt, transcript,
    # and explicit label are the preserved evidence; they intentionally have no
    # final workspace archive because SIGTERM bypasses harness teardown.
    try:
        label = json.loads((d / "label.json").read_text())
        return (label.get("primary") in {"identical-call-loop", "stuck-in-research"}
                and (d / "receipt.json").exists()
                and (d / "transcript.jsonl").exists())
    except Exception:
        return False


def cell_verdict(run_name: str):
    g = LOGS / run_name / "grade.json"
    if not g.exists():
        return None
    try:
        v = json.loads(g.read_text()).get("verdict")
        return v
    except Exception:
        return "BAD_GRADE"


# --- per-cell timing + tok/s ------------------------------------------------
def cell_metrics(run_name: str):
    """Return (wall_s, tok_ps) for a completed cell, from summary.json (transcript fallback)."""
    d = LOGS / run_name
    wall = toks = None
    sp = d / "summary.json"
    if sp.exists():
        try:
            s = json.loads(sp.read_text())
            wall = s.get("elapsed_s")
            toks = s.get("total_completion_tokens")
        except Exception:
            pass
    if (wall is None or toks is None) and (d / "transcript.jsonl").exists():
        try:
            rows = [json.loads(l) for l in (d / "transcript.jsonl").read_text().splitlines() if l.strip()]
            ct = [r.get("completion_tokens") for r in rows if isinstance(r.get("completion_tokens"), (int, float))]
            if toks is None and ct:
                toks = sum(ct)
            ws = [r.get("wall_s") for r in rows if isinstance(r.get("wall_s"), (int, float))]
            if wall is None and ws:
                wall = sum(ws)
        except Exception:
            pass
    tok_ps = None
    if isinstance(wall, (int, float)) and wall > 0 and isinstance(toks, (int, float)):
        tok_ps = round(toks / wall, 2)
    return (wall if isinstance(wall, (int, float)) else None, tok_ps)


def arm_progress(label: str, target: int):
    """Return (done, total, per_task_counts, metrics) for an arm up to target N."""
    total = len(TASKS) * target
    done = 0
    pertask = {}
    walls = []
    tokps = []
    for t in TASKS:
        c = 0
        passes = 0
        for v in range(1, target + 1):
            rn = f"{t}_{label}_v{v}"
            if cell_done(rn):
                c += 1; done += 1
                if cell_verdict(rn) in ("PASS", "STRUCTURAL_PASS"):
                    passes += 1
                w, tp = cell_metrics(rn)
                if w is not None:
                    walls.append(w)
                if tp is not None:
                    tokps.append(tp)
        pertask[t] = {"done": c, "pass": passes}
    metrics = {
        "wall_median": round(statistics.median(walls), 1) if walls else None,
        "tok_ps_median": round(statistics.median(tokps), 2) if tokps else None,
        "n_timed": len(walls),
    }
    return done, total, pertask, metrics


def _arm_label_glob(cfg):
    """A glob fragment matching any arm label of the active preset.

    The original code hard-coded 'p*_397b-*_v*'. To stay general across presets we
    derive a shared prefix from the configured arm labels; for 397b this resolves
    to the same '397b-' fragment, so behavior is unchanged for the live run.
    """
    labels = [a["label"] for a in cfg["arms"]]
    if not labels:
        return "397b-"
    # longest common prefix of the arm labels (e.g. "397b-", "qwen36-27b-")
    s1, s2 = min(labels), max(labels)
    i = 0
    while i < len(s1) and i < len(s2) and s1[i] == s2[i]:
        i += 1
    return s1[:i] or labels[0]


def newest_transcript(cfg=None):
    arm_frag = _arm_label_glob(cfg) if cfg else "397b-"
    best = None; best_mt = 0
    for d in LOGS.glob(f"p*_{arm_frag}*_v*"):
        tp = d / "transcript.jsonl"
        if tp.exists():
            mt = tp.stat().st_mtime
            if mt > best_mt:
                best_mt = mt; best = tp
    return best, best_mt


def current_cell_info(cfg=None):
    tp, mt = newest_transcript(cfg)
    if not tp:
        return {"cell": None, "iter": None, "frozen_secs": None}
    it = None
    try:
        last = None
        for line in tp.read_text().splitlines():
            last = line
        if last:
            it = json.loads(last).get("iter")
    except Exception:
        pass
    return {"cell": tp.parent.name, "iter": it, "frozen_secs": int(time.time() - mt)}


def _last_transcript_row(transcript: Path):
    """Return the newest JSONL object without rereading a potentially huge log."""
    try:
        with transcript.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 65536))
            tail = handle.read().decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            if line.strip():
                row = json.loads(line)
                return row if isinstance(row, dict) else None
    except (OSError, json.JSONDecodeError):
        pass
    return None


def watchdog_stuck_policy(cfg: dict, transcript: Path):
    """Return ``(limit_seconds, phase)`` for the active harness phase.

    Model rows ending in ``tool_calls`` precede tool execution; the matching
    tool row is written only after that command exits.  During that interval
    neither transcript mtime nor inference-slot counters move.  Applying the
    normal 1,200 s inference watchdog there can therefore kill a valid command
    whose harness timeout is 1,800 or 3,600 s.
    """
    inference_limit = int(cfg["stuck_secs"])
    row = _last_transcript_row(transcript)
    if row and row.get("type") == "model" and row.get("finish_reason") == "tool_calls":
        tool_limit = int(cfg.get("tool_stuck_secs", 3900))
        return max(inference_limit, tool_limit), "pending-tool"
    return inference_limit, "inference-or-idle"


def kill_stuck(cell: str):
    """Kill a truly-hung cell's harness PID + sandbox so the chain advances."""
    log(f"STUCK: killing hung cell {cell}")
    r = sh(["pgrep", "-f", f"harness.py {cell} "])
    for pid in r.stdout.split():
        sh(["kill", "-TERM", pid])
    time.sleep(3)
    r = sh(["pgrep", "-f", f"harness.py {cell} "])
    for pid in r.stdout.split():
        sh(["kill", "-KILL", pid])
    sh(["docker", "rm", "-f", f"bench-sandbox-{cell}"])


def active_substance_targets(cfg) -> list[dict]:
    """Return every live lane's exact run/transcript/PID for substance checks."""
    targets = []
    active = active_harnesses_by_port()
    for port in configured_ports(cfg):
        harness = active.get(port)
        if not harness:
            continue
        transcript = LOGS / harness["cell"] / "transcript.jsonl"
        if transcript.exists():
            targets.append({
                "port": port,
                "cell": harness["cell"],
                "pid": harness["pid"],
                "transcript": transcript,
            })
    if targets:
        return targets
    # Preserve the historical single-lane fallback for non-Linux/dev contexts
    # where procfs attribution is unavailable.
    transcript, _ = newest_transcript(cfg)
    if transcript and transcript.exists():
        return [{
            "port": int(cfg["port"]),
            "cell": transcript.parent.name,
            "pid": None,
            "transcript": transcript,
        }]
    return []


def check_current_substance(cfg):
    """Run the published five-minute substance monitor on every active lane.

    Scroll loops are terminated by exact harness PID and receive the canonical
    explicit failure label.  Runaway-generation signals are logged for endpoint
    triage but are not killed, matching SUBSTANCE-MONITORING-WORKFLOW.md.
    """
    global _last_substance_check
    now = time.time()
    for target in active_substance_targets(cfg):
        cell = target["cell"]
        if now - _last_substance_check.get(cell, 0.0) < SUBSTANCE_CHECK_SECS:
            continue
        _last_substance_check[cell] = now
        transcript = target["transcript"]
        result = sh(["python3", str(SCRIPTS / "check_substance.py"), str(transcript)])
        with open(STATE_DIR / f"substance-{cell}.log", "a") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] rc={result.returncode}\n")
            f.write(result.stdout or "")
            f.write(result.stderr or "")
        if result.returncode == 1:
            pid = target["pid"]
            pids = [str(pid)] if pid is not None else \
                sh(["pgrep", "-f", f"harness.py {cell} "]).stdout.split()
            if not pids:
                log(f"SUBSTANCE: scroll-loop detected for {cell}, but exact harness PID was absent")
                continue
            log(f"SUBSTANCE: scroll-loop detected for {cell}; SIGTERM exact PID(s) {','.join(pids)}")
            for exact_pid in pids:
                sh(["kill", "-TERM", exact_pid])
            label = {
                "primary": "identical-call-loop",
                "sub_labels": ["scroll-loop"],
                "notes": (
                    "Operator-SIGTERM per the documented >=30 identical digit-stripped "
                    "tool-command substance rule; see the preserved transcript and monitor log."
                ),
                "labeler": "operator-monitoring-supervisor",
                "labeled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            (transcript.parent / "label.json").write_text(json.dumps(label, indent=2) + "\n")
            sh(["docker", "rm", "-f", f"bench-sandbox-{cell}"])
        elif result.returncode == 2:
            log(
                f"SUBSTANCE: runaway-generation suspected for {cell}; "
                f"endpoint_up={endpoint_up(target['port'])}"
            )


# --- recent cells + fails ---------------------------------------------------
def recent_cells_and_fails(cfg=None, limit: int = 8):
    """Last ~`limit` completed cells (by summary mtime) with wall+verdict, plus all failed run_names."""
    arm_frag = _arm_label_glob(cfg) if cfg else "397b-"
    sums = sorted(LOGS.glob(f"p*_{arm_frag}*_v*/summary.json"), key=lambda p: p.stat().st_mtime)
    recent = []
    for sp in sums[-limit:]:
        rn = sp.parent.name
        w, tp = cell_metrics(rn)
        recent.append({
            "run": rn,
            "verdict": cell_verdict(rn),
            "wall_s": w,
            "tok_ps": tp,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sp.stat().st_mtime)),
        })
    recent.reverse()
    fails = []
    for sp in sums:
        rn = sp.parent.name
        v = cell_verdict(rn)
        if v is not None and v not in ("PASS", "STRUCTURAL_PASS"):
            fails.append(rn)
    return recent, fails


# --- addition C: harness-break anomaly detection ----------------------------
def check_harness_anomaly(cfg):
    """Pushover priority-1 if the >=3 most-recently-graded cells are all harness
    breaks (GRADER_FAILED/MISSING_OUTPUT). Idempotent within a run: we only alert
    when the trailing streak first crosses the threshold, tracked in a state file.
    """
    try:
        arm_frag = _arm_label_glob(cfg)
        sums = sorted(LOGS.glob(f"p*_{arm_frag}*_v*/summary.json"),
                      key=lambda p: p.stat().st_mtime)
        # trailing streak of harness-break verdicts among graded cells (newest first)
        streak = []
        for sp in reversed(sums):
            v = cell_verdict(sp.parent.name)
            if v is None:
                continue  # not graded yet; skip, keep scanning older graded cells
            if v in HARNESS_BREAK_VERDICTS:
                streak.append(sp.parent.name)
            else:
                break
        streak_n = len(streak)
        state_f = STATE_DIR / "anomaly_state.json"
        try:
            prev = json.loads(state_f.read_text()).get("alerted_streak", 0)
        except Exception:
            prev = 0
        if streak_n >= ANOMALY_RUN_THRESHOLD and streak_n != prev:
            cells = ", ".join(streak[:5])
            notify("bench: HARNESS ANOMALY",
                   f"{streak_n} consecutive grader breaks ({'/'.join(HARNESS_BREAK_VERDICTS)}): "
                   f"{cells} — likely a grader/harness fault, not model quality.", 1)
            log(f"ANOMALY: {streak_n} consecutive harness-break cells: {cells}")
        # remember the current streak so we don't re-alert on the same streak,
        # but DO alert again if it grows (e.g. 3 -> 4 -> 5).
        try:
            state_f.write_text(json.dumps({"alerted_streak": streak_n,
                                           "cells": streak[:10]}))
        except Exception:
            pass
        return streak_n
    except Exception as e:
        log(f"anomaly check failed (non-fatal): {e}")
        return 0


def write_status(cfg, target, phase, arms_done, started_at=None):
    arms = []
    grand_done = grand_total = 0
    all_walls = []
    for a in cfg["arms"]:
        done, total, pertask, metrics = arm_progress(a["label"], target)
        grand_done += done; grand_total += total
        if metrics["wall_median"] is not None:
            all_walls.append(metrics["wall_median"])
        arms.append({"label": a["label"], "done": done, "total": total,
                     "pertask": pertask, "metrics": metrics})
    cur = current_cell_info(cfg)
    rem = grand_total - grand_done
    eta_secs = None
    if all_walls and rem > 0:
        eta_secs = int(statistics.median(all_walls) * rem)
    recent, fails = recent_cells_and_fails(cfg)
    now = time.time()
    lane_endpoint_status = {
        str(port): endpoint_up(port) for port in configured_ports(cfg)
    }
    status = {
        # ---- original keys (unchanged) ----
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_n": target, "phase": phase,
        "endpoint_up": all(lane_endpoint_status.values()),
        "container_up": runtime_running(cfg),
        "grand_done": grand_done, "grand_total": grand_total,
        "pct": round(100 * grand_done / grand_total, 1) if grand_total else 0,
        "current": cur, "arms": arms, "arms_done": arms_done, "tasks": TASKS,
        "eta_secs": eta_secs,
        "recent_cells": recent,
        "fails": fails,
        "started_at": started_at,
        "elapsed_secs": int(now - started_at) if isinstance(started_at, (int, float)) else None,
        # ---- v2 additive keys ----
        "preset": cfg.get("preset"),       # addition A: which preset is driving
        "model": cfg.get("model"),
        "engine": cfg.get("engine", "llamacpp"),
        "lane_endpoints": lane_endpoint_status,
        "runtime_up": runtime_running(cfg),
    }
    STATUS.write_text(json.dumps(status, indent=2))
    return status


# --- addition B: findings scorecard + git commit ----------------------------
def _date_from_status():
    """Date string for the results branch — taken from status.json 'updated'
    (YYYY-MM-DD), falling back to today's UTC date."""
    try:
        upd = json.loads(STATUS.read_text()).get("updated", "")
        if upd and len(upd) >= 10:
            return upd[:10]
    except Exception:
        pass
    return time.strftime("%Y-%m-%d", time.gmtime())


def build_scorecard(cfg, target, final_status):
    """Render a findings scorecard markdown: per-task pass/N for both arms, totals,
    and deltas vs the N=10 no-think baseline. Returns the markdown string."""
    lines = []
    model = cfg.get("model", "?")
    preset = cfg.get("preset", "?")
    date = _date_from_status()
    lines.append(f"# MMBT findings scorecard — {model}")
    lines.append("")
    lines.append(f"- Preset: `{preset}`  ·  Engine: `{cfg.get('engine','llamacpp')}`  ·  N={target}")
    lines.append(f"- Generated: {final_status.get('updated','?')}  ·  Phase: {final_status.get('phase','?')}")
    lines.append(f"- Cells: {final_status.get('grand_done','?')}/{final_status.get('grand_total','?')}")
    lines.append("")

    # per-arm pertask, indexed by label for the table
    arm_pt = {}
    arm_meta = {}
    for a in final_status.get("arms", []):
        arm_pt[a["label"]] = a.get("pertask", {}) or {}
        arm_meta[a["label"]] = a.get("metrics", {}) or {}
    arm_labels = [a["label"] for a in cfg["arms"]]

    # main grid: task | <arm> pass/N | ... | baseline-delta (nothink arm only)
    header = "| task | " + " | ".join(arm_labels) + " | Δ vs N=10 (nothink) |"
    sep = "|" + "---|" * (2 + len(arm_labels))
    lines.append(header)
    lines.append(sep)
    arm_totals = {lbl: [0, 0] for lbl in arm_labels}   # [pass, done]
    for t in TASKS:
        cells = [f"`{t}`"]
        for lbl in arm_labels:
            pt = arm_pt.get(lbl, {}).get(t, {})
            p = pt.get("pass", 0); d = pt.get("done", 0)
            arm_totals[lbl][0] += p; arm_totals[lbl][1] += d
            cells.append(f"{p}/{d}")
        # baseline delta uses the nothink arm if present
        nothink = next((l for l in arm_labels if BASELINE_ARM_HINT in l), None)
        dcell = ""
        if nothink is not None:
            pt = arm_pt.get(nothink, {}).get(t, {})
            base = BASELINE_N10_NOTHINK.get(t)
            if base is not None and isinstance(pt.get("pass"), int):
                dcell = f"{pt['pass'] - base:+d} (base {base}/10)"
        cells.append(dcell)
        lines.append("| " + " | ".join(cells) + " |")

    # totals row
    trow = ["**TOTAL**"]
    for lbl in arm_labels:
        p, d = arm_totals[lbl]
        trow.append(f"**{p}/{d}**")
    nothink = next((l for l in arm_labels if BASELINE_ARM_HINT in l), None)
    if nothink is not None:
        p = arm_totals[nothink][0]
        trow.append(f"**{p - BASELINE_N10_TOTAL_PASS:+d} vs {BASELINE_N10_TOTAL_PASS}/{BASELINE_N10_TOTAL_CELLS}**")
    else:
        trow.append("")
    lines.append("| " + " | ".join(trow) + " |")
    lines.append("")

    # pass-rate summary + timing
    lines.append("## Summary")
    lines.append("")
    base_rate = BASELINE_N10_TOTAL_PASS / BASELINE_N10_TOTAL_CELLS * 100
    for lbl in arm_labels:
        p, d = arm_totals[lbl]
        rate = (100 * p / d) if d else 0.0
        m = arm_meta.get(lbl, {})
        wall = f"{m.get('wall_median')/60:.1f} min/cell" if m.get("wall_median") else "n/a"
        tps = f"{m.get('tok_ps_median')} tok/s" if m.get("tok_ps_median") else "n/a"
        extra = ""
        if BASELINE_ARM_HINT in lbl:
            extra = f"  ·  Δ {rate - base_rate:+.1f}pp vs N=10 baseline ({base_rate:.1f}%)"
        lines.append(f"- **{lbl}**: {p}/{d} pass = {rate:.1f}%  ·  median {wall}  ·  {tps}{extra}")
    lines.append("")
    if final_status.get("fails"):
        lines.append(f"Non-pass cells ({len(final_status['fails'])}): " +
                     ", ".join(f"`{x}`" for x in final_status["fails"][:40]))
        lines.append("")
    return "\n".join(lines) + "\n"


def publish_scorecard(cfg, target, final_status):
    """Write scorecard.md and git add+commit to bench-results-<date> in ~/bench.
    Idempotent (re-runs update the same file/branch). NEVER raises — git failures
    are logged and swallowed so they can't crash the run."""
    try:
        md = build_scorecard(cfg, target, final_status)
        SCORECARD.write_text(md)
        log(f"scorecard written to {SCORECARD} ({len(md)} bytes)")
    except Exception as e:
        log(f"publish: failed to build/write scorecard (non-fatal): {e}")
        return
    try:
        date = _date_from_status()
        branch = f"bench-results-{date}"
        # mirror the scorecard into the repo so it can be committed
        repo_path = BENCH / "results" / f"scorecard-{cfg.get('model','model')}-N{target}.md"
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        repo_path.write_text(md)

        def git(*args, check=False):
            r = sh(["git", "-C", str(BENCH), *args])
            if r.returncode != 0:
                log(f"publish git {' '.join(args)} rc={r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")
            return r

        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            log("publish: ~/bench is not a git work tree — skipping commit (scorecard.md still written)")
            return
        # create-or-switch to the results branch idempotently
        if git("rev-parse", "--verify", branch).returncode == 0:
            git("checkout", branch)
        else:
            git("checkout", "-b", branch)
        git("add", str(repo_path), str(SCORECARD) if str(SCORECARD).startswith(str(BENCH)) else str(repo_path))
        # commit; "nothing to commit" is fine (idempotent re-run)
        c = git("commit", "-m",
                f"bench results: {cfg.get('model','model')} N={target} "
                f"({final_status.get('grand_done','?')}/{final_status.get('grand_total','?')} cells)")
        if c.returncode == 0:
            log(f"publish: committed scorecard to branch {branch} (not pushed)")
        else:
            log(f"publish: no new commit on {branch} (idempotent / nothing changed)")
    except Exception as e:
        log(f"publish: git step failed (non-fatal): {e}")


def benchmark_environment(cfg, base_env=None, arm=None):
    """Return the child environment carrying a model's pinned sampling point.

    ``run_microbench.sh`` intentionally keeps historical defaults, so model-card
    campaigns must pass their explicit overrides through the supervisor.  Keep
    this in a testable helper: a config field that is only written to a receipt
    or README but not sent to the harness is a methodology failure.
    """
    run_env = dict(os.environ if base_env is None else base_env)
    sampling_env = {
        "benchmark_temperature": "BENCH_TEMP",
        "benchmark_top_p": "BENCH_TOP_P",
        "benchmark_top_k": "BENCH_TOP_K",
        "benchmark_min_p": "BENCH_MIN_P",
        "benchmark_presence_penalty": "BENCH_PRESENCE_PENALTY",
        "benchmark_repeat_penalty": "BENCH_REPEAT_PENALTY",
        "benchmark_seed": "BENCH_SEED",
        "benchmark_max_output_tokens_cap": "BENCH_MAX_OUTPUT_TOKENS_CAP",
        "benchmark_sandbox_gpus": "BENCH_SANDBOX_GPUS",
        "preserve_thinking": "BENCH_PRESERVE_THINKING",
        "reasoning_effort_location": "BENCH_REASONING_EFFORT_LOCATION",
        "serving_manifest": "BENCH_SERVING_MANIFEST",
    }
    for config_key, env_key in sampling_env.items():
        value = arm.get(config_key, cfg.get(config_key)) if arm else cfg.get(config_key)
        if value is not None:
            run_env[env_key] = str(value).lower() if isinstance(value, bool) else str(value)
        else:
            run_env.pop(env_key, None)
    return run_env


def run_arm_with_supervision(cfg, arm, target, started_at):
    """Shard one arm deterministically across configured replica endpoints."""
    label, thinking = arm["label"], arm["thinking"]
    # Scope to THIS arm only. A global wipe kills concurrent campaigns' live cells
    # mid-run; harness.py names sandboxes per-cell so parallel runs can coexist.
    ids = sh(f"docker ps -aq --filter name=bench-sandbox-.*{label}").stdout.split()
    if ids:
        sh(["docker", "rm", "-f", *ids])
    cleanup_pattern(TOOLING / "workspace", f"*{label}_v*")
    ports = configured_ports(cfg)
    lane_count = len(ports)
    log(f"RUN arm {label} (thinking={thinking}) target N={target} lanes={ports}")
    procs = []
    handles = []
    try:
        for lane_index, port in enumerate(ports):
            run_env = benchmark_environment(cfg, arm=arm)
            run_env["BENCH_LANE_INDEX"] = str(lane_index)
            run_env["BENCH_LANE_COUNT"] = str(lane_count)
            log_path = STATE_DIR / (
                f"run-{label}.log" if lane_count == 1
                else f"run-{label}-lane{lane_index}-port{port}.log"
            )
            handle = open(log_path, "a")
            handles.append(handle)
            proc = subprocess.Popen(
                ["bash", str(SCRIPTS / "run_microbench.sh"), cfg["model"], str(port),
                 label, str(target), str(arm.get("reasoning_effort", "")),
                 thinking, str(cfg["max_model_len"])],
                stdout=handle, stderr=subprocess.STDOUT, env=run_env)
            procs.append((lane_index, port, proc))

        last_endpoint_ok = {port: time.time() for port in ports}
        lane_progress = {
            port: {"cell": None, "signal": None, "last_progress": time.time()}
            for port in ports
        }
        while any(proc.poll() is None for _, _, proc in procs):
            time.sleep(30)
            write_heartbeat()
            write_status(cfg, target, f"run:{label}", [], started_at)
            check_harness_anomaly(cfg)                        # addition C
            check_current_substance(cfg)
            for port in ports:
                if endpoint_up(port):
                    last_endpoint_ok[port] = time.time()
                elif time.time() - last_endpoint_ok[port] > 90:
                    log(f"watchdog: endpoint lane {port} down >90s — restarting runtime")
                    ensure_endpoint(cfg)
                    last_endpoint_ok[port] = time.time()
            # Transcript mtimes do not advance while urllib waits for a
            # non-streamed response. Watch each replica independently and count
            # live llama.cpp slot-token movement as progress so native-context
            # generations are not mistaken for hung harnesses.
            now = time.time()
            active = active_harnesses_by_port()
            for port in ports:
                harness = active.get(port)
                watch = lane_progress[port]
                if not harness:
                    watch.update(cell=None, signal=None, last_progress=now)
                    continue
                cell = harness["cell"]
                transcript = LOGS / cell / "transcript.jsonl"
                try:
                    transcript_mtime_ns = transcript.stat().st_mtime_ns
                except OSError:
                    transcript_mtime_ns = None
                signal = (cell, transcript_mtime_ns, endpoint_slot_progress(port))
                if watch["cell"] != cell or watch["signal"] != signal:
                    watch.update(cell=cell, signal=signal, last_progress=now)
                    continue
                frozen_secs = int(now - watch["last_progress"])
                stuck_limit, phase = watchdog_stuck_policy(cfg, transcript)
                if frozen_secs > stuck_limit:
                    log(
                        f"STUCK: lane port {port} cell {cell} showed no transcript "
                        f"or server-slot progress for {frozen_secs}s "
                        f"(phase={phase}, limit={stuck_limit}s)"
                    )
                    kill_stuck(cell)
                    watch.update(cell=None, signal=None, last_progress=now)
        lane_results = {port: proc.returncode for _, port, proc in procs}
        log(f"run_microbench {label} lane exit codes={lane_results}")
    finally:
        for handle in handles:
            handle.close()
    cleanup_pattern(Path("/tmp"), f"grade_*{label}_v*")
    g = sh(["bash", str(SCRIPTS / "grade_microbench.sh"), label])
    (STATE_DIR / f"grade-{label}.log").write_text(g.stdout + g.stderr)
    s = sh(["bash", str(SCRIPTS / "summarize.sh"), label])
    (STATE_DIR / f"summary-{label}.txt").write_text(s.stdout + s.stderr)
    log(f"graded+summarized {label}")
    check_harness_anomaly(cfg)                                # addition C (post-grade)
    done, total, pertask, metrics = arm_progress(label, target)
    npass = sum(p["pass"] for p in pertask.values())
    wall = f"{metrics['wall_median']/60:.1f}m" if metrics["wall_median"] else "?"
    tps = f"{metrics['tok_ps_median']}" if metrics["tok_ps_median"] else "?"
    notify("bench: arm complete",
           f"{label} {done}/{total} cells, {npass} pass — median {wall}/cell, {tps} tok/s", 0)


def all_done(cfg, target) -> bool:
    for a in cfg["arms"]:
        done, total, _, _ = arm_progress(a["label"], target)
        if done < total:
            return False
    return True


def resolve_config(args):
    """addition A: build the active config from --preset, then DEFAULT_CONFIG
    fallback, then --config overrides (config file still wins, additive)."""
    if args.preset:
        if args.preset not in PRESETS:
            raise SystemExit(f"unknown --preset '{args.preset}'. choices: {', '.join(PRESETS)}")
        cfg = dict(PRESETS[args.preset])
        cfg["preset"] = args.preset
    else:
        cfg = dict(DEFAULT_CONFIG)
        cfg["preset"] = "397b"
    if args.config and Path(args.config).exists():
        cfg.update(json.loads(Path(args.config).read_text()))
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-n", type=int, default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--max-passes", type=int, default=6)
    ap.add_argument("--once", action="store_true",
                    help="write a single status snapshot and exit (for external monitors)")
    ap.add_argument("--preset", default=None,
                    help=f"model preset selecting model/container/gguf/ctx/arms. choices: {', '.join(PRESETS)}")
    ap.add_argument("--publish", action="store_true",
                    help="on a COMPLETE run, write scorecard.md + git-commit it to bench-results-<date> (no push)")
    args = ap.parse_args()
    cfg = resolve_config(args)

    if args.once:
        target = args.target_n
        if target is None:
            try:
                target = int(json.loads(STATUS.read_text()).get("target_n", 1))
            except Exception:
                target = 1
        write_status(cfg, target, "snapshot", [])
        print("AUTOPILOT_SNAPSHOT")
        return

    if args.target_n is None:
        ap.error("--target-n is required unless --once is given")
    target = args.target_n

    fh = fresh_heartbeat()
    if fh:
        age, pid = fh
        msg = (f"ABORT: another autopilot heartbeat is fresh ({age:.0f}s old, pid={pid}). "
               f"Refusing to double-drive. If that process is dead, remove {HEARTBEAT}.")
        log(msg)
        print(msg, file=sys.stderr)
        print("AUTOPILOT_ABORTED_DOUBLE_DRIVE")
        sys.exit(3)

    started_at = time.time()
    write_heartbeat()
    log(f"=== AUTOPILOT START target N={target} preset={cfg.get('preset')} model={cfg.get('model')} ===")
    notify("bench: autopilot start", f"N={target}, {len(cfg['arms'])} arms, model {cfg['model']}", 0)
    write_status(cfg, target, "starting", [], started_at)
    for p in range(1, args.max_passes + 1):
        if all_done(cfg, target):
            break
        log(f"--- pass {p}/{args.max_passes} ---")
        write_heartbeat()
        if not ensure_endpoint(cfg):
            log("endpoint unrecoverable; sleeping 60s then retrying"); time.sleep(60); continue
        for a in cfg["arms"]:
            done, total, _, _ = arm_progress(a["label"], target)
            if done < total:
                run_arm_with_supervision(cfg, a, target, started_at)
        write_status(cfg, target, f"pass{p}-done", [a["label"] for a in cfg["arms"]], started_at)
    final = write_status(cfg, target,
                         "COMPLETE" if all_done(cfg, target) else "INCOMPLETE", [], started_at)
    log(f"=== AUTOPILOT DONE phase={final['phase']} {final['grand_done']}/{final['grand_total']} ===")
    if final["phase"] == "COMPLETE":
        notify("bench: run COMPLETE",
               f"N={target} done — {final['grand_done']}/{final['grand_total']} cells, "
               f"{len(final['fails'])} fails", 0)
        if args.publish:                                      # addition B
            publish_scorecard(cfg, target, final)
    else:
        notify("bench: run INCOMPLETE",
               f"N={target} stopped at {final['grand_done']}/{final['grand_total']} cells "
               f"after {args.max_passes} passes — {len(final['fails'])} fails", 1)
        if args.publish:
            log("publish: run INCOMPLETE — scorecard NOT committed (only COMPLETE runs publish)")
    print("AUTOPILOT_COMPLETE" if final["phase"] == "COMPLETE" else "AUTOPILOT_INCOMPLETE")


if __name__ == "__main__":
    main()
