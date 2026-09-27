#!/usr/bin/env python3
"""Owned native DSV study driver. Stdlib only. No actuation."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

B = Path("/mnt/bulk/codex-work/four-gpu-dsv41-20260926")
URL = "http://127.0.0.1:8010"
MODEL = "deepseek-v4.1-flash"
CKPT = "fb2764a5cf321eaa5070ca8f9e892818f477c16d"
IMG = "sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f"
CONTAINER = "mmbt-dsv41"
HTTP_TIMEOUT = 120.0
PHASE_RE = re.compile(r"^[A-Za-z0-9-]+$")


def _load_parser():
    spec = importlib.util.spec_from_file_location(
        "native_sse_parser", str(B / "native_sse_parser.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load native_sse_parser")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_diag():
    path = B / "native-acoustic-diagnostic.py"
    spec = importlib.util.spec_from_file_location("native_acoustic_diagnostic", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load native-acoustic-diagnostic")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_api_key() -> str:
    p = B / "model-state" / "api-key"
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600 or not 1 <= st.st_size <= 4096:
            raise RuntimeError("API credential file rejected")
        value = os.read(fd, 4097).decode("ascii").strip()
        if not value or any(c.isspace() for c in value): raise RuntimeError("API credential rejected")
        return value
    finally:
        os.close(fd)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _http_get(path: str, key: str) -> dict:
    req = urllib.request.Request(
        URL + path,
        headers={"Authorization": "Bearer " + key},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_post_json(path: str, key: str, body: dict, timeout: float):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        URL + path,
        data=data,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _verify_runtime(key: str) -> dict:
    rt_path = B / "evidence" / "native-runtime-start.json"
    rt = json.loads(rt_path.read_text())
    if rt.get("checkpointRevision") != CKPT:
        raise RuntimeError("runtime checkpoint mismatch")
    if rt.get("imageId") != IMG:
        raise RuntimeError("runtime image mismatch")
    models = _http_get("/v1/models", key)
    ids = [m.get("id") for m in models.get("data", [])]
    if len(ids) != 1 or ids[0] != MODEL:
        raise RuntimeError("exact loaded model mismatch")
    return {"runtime": rt, "verifiedModels": models}


def _verify_docker_image() -> None:
    out = subprocess.run(
        ["docker", "inspect", "--format",
         "{{.Image}}|{{.State.Running}}|{{.State.Paused}}", CONTAINER],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError("docker inspect failed")
    img, running, paused = out.stdout.strip().split("|")
    if img != IMG:
        raise RuntimeError("docker image mismatch")
    if running != "true":
        raise RuntimeError("container not running")
    if paused != "false":
        raise RuntimeError("container paused")


def _verify_guard_config(out_dir) -> dict:
    cfg_path = B / "guard-config" / "profile.json"
    raw = cfg_path.read_bytes()
    cfg = json.loads(raw)
    if type(cfg.get("power_limit_w")) is not int or not 150 <= cfg["power_limit_w"] <= 275:
        raise RuntimeError("power_limit_w exceeds 275")
    if set(cfg) - {"power_limit_w", "mode", "fixed_targets"} or cfg.get("mode") not in ("auto", "fixed"):
        raise RuntimeError("profile rejected")
    if cfg["mode"] == "auto" and "fixed_targets" in cfg: raise RuntimeError("auto profile rejected")
    if cfg["mode"] == "fixed":
        targets = cfg.get("fixed_targets")
        if type(targets) is not dict or set(targets) != _load_diag().UUIDS or any(type(v) is not int or not 30 <= v <= 100 for v in targets.values()):
            raise RuntimeError("fixed targets rejected")
    snap_dir = out_dir / "guard-config"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / "profile.json"
    snap.write_bytes(raw)
    return {"path": str(snap), "sha256": _sha256_bytes(raw), "bytes": raw}


def _verify_guard_state() -> dict:
    return _load_diag().sample()


def _verify_watchdog() -> None:
    out = subprocess.run(
        ["systemctl", "--user", "is-active", "mmbt-qwen-thermal-watchdog.service"],
        capture_output=True, text=True, timeout=15,
    )
    if out.stdout.strip() != "active":
        raise RuntimeError("watchdog not active")
    abort = B / "evidence" / "qwen-watchdog" / "abort.json"
    if abort.exists():
        raise RuntimeError("watchdog abort present")


def _load_fixtures(name: str) -> dict:
    p = B / "evidence" / name
    if Path(name).name != name or p.resolve().parent != (B / "evidence").resolve():
        raise RuntimeError("fixture path rejected")
    fx = json.loads(p.read_text())
    if fx.get("inputTokens") != 8192:
        raise RuntimeError("fixture inputTokens must be 8192")
    recs = fx.get("records")
    if not isinstance(recs, list) or not recs:
        raise RuntimeError("fixture records missing")
    if type(fx.get("count")) is not int or fx["count"] != len(recs):
        raise RuntimeError("fixture count mismatch")
    seen = set(); nonces = set()
    for r in recs:
        idx = r.get("index")
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
            raise RuntimeError("fixture index invalid")
        if idx in seen:
            raise RuntimeError("duplicate fixture index")
        seen.add(idx)
        ids = r.get("input_ids")
        if not isinstance(ids, list) or len(ids) != 8192:
            raise RuntimeError("fixture input_ids length mismatch")
        for v in ids:
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise RuntimeError("fixture input_ids must be nonneg ints")
        if r.get("inputTokens") != 8192:
            raise RuntimeError("fixture record inputTokens mismatch")
        compact = json.dumps(ids, separators=(",", ":")).encode("utf-8")
        if _sha256_bytes(compact) != r.get("inputIdsSha256"):
            raise RuntimeError("fixture inputIdsSha256 mismatch")
        if not isinstance(r.get("nonce"), str) or not r["nonce"] or r["nonce"] in nonces:
            raise RuntimeError("fixture nonce missing")
        nonces.add(r["nonce"])
    return fx


class Monitor:
    def __init__(self, diag, out_path: Path, config_bytes, operating_max_c=None):
        if operating_max_c is not None and (type(operating_max_c) is not int or operating_max_c not in (80,82)):
            raise ValueError('Quiet study operating maximum must be80 or82C')
        self.diag = diag
        self.out_path = out_path
        self._stop = threading.Event()
        self._thread = None
        self._err = None
        self._baseline = None
        self.config_bytes = config_bytes
        self.operating_max_c = operating_max_c

    def _loop(self):
        try:
            with self.out_path.open("a") as f:
                while not self._stop.is_set():
                    t0 = time.monotonic()
                    s = None
                    try:
                        s = self.diag.sample()
                        temperatures=[float(r['temperature.gpu']) for r in s['rows']]
                        if any(not math.isfinite(v) or v<0 for v in temperatures):
                            raise RuntimeError('Invalid study temperature')
                        if self.operating_max_c is None:
                            if any(v>=79 for v in temperatures):
                                raise RuntimeError('Study soft thermal ceiling 79 C reached')
                        elif any(v>self.operating_max_c for v in temperatures):
                            raise RuntimeError(f'Quiet study operating maximum{self.operating_max_c} C exceeded')
                        if (B / "guard-config/profile.json").read_bytes() != self.config_bytes:
                            raise RuntimeError("profile changed during trial")
                        if (B / "evidence/qwen-watchdog/abort.json").exists(): raise RuntimeError("watchdog aborted")
                        state = self.diag.inspect()
                        if not state["Running"] or state["Paused"]: raise RuntimeError("runtime interrupted")
                        old = {r["uuid"]: r for r in self._baseline["rows"]}
                        if any(r[k] != old[r["uuid"]][k] for r in s["rows"] for k in self.diag.FIELDS[-3:]):
                            raise RuntimeError("thermal/brake counter changed")
                        if s["vmstat"]["oom_kill"] != self._baseline["vmstat"]["oom_kill"]: raise RuntimeError("OOM counter changed")
                    except Exception as e:
                        self._err = ("sample", type(e).__name__, str(e)[:200])
                        try: self.diag.pause()
                        except Exception: pass
                        try:
                            _write_json(self.out_path.with_name('monitor-fault.json'),
                                        {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                         'monotonic':time.monotonic(),'error':self._err,'observedSample':s})
                        except Exception as record_error:
                            self._err=('sample',type(e).__name__,str(e)[:100]+'; fault persistence failed: '+type(record_error).__name__)
                        return
                    f.write(json.dumps({"t": time.time(), "sample": s}) + "\n")
                    f.flush()
                    dt = 1.0 - (time.monotonic() - t0)
                    if dt > 0:
                        self._stop.wait(dt)
        except Exception as e:
            self._err = ("loop", type(e).__name__, str(e)[:200])
            try:self.diag.pause()
            except Exception:pass

    def start(self):
        self._baseline = self.diag.sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)

    @property
    def error(self):
        return self._err

    @property
    def baseline(self):
        return self._baseline


def _stream_one(key: str, ids: list, budget: int, wave_start: float, jsonl_path: Path):
    body = {
        "input_ids": ids,
        "stream": True,
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": budget,
            "ignore_eos": True,
        },
    }
    lines = []
    resp = _http_post_json("/generate", key, body, HTTP_TIMEOUT)
    try:
        with jsonl_path.open("w") as jf:
            for raw in resp:
                t = time.monotonic() - wave_start
                if not raw:
                    continue
                line = raw.rstrip(b"\r\n")
                if not line:
                    continue
                s = line.decode("utf-8")
                jf.write(json.dumps({"seconds": t, "line": s}) + "\n")
                lines.append((t, line))
    finally:
        resp.close()
    return lines


def _pause_container():
    return _load_diag().pause()


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase")
    ap.add_argument("fixtures")
    ap.add_argument("seconds", type=int)
    ap.add_argument("concurrency", type=int)
    ap.add_argument("budget", type=int)
    ap.add_argument('--operating-max-c',type=int,choices=[80,82],default=None)
    args = ap.parse_args()

    if not PHASE_RE.match(args.phase):
        print("invalid phase", file=sys.stderr)
        return 2
    if not (0 <= args.seconds <= 1800):
        print("seconds out of range", file=sys.stderr)
        return 2
    if not (1 <= args.concurrency <= 8):
        print("concurrency out of range", file=sys.stderr)
        return 2
    if not (64 <= args.budget <= 4096):
        print("budget out of range", file=sys.stderr)
        return 2
    if 8192 + args.budget >= 409600:
        print("input+output too large", file=sys.stderr)
        return 2

    out_dir = B / "evidence" / args.phase
    if out_dir.exists():
        print("output dir exists", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True)

    result = {
        "phase": args.phase,
        "utcStart": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostBootId": Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        "sourceHashes": None,
        "softThermalCeilingC": 79 if args.operating_max_c is None else None,
        "operatingMaxCoreC": args.operating_max_c,
        "fixtures": args.fixtures,
        "seconds": args.seconds,
        "concurrency": args.concurrency,
        "budget": args.budget,
        "status": "init",
        "waves": [],
        "error": None,
        "totalElapsed": None,
        "callsComplete": 0,
        "totalActualOutputTokens": 0,
        "totalPromptTokens": 0,
        "commonWindowResults": [],
        "finishReasons": [],
        "e2ePerCallTimings": [],
        "baseline": None,
        "guardConfig": None,
        "runtime": None,
        "verifiedModels": None,
    }
    result_path = out_dir / "result.json"

    monitor = None
    paused = False
    try:
        source_dir=out_dir/'sources';source_dir.mkdir()
        result['sourceHashes']={}
        for name in ('native-wave-client.py','native_sse_parser.py','native-acoustic-diagnostic.py'):
            source=(B/name).read_bytes();(source_dir/name).write_bytes(source)
            result['sourceHashes'][name]=_sha256_bytes(source)
        parser = _load_parser()
        diag = _load_diag()
        key = _read_api_key()

        runtime_info = _verify_runtime(key)
        _verify_docker_image()
        cfg_info = _verify_guard_config(out_dir)
        _verify_guard_state()
        _verify_watchdog()

        result["runtime"] = runtime_info["runtime"]
        result["verifiedModels"] = runtime_info["verifiedModels"]
        result["guardConfig"] = {
            "path": cfg_info["path"],
            "sha256": cfg_info["sha256"],
        }

        fx = _load_fixtures(args.fixtures)
        records = fx["records"]
        cursor = 0

        monitor = Monitor(diag, out_dir / "telemetry.jsonl", cfg_info["bytes"],args.operating_max_c)
        monitor.start()
        if monitor.error:
            raise RuntimeError("monitor failed: " + repr(monitor.error))
        result["baseline"] = monitor.baseline

        run_start = time.monotonic()
        result["runStartMonotonic"] = run_start
        wave_idx = 0

        def run_wave(wave_idx: int):
            nonlocal cursor
            if cursor + args.concurrency > len(records):
                raise RuntimeError("fixtures exhausted")
            batch = records[cursor:cursor + args.concurrency]
            cursor += args.concurrency
            wave_start = time.monotonic()
            wave_rel = wave_start - run_start
            parsed_records = []
            threads = []
            results = [None] * len(batch)
            errors = [None] * len(batch)
            timings = [None] * len(batch)
            timestamps = [None] * len(batch)

            def worker(i, rec):
                t0 = time.monotonic()
                utc_start = datetime.datetime.now(datetime.timezone.utc).isoformat()
                try:
                    jsonl = out_dir / f"{args.phase}-w{wave_idx}-r{rec['index']}.sse.jsonl"
                    lines = _stream_one(key, rec["input_ids"], args.budget, wave_start, jsonl)
                    parsed = parser.parse_sse(lines)
                    results[i] = (rec, parsed, jsonl)
                    timings[i] = time.monotonic() - t0
                    timestamps[i] = (utc_start, datetime.datetime.now(datetime.timezone.utc).isoformat())
                except Exception as e:
                    errors[i] = (type(e).__name__, str(e)[:300])

            for i, rec in enumerate(batch):
                th = threading.Thread(target=worker, args=(i, rec))
                th.start()
                threads.append(th)
            for th in threads:
                th.join()

            for i, err in enumerate(errors):
                if err is not None:
                    raise RuntimeError(f"stream {i} failed: {err[0]}: {err[1]}")

            for i, (rec, parsed, jsonl) in enumerate(results):
                fr = parsed["finish_reason"]
                if fr.get("type") != "length":
                    raise RuntimeError(f"stream {i} finish not length")
                if fr.get("length") != args.budget:
                    raise RuntimeError(f"stream {i} length != budget")
                mi = parsed["final_meta_info"]
                if mi.get("prompt_tokens") != len(rec["input_ids"]):
                    raise RuntimeError(f"stream {i} prompt_tokens mismatch")
                if mi.get("completion_tokens") != args.budget:
                    raise RuntimeError(f"stream {i} completion_tokens mismatch")
                if len(parsed["final_output_ids"]) != args.budget:
                    raise RuntimeError(f"stream {i} output_ids length mismatch")

                utc_start, utc_end = timestamps[i]
                receipt = {
                    "provider": "sglang-native-generate",
                    "worker": "tower2",
                    "runtime": runtime_info["runtime"],
                    "verifiedModels": runtime_info["verifiedModels"],
                    "utcStart": utc_start,
                    "utcEnd": utc_end,
                    "request": {
                        "inputIdsSha256": rec["inputIdsSha256"],
                        "inputTokens": rec["inputTokens"],
                        "maxNewTokens": args.budget,
                        "ignoreEos": True,
                    },
                    "response": {
                        "output_ids": parsed["final_output_ids"],
                        "text": parsed["final_text"],
                        "meta_info": parsed["final_meta_info"],
                    },
                }
                rpath = B / "evidence" / f"{args.phase}-w{wave_idx}-r{rec['index']}.generate-receipt.json"
                _write_json(rpath, receipt)

                parsed_records.append(parsed)
                result["callsComplete"] += 1
                result["totalActualOutputTokens"] += mi["completion_tokens"]
                result["totalPromptTokens"] += mi["prompt_tokens"]
                result["finishReasons"].append({
                    "wave": wave_idx,
                    "index": rec["index"],
                    "finish_reason": fr,
                })
                result["e2ePerCallTimings"].append({
                    "wave": wave_idx,
                    "index": rec["index"],
                    "seconds": timings[i],
                })

            analysis = parser.analyze(parsed_records)
            if analysis["status"] != "ok": raise RuntimeError("common-window qualification failed: " + analysis["status"])
            _write_json(out_dir / f"wave-{wave_idx}.json", {"wave_start_rel": wave_rel, "records": parsed_records, "analysis": analysis})
            wave_rec = {
                "wave": wave_idx,
                "wave_start_rel": wave_rel,
                "analysis": analysis,
                "streams": [
                    {
                        "index": rec["index"],
                        "inputIdsSha256": rec["inputIdsSha256"],
                        "finish_reason": parsed["finish_reason"],
                        "prompt_tokens": parsed["final_meta_info"]["prompt_tokens"],
                        "completion_tokens": parsed["final_meta_info"]["completion_tokens"],
                        "last_delivery_time": parsed["last_delivery_time"],
                    }
                    for rec, parsed, _ in results
                ],
            }
            result["waves"].append(wave_rec)
            result["commonWindowResults"].append({
                "wave": wave_idx,
                "status": analysis.get("status"),
                "aggregate_rate": analysis.get("aggregate_rate"),
                "shared_duration": analysis.get("shared_duration"),
            })

            elapsed = time.monotonic() - run_start
            temps = None
            try:
                s = diag.sample()
                temps = [row["temperature.gpu"] for row in s["rows"]]
            except Exception:
                temps = None
            print(
                f"wave={wave_idx} elapsed={elapsed:.1f}s "
                f"rate={analysis.get('aggregate_rate')} "
                f"status={analysis.get('status')} temps={temps}",
                flush=True,
            )
            return analysis

        if args.seconds == 0:
            run_wave(0)
        else:
            while True:
                if monitor.error: raise RuntimeError("monitor failed: " + repr(monitor.error))
                elapsed = time.monotonic() - run_start
                if elapsed >= args.seconds:
                    break
                run_wave(wave_idx)
                wave_idx += 1
            # drain last wave already done in loop; nothing extra

        result["totalElapsed"] = time.monotonic() - run_start
        if monitor.error: raise RuntimeError("monitor failed: " + repr(monitor.error))
        result["status"] = "ok"

        result["deliveredOutputTokensPerSecondIncludingPrefillAndDrain"] = result["totalActualOutputTokens"] / result["totalElapsed"]

    except Exception as e:
        result["status"] = "error"
        result["error"] = {"type": type(e).__name__, "message": str(e)[:500]}
        try:
            after = _pause_container()
            result["runtimeAfterFailure"] = after
            result["paused"] = after["paused"]
        except Exception as pe:
            result["pauseError"] = {"type": type(pe).__name__, "message": str(pe)[:200]}
    finally:
        if monitor is not None:
            monitor.stop()
            if monitor.error:
                result["monitorError"] = monitor.error
                result["status"] = "error"
                try: result["runtimeAfterFailure"] = _pause_container()
                except Exception as pe: result["pauseError"] = {"type": type(pe).__name__}
        _write_json(result_path, result)

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
