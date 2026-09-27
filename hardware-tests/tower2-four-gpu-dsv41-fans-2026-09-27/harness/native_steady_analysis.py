#!/usr/bin/env python3
"""Native steady-state analysis: CPU-only, stdlib-only.

Reads a trial directory's evidence (result.json, telemetry.jsonl, guard-config,
wave-N.json) and produces a qualified/measured rate summary. Delegates thermal
validation to the sibling native_thermal_validation module and SSE parsing to
native_sse_parser. Never actuates hardware, never spawns subprocesses, never
touches the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import native_sse_parser as sse  # noqa: E402
import native_thermal_validation as thermal  # noqa: E402

CHECKPOINT_REVISION = "fb2764a5cf321eaa5070ca8f9e892818f477c16d"
IMAGE_ID = "sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f"
MODEL_ID = "deepseek-v4.1-flash"
MIN_SECONDS = 480
EXPECTED_CONCURRENCY = 8
EXPECTED_BUDGET = 2048
EXPECTED_PROMPT = 8192
EXPECTED_COMPLETION = 2048
MIN_DECODE_COVERAGE = 60.0
SERIAL_TOLERANCE = 1e-3


class InputError(ValueError):
    pass


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _load_json(path: Path) -> Any:
    try:
        with path.open("rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError as e:
        raise InputError(f"missing file: {path}") from e
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise InputError(f"unreadable json {path}: {e}") from e


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise InputError(f"cannot hash {path}: {e}") from e
    return h.hexdigest()


def _load_telemetry(path: Path) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    try:
        with path.open("rb") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise InputError(f"telemetry line {lineno} malformed: {e}") from e
                if not isinstance(obj, dict):
                    raise InputError(f"telemetry line {lineno} not object")
                samples.append(obj)
    except FileNotFoundError as e:
        raise InputError(f"missing telemetry: {path}") from e
    except OSError as e:
        raise InputError(f"cannot read telemetry: {e}") from e
    return samples


def _validate_result(result: Dict[str, Any], reasons: List[str]) -> None:
    if result.get("status") != "ok":
        reasons.append(f"result.status != ok: {result.get('status')!r}")
    secs = result.get("seconds")
    if type(secs) is not int or secs < MIN_SECONDS:
        reasons.append(f"result.seconds invalid: {secs!r}")
    if type(result.get('concurrency')) is not int or result.get("concurrency") != EXPECTED_CONCURRENCY:
        reasons.append(f"concurrency != {EXPECTED_CONCURRENCY}: {result.get('concurrency')!r}")
    if type(result.get('budget')) is not int or result.get("budget") != EXPECTED_BUDGET:
        reasons.append(f"budget != {EXPECTED_BUDGET}: {result.get('budget')!r}")
    total_elapsed = result.get("totalElapsed")
    if not _finite(total_elapsed) or total_elapsed < 0:
        reasons.append(f"totalElapsed invalid: {total_elapsed!r}")
    elif _finite(secs) and total_elapsed < secs:
        reasons.append("totalElapsed < seconds")
    rs = result.get("runStartMonotonic")
    if not _finite(rs):
        reasons.append(f"runStartMonotonic invalid: {rs!r}")
    runtime = result.get("runtime")
    if not isinstance(runtime, dict):
        reasons.append("runtime missing")
    else:
        if runtime.get("checkpointRevision") != CHECKPOINT_REVISION:
            reasons.append("runtime.checkpointRevision mismatch")
        if runtime.get("imageId") != IMAGE_ID:
            reasons.append("runtime.imageId mismatch")
    vm = result.get("verifiedModels")
    data = vm.get("data") if isinstance(vm, dict) else None
    if not isinstance(data, list) or len(data) != 1:
        reasons.append("verifiedModels.data must be single-entry list")
    else:
        entry = data[0]
        if not isinstance(entry, dict) or entry.get("id") != MODEL_ID:
            reasons.append("verifiedModels.data[0].id mismatch")


def _validate_guard_config(result: Dict[str, Any], trial_dir: Path, reasons: List[str]) -> None:
    gc = result.get("guardConfig")
    if not isinstance(gc, dict):
        reasons.append("guardConfig missing")
        return
    rel = gc.get("path")
    expected = gc.get("sha256")
    if not isinstance(rel, str) or not rel:
        reasons.append("guardConfig.path invalid")
        return
    if not isinstance(expected, str) or len(expected) != 64:
        reasons.append("guardConfig.sha256 invalid")
        return
    local = trial_dir / "guard-config" / "profile.json"
    if not local.is_file():
        reasons.append(f"guard-config/profile.json missing at {local}")
        return
    try:
        actual = _sha256_file(local)
    except InputError as e:
        reasons.append(str(e))
        return
    if actual != expected:
        reasons.append("guard-config/profile.json sha256 mismatch")


def _validate_waves(
    result: Dict[str, Any], trial_dir: Path, reasons: List[str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    waves_meta = result.get("waves")
    if not isinstance(waves_meta, list) or not waves_meta:
        reasons.append("result.waves missing or empty")
        return [], []
    wave_files: List[Dict[str, Any]] = []
    prev_start: Optional[float] = None
    for idx, meta in enumerate(waves_meta):
        if not isinstance(meta, dict):
            reasons.append(f"waves[{idx}] not object")
            return wave_files, []
        if type(meta.get('wave')) is not int or meta['wave'] != idx:
            reasons.append(f'wave-{idx} metadata index mismatch');return wave_files, []
        wf_path = trial_dir / f"wave-{idx}.json"
        try:
            wf = _load_json(wf_path)
        except InputError as e:
            reasons.append(str(e))
            return wave_files, []
        if not isinstance(wf, dict):
            reasons.append(f"wave-{idx}.json not object")
            return wave_files, []
        start = wf.get("wave_start_rel")
        if not _finite(start) or start < 0:
            reasons.append(f"wave-{idx} wave_start_rel invalid: {start!r}")
            return wave_files, []
        if not _finite(meta.get('wave_start_rel')) or start != meta['wave_start_rel']:
            reasons.append(f'wave-{idx} metadata start mismatch');return wave_files, []
        if prev_start is not None and not (start > prev_start):
            reasons.append(f"wave-{idx} wave_start_rel not strictly increasing")
            return wave_files, []
        prev_start = start
        records = wf.get("records")
        if not isinstance(records, list) or len(records) != EXPECTED_CONCURRENCY:
            reasons.append(f"wave-{idx} records count != {EXPECTED_CONCURRENCY}")
            return wave_files, []
        wave_files.append({"index": idx, "wave_start_rel": float(start), "records": records})
    return wave_files, waves_meta


def _validate_records(
    wave_files: List[Dict[str, Any]], reasons: List[str]
) -> List[Dict[str, Any]]:
    analyses: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for wf in wave_files:
        idx = wf["index"]
        try:
            analysis = sse.analyze(wf["records"])
        except Exception as e:  # noqa: BLE001 - parser raises SSEError/ValueError
            reasons.append(f"wave-{idx} parser raised: {e}")
            return analyses
        if analysis.get("status") != "ok":
            reasons.append(f"wave-{idx} parser status {analysis.get('status')!r}: {analysis.get('reason')!r}")
            return analyses
        for rec in wf["records"]:
            mi = rec.get("final_meta_info")
            if not isinstance(mi, dict):
                reasons.append(f"wave-{idx} record missing final_meta_info")
                return analyses
            rid = mi.get("id")
            if not isinstance(rid, str) or not rid:
                reasons.append(f"wave-{idx} final_meta_info.id invalid")
                return analyses
            if rid in seen_ids:
                reasons.append(f"duplicate final_meta_info.id: {rid}")
                return analyses
            seen_ids.add(rid)
            if mi.get("prompt_tokens") != EXPECTED_PROMPT:
                reasons.append(f"wave-{idx} prompt_tokens != {EXPECTED_PROMPT}")
                return analyses
            if mi.get("completion_tokens") != EXPECTED_COMPLETION:
                reasons.append(f"wave-{idx} completion_tokens != {EXPECTED_COMPLETION}")
                return analyses
            fr = rec.get("finish_reason")
            if not isinstance(fr, dict) or fr.get("type") != "length" or fr.get("length") != EXPECTED_COMPLETION:
                reasons.append(f"wave-{idx} finish_reason invalid")
                return analyses
            fids = rec.get("final_output_ids")
            if not isinstance(fids, list) or len(fids) != EXPECTED_COMPLETION:
                reasons.append(f"wave-{idx} final_output_ids length != {EXPECTED_COMPLETION}")
                return analyses
        analyses.append(analysis)
    return analyses


def _validate_totals(
    result: Dict[str, Any], wave_files: List[Dict[str, Any]], reasons: List[str]
) -> None:
    total_calls = 0
    total_tokens = 0
    total_prompt = 0
    for wf in wave_files:
        for rec in wf["records"]:
            total_calls += 1
            mi = rec["final_meta_info"]
            total_tokens += int(mi["completion_tokens"])
            total_prompt += int(mi["prompt_tokens"])
    if type(result.get('callsComplete')) is not int or result.get("callsComplete") != total_calls:
        reasons.append(f"callsComplete {result.get('callsComplete')!r} != {total_calls}")
    if type(result.get('totalActualOutputTokens')) is not int or result.get("totalActualOutputTokens") != total_tokens:
        reasons.append(f"totalActualOutputTokens {result.get('totalActualOutputTokens')!r} != {total_tokens}")
    if type(result.get('totalPromptTokens')) is not int or result.get("totalPromptTokens") != total_prompt:
        reasons.append(f"totalPromptTokens {result.get('totalPromptTokens')!r} != {total_prompt}")


def _validate_serial(
    wave_files: List[Dict[str, Any]], reasons: List[str]
) -> None:
    for i in range(len(wave_files) - 1):
        cur = wave_files[i]
        nxt = wave_files[i + 1]
        max_t = 0.0
        for rec in cur["records"]:
            for ev in rec.get("events", []):
                t = ev.get("t")
                if _finite(t) and t > max_t:
                    max_t = float(t)
        cur_end_abs = cur["wave_start_rel"] + max_t
        if cur_end_abs > nxt["wave_start_rel"] + SERIAL_TOLERANCE:
            reasons.append(
                f"waves {i} and {i+1} overlap: end {cur_end_abs:.6f} > start {nxt['wave_start_rel']:.6f}"
            )


def _bursts(rec: Dict[str, Any]) -> List[Tuple[float, int]]:
    prev = 0
    out: List[Tuple[float, int]] = []
    for ev in rec.get("events", []):
        ids = ev.get("output_ids")
        if ids is None:
            continue
        n = len(ids)
        if n > prev:
            out.append((float(ev["t"]), n - prev))
        prev = n
    return out


def _first_positive(rec: Dict[str, Any]) -> Optional[float]:
    prev = 0
    for ev in rec.get("events", []):
        ids = ev.get("output_ids")
        if ids is None:
            continue
        if len(ids) > prev:
            return float(ev["t"])
        prev = len(ids)
    return None


def _last_positive(rec: Dict[str, Any]) -> Optional[float]:
    prev = 0
    last: Optional[float] = None
    for ev in rec.get("events", []):
        ids = ev.get("output_ids")
        if ids is None:
            continue
        if len(ids) > prev:
            last = float(ev["t"])
        prev = len(ids)
    return last


def _compute_rate(
    wave_files: List[Dict[str, Any]],
    total_elapsed: float,
    tail_seconds: float,
    reasons: List[str],
) -> Dict[str, Any]:
    tail_begin = max(0.0, total_elapsed - tail_seconds)
    total_bursts = 0
    coverage = 0.0
    per_wave: List[Dict[str, Any]] = []
    for wf in wave_files:
        start_rel = wf["wave_start_rel"]
        firsts: List[float] = []
        lasts: List[float] = []
        for rec in wf["records"]:
            f = _first_positive(rec)
            l = _last_positive(rec)
            if f is None or l is None:
                reasons.append(f"wave-{wf['index']} record missing positive emission")
                return {"measured_rate": None, "coverage_seconds": 0.0, "per_wave": per_wave}
            firsts.append(f)
            lasts.append(l)
        common_begin = max(firsts)
        common_end = min(lasts)
        clipped_begin = max(common_begin, tail_begin - start_rel)
        clipped_end = min(common_end, total_elapsed - start_rel)
        clip_dur = clipped_end - clipped_begin
        if clip_dur < 2.0:
            per_wave.append({
                "index": wf["index"],
                "skipped": True,
                "reason": f"clip duration {clip_dur:.3f}s < 2s",
                "tokens": 0,
                "duration": 0.0,
            })
            continue
        wave_tokens = 0
        for rec in wf["records"]:
            for t, delta in _bursts(rec):
                if clipped_begin < t <= clipped_end:
                    wave_tokens += delta
        total_bursts += wave_tokens
        coverage += clip_dur
        per_wave.append({
            "index": wf["index"],
            "skipped": False,
            "tokens": wave_tokens,
            "duration": clip_dur,
            "clipped_begin": clipped_begin,
            "clipped_end": clipped_end,
        })
    if coverage < MIN_DECODE_COVERAGE:
        reasons.append(f"decode coverage {coverage:.3f}s < {MIN_DECODE_COVERAGE}s")
    measured = (total_bursts / coverage) if coverage > 0 else None
    return {
        "measured_rate": measured,
        "coverage_seconds": coverage,
        "total_tokens": total_bursts,
        "per_wave": per_wave,
    }


def _secondary_rate(result):
    # Aggregate wall time includes prefill, dispatch, parsing and drain; never sum parallel call latencies.
    return result['totalActualOutputTokens']/result['totalElapsed']


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".summary-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def analyze_trial(trial_dir: str, tail_seconds: int = 180) -> Dict[str, Any]:
    """Analyze a native steady-state trial directory. Always writes summary.json."""
    reasons: List[str] = []
    trial_path = Path(trial_dir)
    summary: Dict[str, Any] = {
        "phase": trial_path.name,
        "qualified": False,
        "reasons": reasons,
        "accepted_rate": None,
        "measured_rate": None,
        "secondary_rate": None,
        "coverage_seconds": 0.0,
        "per_gpu": {},
        "vmstat_delta": None,
        "tail_vmstat_delta": None,
        "thermal": None,
        "per_wave": [],
    }

    try:
        if not trial_path.is_dir():
            raise InputError(f"trial_dir not a directory: {trial_path}")
        if not _finite(tail_seconds) or tail_seconds <= 0:
            raise InputError(f"tail_seconds invalid: {tail_seconds!r}")

        result = _load_json(trial_path / "result.json")
        if not isinstance(result, dict):
            raise InputError("result.json not object")

        _validate_result(result, reasons)
        operating_max=result.get('operatingMaxCoreC')
        if operating_max is not None and (type(operating_max) is not int or operating_max not in (80,82)):
            raise InputError('Invalid quiet operating maximum')
        if trial_path.name.startswith('native-quiet') and operating_max not in (80,82):
            raise InputError('Quiet trial missing registered operating maximum')
        _validate_guard_config(result, trial_path, reasons)

        wave_files, _ = _validate_waves(result, trial_path, reasons)
        if wave_files:
            analyses = _validate_records(wave_files, reasons)
            _validate_totals(result, wave_files, reasons)
            _validate_serial(wave_files, reasons)
            if len(analyses)!=len(wave_files):reasons.append('Not all waves validated')

        total_elapsed = result.get("totalElapsed")
        if not reasons and wave_files and _finite(total_elapsed) and total_elapsed > 0:
            rate_info = _compute_rate(wave_files, float(total_elapsed), float(tail_seconds), reasons)
            summary["measured_rate"] = rate_info["measured_rate"]
            summary["coverage_seconds"] = rate_info["coverage_seconds"]
            summary["per_wave"] = rate_info["per_wave"]
            summary["secondary_rate"] = _secondary_rate(result)

        samples = _load_telemetry(trial_path / "telemetry.jsonl")
        baseline = result.get("baseline")
        run_start = result.get("runStartMonotonic")
        if not isinstance(baseline, dict):
            reasons.append("result.baseline missing")
        elif not _finite(run_start):
            reasons.append("runStartMonotonic missing for thermal")
        elif not _finite(total_elapsed):
            reasons.append("totalElapsed missing for thermal")
        else:
            try:
                thermal_out = thermal.collect_thermal(
                    samples,
                    baseline,
                    float(run_start),
                    float(total_elapsed),
                    float(tail_seconds),
                    operating_max_c=operating_max,
                )
            except Exception as e:  # noqa: BLE001
                reasons.append(f"thermal validation raised: {e}")
                thermal_out = None
            if isinstance(thermal_out, dict):
                summary["thermal"] = thermal_out
                if thermal_out.get("qualified") is not True:
                    reasons.append("thermal validation not qualified")
                    for r in thermal_out.get("reasons", []) or []:
                        reasons.append(f"thermal: {r}")
                tail = thermal_out.get("tail") or {}
                per_gpu = tail.get("per_gpu") or {}
                summary["per_gpu"] = {
                    uuid: {
                        "temperature_c": v.get("temperature_c"),
                        "temperature_slope_c_per_min": v.get("temperature_slope_c_per_min"),
                        "fan_percent": v.get("fan_percent"),
                        "power_average_w": v.get("power_average_w"),
                    }
                    for uuid, v in per_gpu.items()
                }
                full = thermal_out.get("full") or {}
                summary["vmstat_delta"] = full.get("vmstat_delta")
                summary["tail_vmstat_delta"] = full.get("tail_vmstat_delta")

        if not reasons and summary["measured_rate"] is not None:
            summary["qualified"] = True
            summary["accepted_rate"] = summary["measured_rate"]
        else:
            summary["qualified"] = False
            summary["accepted_rate"] = None

    except InputError as e:
        reasons.append(f"input error: {e}")
        summary["qualified"] = False
        summary["accepted_rate"] = None
    except Exception as e:  # noqa: BLE001 - never crash the CLI
        reasons.append(f"unexpected error: {type(e).__name__}: {e}")
        summary["qualified"] = False
        summary["accepted_rate"] = None

    try:
        _atomic_write(trial_path / "summary.json", summary)
    except OSError as e:
        summary['qualified']=False;summary['accepted_rate']=None
        reasons.append('Could not persist summary: '+str(e))

    return summary


def _compact(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase": summary.get("phase"),
        "qualified": summary.get("qualified"),
        "reasons": summary.get("reasons"),
        "accepted_rate": summary.get("accepted_rate"),
        "measured_rate": summary.get("measured_rate"),
        "coverage_seconds": summary.get("coverage_seconds"),
        "per_gpu": summary.get("per_gpu"),
        "vmstat_delta": summary.get("vmstat_delta"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Native steady-state analysis (CPU-only).")
    parser.add_argument("trial_dir", help="Path to trial directory")
    parser.add_argument("--tail", type=int, default=180, help="Tail window seconds (default 180)")
    args = parser.parse_args(argv)

    summary = analyze_trial(args.trial_dir, tail_seconds=args.tail)
    print(json.dumps(_compact(summary), indent=2, sort_keys=True))
    return 0 if summary.get("qualified") else 1


if __name__ == "__main__":
    sys.exit(main())
