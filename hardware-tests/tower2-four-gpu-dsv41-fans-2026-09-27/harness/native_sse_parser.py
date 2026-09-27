"""Strict CPU parser/analyzer for native /generate SSE receipts.

Pure parsing/analysis. No hardware actuation, no cap/thermal claims.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple


class SSEError(ValueError):
    pass


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _finite_nonneg(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def _validate_finish(fr: Any, final_len: Optional[int]) -> Dict[str, Any]:
    if not isinstance(fr, dict):
        raise SSEError("finish_reason must be dict")
    ftype = fr.get("type")
    if ftype not in ("stop", "length"):
        raise SSEError(f"finish_reason.type invalid: {ftype!r}")
    if ftype == "length":
        ln = fr.get("length")
        if not _is_int(ln) or ln < 0:
            raise SSEError("length finish_reason requires genuine int length")
        if final_len is not None and ln != final_len:
            raise SSEError("length finish_reason does not match final output token count")
    return fr


def parse_sse(lines: Iterable[Tuple[float, bytes]]) -> Dict[str, Any]:
    """Parse a completed HTTP200 SSE stream.

    lines: iterable of (elapsed_seconds, raw_bytes_line).
    """
    events: List[Dict[str, Any]] = []
    final_ids: Optional[List[int]] = None
    final_text: Optional[str] = None
    finish_reason: Optional[Dict[str, Any]] = None
    final_meta: Optional[Dict[str, Any]] = None
    last_delivery_time: Optional[float] = None
    done_seen = False
    prev_time = -1.0
    prev_ids: Optional[List[int]] = None
    event_count = 0
    ids_seen = False

    for pair in lines:
        if not (isinstance(pair, tuple) and len(pair) == 2):
            raise SSEError("line entry must be (elapsed_seconds, bytes_line)")
        t, raw = pair
        if not _finite_nonneg(t):
            raise SSEError("elapsed must be finite nonnegative")
        if t < prev_time:
            raise SSEError("elapsed not monotonic")
        prev_time = t
        if not isinstance(raw, (bytes, bytearray)):
            raise SSEError("line must be bytes")
        try:
            s = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as e:
            raise SSEError(f"non-utf8 line: {e}") from e
        s = s.rstrip("\r\n")
        if s == "" or s.startswith(":"):
            continue
        if not s.startswith("data:"):
            raise SSEError(f"unexpected SSE line: {s!r}")
        payload = s[5:].lstrip(" ")
        if payload == "[DONE]":
            if done_seen:
                raise SSEError("duplicate [DONE]")
            done_seen = True
            continue
        if done_seen:
            raise SSEError("event after [DONE]")
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError as e:
            raise SSEError(f"malformed JSON: {e}") from e
        if not isinstance(obj, dict):
            raise SSEError("event must be JSON object")
        if "error" in obj:
            raise SSEError(f"server error key present: {obj.get('error')!r}")

        event_count += 1
        ev: Dict[str, Any] = {"t": float(t), "raw": obj}
        if "output_ids" not in obj and not ids_seen:
            raise SSEError("metadata-only event before output_ids")

        if "output_ids" in obj:
            ids = obj["output_ids"]
            if not isinstance(ids, list):
                raise SSEError("output_ids must be list")
            for v in ids:
                if not _is_int(v) or v < 0:
                    raise SSEError("output_ids must be genuine nonnegative ints")
            if prev_ids is not None:
                if len(ids) < len(prev_ids):
                    raise SSEError("output_ids count shrink")
                if ids[: len(prev_ids)] != prev_ids:
                    raise SSEError("output_ids prefix rewrite")
            grew = len(ids) > (len(prev_ids) if prev_ids is not None else 0)
            if grew and finish_reason is not None:
                raise SSEError("positive delivery after finish")
            prev_ids = list(ids)
            final_ids = list(ids)
            ids_seen = True
            ev["output_ids"] = list(ids)
            if grew:
                last_delivery_time = float(t)

        if "text" in obj:
            if not isinstance(obj["text"], str):
                raise SSEError("text must be string")
            final_text = obj["text"]
            ev["text"] = obj["text"]

        if "meta_info" in obj:
            mi = obj["meta_info"]
            if not isinstance(mi, dict):
                raise SSEError("meta_info must be object")
            ev["meta_info"] = mi
            final_meta = mi
            for k in ("prompt_tokens", "completion_tokens", "cached_tokens"):
                if k in mi and mi[k] is not None:
                    if not _is_int(mi[k]) or mi[k] < 0:
                        raise SSEError(f"meta_info.{k} must be nonnegative int")
            if mi.get("cached_tokens") is not None and mi.get("prompt_tokens") is not None:
                if mi["cached_tokens"] > mi["prompt_tokens"]:
                    raise SSEError("cached_tokens exceeds prompt_tokens")
            if mi.get("completion_tokens") is not None and final_ids is not None:
                if mi["completion_tokens"] != len(final_ids):
                    raise SSEError("completion_tokens != cumulative output_ids count")
            fr_nested = mi.get("finish_reason")
            if fr_nested is not None:
                checked = _validate_finish(fr_nested, len(final_ids) if final_ids is not None else None)
                if finish_reason is not None and checked != finish_reason:
                    raise SSEError("finish_reason changed")
                finish_reason = checked
                ev["finish_reason"] = finish_reason

        if "finish_reason" in obj and obj["finish_reason"] is not None:
            raise SSEError("native finish_reason must be nested in meta_info")

        events.append(ev)

    if not done_seen:
        raise SSEError("missing [DONE]")
    if not ids_seen or final_ids is None:
        raise SSEError("missing output_ids")
    if finish_reason is None:
        raise SSEError("missing finish_reason")
    if finish_reason["type"] == "length" and finish_reason["length"] != len(final_ids):
        raise SSEError("length finish_reason does not match final output token count")
    if final_meta is None:
        raise SSEError("missing final meta_info")
    if final_meta.get("finish_reason") != finish_reason:
        raise SSEError("final metadata lost finish evidence")
    pt = final_meta.get("prompt_tokens")
    ct = final_meta.get("completion_tokens")
    if not _is_int(pt) or pt < 0:
        raise SSEError("final meta_info.prompt_tokens required genuine int")
    if not _is_int(ct) or ct < 0:
        raise SSEError("final meta_info.completion_tokens required genuine int")
    if ct != len(final_ids):
        raise SSEError("final completion_tokens != final output_ids count")
    cached = final_meta.get("cached_tokens")
    if cached is not None:
        if not _is_int(cached) or cached < 0 or cached > pt:
            raise SSEError("cached_tokens must be genuine int in [0, prompt_tokens]")

    return {
        "events": events,
        "final_output_ids": final_ids,
        "final_text": final_text,
        "finish_reason": finish_reason,
        "final_meta_info": final_meta,
        "last_delivery_time": last_delivery_time,
        "done_seen": True,
        "event_count": event_count,
    }


def _first_positive_emission(rec: Dict[str, Any]) -> Optional[float]:
    prev = 0
    for ev in rec["events"]:
        ids = ev.get("output_ids")
        if ids is None:
            continue
        if len(ids) > prev:
            return ev["t"]
        prev = len(ids)
    return None


def _last_positive_delta(rec: Dict[str, Any]) -> Optional[float]:
    prev = 0
    last: Optional[float] = None
    for ev in rec["events"]:
        ids = ev.get("output_ids")
        if ids is None:
            continue
        if len(ids) > prev:
            last = ev["t"]
        prev = len(ids)
    return last


def _tokens_after(rec: Dict[str, Any], begin: float, end: float) -> int:
    prev = 0
    total = 0
    for ev in rec["events"]:
        ids = ev.get("output_ids")
        if ids is None:
            continue
        n = len(ids)
        if n > prev:
            delta = n - prev
            if ev["t"] > begin and ev["t"] <= end:
                total += delta
        prev = n
    return total


def _revalidate(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Re-run strict parser over reconstructed lines to prevent bypass."""
    lines: List[Tuple[float, bytes]] = []
    for ev in rec.get("events", []):
        if not isinstance(ev, dict) or "t" not in ev or "raw" not in ev:
            raise SSEError("event missing t/raw")
        t = ev["t"]
        if not _finite_nonneg(t):
            raise SSEError("event t invalid")
        raw = ev["raw"]
        if not isinstance(raw, dict):
            raise SSEError("event raw must be dict")
        lines.append((float(t), ("data:" + json.dumps(raw)).encode("utf-8")))
    lines.append((lines[-1][0] if lines else 0.0, b"data: [DONE]"))
    parsed = parse_sse(lines)
    for name in ("final_output_ids", "finish_reason", "final_meta_info", "last_delivery_time"):
        if rec.get(name) != parsed[name]:
            raise SSEError("record disagrees with validated events: " + name)
    return parsed


def analyze(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze completed parsed records. Returns honest status + metrics."""
    out: Dict[str, Any] = {
        "status": "ok",
        "reason": None,
        "per_stream": [],
        "aggregate_tokens": None,
        "shared_duration": None,
        "aggregate_rate": None,
        "fresh_cache_split": "unknown",
        "cache_split": None,
    }

    if not records:
        out["status"] = "failed"
        out["reason"] = "no records"
        return out

    validated: List[Dict[str, Any]] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            out["status"] = "failed"
            out["reason"] = f"record {i} malformed"
            return out
        if rec.get("done_seen") is not True:
            out["status"] = "failed"
            out["reason"] = f"record {i} missing done_seen"
            return out
        try:
            revalidated = _revalidate(rec)
        except (SSEError, TypeError, KeyError, ValueError) as e:
            out["status"] = "failed"
            out["reason"] = f"record {i} revalidation failed: {e}"
            return out
        validated.append(revalidated)

    for i, rec in enumerate(validated):
        ids = rec["final_output_ids"]
        if not ids:
            out["status"] = "no_output"
            out["reason"] = f"record {i} empty final output"
            return out

    firsts: List[float] = []
    lasts: List[float] = []
    for i, rec in enumerate(validated):
        f = _first_positive_emission(rec)
        l = _last_positive_delta(rec)
        if f is None or l is None:
            out["status"] = "failed"
            out["reason"] = f"record {i} has no positive emission"
            return out
        firsts.append(f)
        lasts.append(l)

    begin = max(firsts)
    end = min(lasts)
    if end <= begin:
        out["status"] = "no_overlap"
        out["reason"] = "no common positive-delivery interval"
        return out
    duration = end - begin
    if duration < 2.0:
        out["status"] = "short"
        out["reason"] = f"shared window {duration:.3f}s < 2s"
        return out

    per_stream = []
    total_tokens = 0
    for i, rec in enumerate(validated):
        toks = _tokens_after(rec, begin, end)
        rate = toks / duration
        per_stream.append({"index": i, "tokens": toks, "rate": rate})
        total_tokens += toks

    out["per_stream"] = per_stream
    out["aggregate_tokens"] = total_tokens
    out["shared_duration"] = duration
    out["aggregate_rate"] = total_tokens / duration

    cache_known = True
    cache_records = []
    for rec in validated:
        mi = rec["final_meta_info"]
        pt = mi["prompt_tokens"]
        ct = mi["completion_tokens"]
        cached = mi.get("cached_tokens")
        if cached is None:
            cache_known = False
            cache_records.append({
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cached_tokens": None,
                "uncached_prompt_tokens": None,
            })
        else:
            cache_records.append({
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cached_tokens": cached,
                "uncached_prompt_tokens": pt - cached,
            })
    out["cache_split"] = cache_records
    if not cache_known:
        out["fresh_cache_split"] = "unknown"
    elif any(r["cached_tokens"] > 0 for r in cache_records):
        out["fresh_cache_split"] = "partial_cache"
    else:
        out["fresh_cache_split"] = "all_fresh"

    return out
