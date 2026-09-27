#!/usr/bin/env python3
"""bench_dashboard_v2 — superset of bench_dashboard.py for the MMBT autopilot.

Preserves the original/enriched dashboard verbatim: same color grid (tasks x reps
per arm), same baseline-delta / sparkline / events enrichments, and ALL original
flags (--watch, --html, --no-color, --oneline, --no-events, --no-sparkline). It
reads the SAME /tmp/bench-autopilot/status.json + per-cell grade.json — and never
edits them. Three new read-only analysis flags are added:

  --json   : compact machine-readable status dump to stdout (pct, per-arm
             per-task pass/done, current cell, fails) — derived from grade.json so
             it works even against the original (un-enriched) status.json schema.

  --trend  : per task, the pass-RATE across cumulative rep windows it can compute
             from grade.json (v1-3, v1-5, v1-10, v1-20) per arm. Reveals where a
             small-N read was misleading (e.g. no-think p3_market drifting as N grows).

  --flips  : per-task 'flip map' marking cells whose verdict differs from that
             task/arm's MODAL verdict — surfacing high-variance cells.

All three degrade gracefully on sparse/missing data (no status.json, no grade.json,
partial windows) and each exits rc=0. New flags are mutually independent and additive;
existing CLI behavior is untouched.

Usage:
  python3 bench_dashboard_v2.py                 # one-shot terminal render (unchanged)
  python3 bench_dashboard_v2.py --json
  python3 bench_dashboard_v2.py --trend
  python3 bench_dashboard_v2.py --flips
"""
from __future__ import annotations
import argparse, json, os, time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOGS = REPO / "logs"
STATE = Path("/tmp/bench-autopilot")
STATUS = STATE / "status.json"
LOG = STATE / "autopilot.log"

# Glob that matches a cell dir for any model arm/rep. A dedicated campaign
# checkout keeps this generic scan isolated from unrelated historical logs.
CELL_GLOB = "p[1-3]_*_v*"

# N=10 no-think baseline pass counts per task (totals to 82/120).
BASELINE_N10_NOTHINK = {
    "p1_bugfix": 10, "p1_testwrite": 0, "p1_refactor": 0,
    "p2_extract": 10, "p2_ci": 10, "p2_hallucination": 10, "p2_triage": 10,
    "p3_doc": 9, "p3_business": 10, "p3_market": 8, "p3_writing": 0, "p3_pm": 5,
}
BASELINE_N10_TOTAL_PASS = 82
BASELINE_N10_TOTAL_CELLS = 120
BASELINE_ARM_HINT = "nothink"

# Cumulative rep windows for --trend (clamped to target_n at render time).
TREND_WINDOWS = (3, 5, 10, 20)

C = {"reset":"\033[0m","grn":"\033[42m\033[30m","red":"\033[41m\033[37m",
     "yel":"\033[43m\033[30m","blu":"\033[44m\033[37m","gry":"\033[100m\033[37m",
     "b":"\033[1m","dim":"\033[2m","cyan":"\033[96m","fg_grn":"\033[92m",
     "fg_red":"\033[91m","fg_yel":"\033[93m"}

STATUS_TASKS = []


# ---------------------------------------------------------------------------
# small helpers (all defensive — return safe defaults rather than raising)
# ---------------------------------------------------------------------------
def _g(d, key, default=None):
    """Dict-get that tolerates non-dicts."""
    if isinstance(d, dict):
        return d.get(key, default)
    return default


def raw_verdict(run):
    """Raw grade.json verdict string for a cell, or None if not graded/absent."""
    g = LOGS / run / "grade.json"
    try:
        if g.exists():
            return json.loads(g.read_text()).get("verdict")
    except Exception:
        return None
    return None


def is_pass(v):
    """True iff a raw verdict string counts as a pass."""
    return v in ("PASS", "STRUCTURAL_PASS")


def verdict(run):
    g = LOGS / run / "grade.json"
    s = LOGS / run / "summary.json"
    try:
        if g.exists():
            try:
                v = json.loads(g.read_text()).get("verdict")
                if v in ("PASS","STRUCTURAL_PASS"): return "pass"
                if v in (None,"BAD_GRADE","GRADER_FAILED","MISSING_OUTPUT"): return "err"
                return "fail"
            except Exception: return "err"
        if s.exists(): return "ungraded"
        if (LOGS / run / "transcript.jsonl").exists(): return "running"
    except Exception:
        return "pending"
    return "pending"


CELL = {"pass":("grn","✓"),"fail":("red","✗"),"err":("yel","!"),
        "ungraded":("blu","·"),"running":("cyan","▶"),"pending":("gry"," ")}


def render_grid(arm, target, color=True):
    label = _g(arm, "label", "?"); tasks = _g(arm, "pertask", {}) or {}
    lines = []
    head = "  " + "".join(f"{v:>3}" for v in range(1,target+1))
    lines.append(f"{C['b'] if color else ''}{label}{C['reset'] if color else ''}   {C['dim'] if color else ''}{head}{C['reset'] if color else ''}")
    for t in STATUS_TASKS:
        row = f"{t:<17}"
        for v in range(1,target+1):
            st = verdict(f"{t}_{label}_v{v}")
            ck, ch = CELL[st]
            if color:
                row += f" {C[ck]}{ch}{C['reset']} "
            else:
                row += f" {ch} "
        pt = tasks.get(t,{}) if isinstance(tasks, dict) else {}
        row += f"  {_g(pt,'pass','?')}/{_g(pt,'done','?')}"
        if BASELINE_ARM_HINT in str(label):
            base = BASELINE_N10_NOTHINK.get(t)
            if base is not None and isinstance(pt, dict) and isinstance(pt.get("pass"), int):
                d = pt["pass"] - base
                sign = "+" if d > 0 else ("" if d == 0 else "")
                col = (C['fg_grn'] if d > 0 else C['fg_red'] if d < 0 else C['dim']) if color else ""
                rs = C['reset'] if color else ""
                row += f"  {col}{sign}{d:>+d} vs {base}/10{rs}"
        lines.append(row)
    return "\n".join(lines)


def _cell_summaries():
    try:
        sums = list(LOGS.glob(f"{CELL_GLOB}/summary.json"))
        sums.sort(key=lambda p: p.stat().st_mtime)
        return sums
    except Exception:
        return []


def human_eta(status):
    try:
        done = _g(status, "grand_done", 0) or 0
        total = _g(status, "grand_total", 0) or 0
        rem = total - done
        sums = _cell_summaries()[-9:]
        if len(sums) >= 2:
            span = sums[-1].stat().st_mtime - sums[0].stat().st_mtime
            per = span / (len(sums)-1)
            if per <= 0:
                return "n/a"
            secs = int(rem * per)
            h, m = secs//3600, (secs%3600)//60
            return f"~{h}h{m:02d}m (≈{per/60:.1f}min/cell over last {len(sums)} cells)"
    except Exception:
        pass
    return "n/a"


# ---------------------------------------------------------------------------
# enrichment #3 — completion sparkline over time (from summary.json mtimes)
# ---------------------------------------------------------------------------
SPARK = "▁▂▃▄▅▆▇█"

def completion_sparkline(buckets=24, window_secs=None):
    try:
        sums = _cell_summaries()
        if len(sums) < 2:
            return None, 0
        mts = [p.stat().st_mtime for p in sums]
        t0, t1 = mts[0], mts[-1]
        if window_secs:
            t0 = max(t0, t1 - window_secs)
            mts = [m for m in mts if m >= t0]
            if len(mts) < 2:
                return None, 0
        span = max(t1 - t0, 1e-6)
        counts = [0] * buckets
        for m in mts:
            idx = min(buckets - 1, int((m - t0) / span * buckets))
            counts[idx] += 1
        peak = max(counts) or 1
        spark = "".join(SPARK[min(len(SPARK)-1, int(c / peak * (len(SPARK)-1)))] for c in counts)
        mins = int(span / 60)
        return f"{spark}  ({len(mts)} cells over ~{mins}m, peak {peak}/bin)", len(mts)
    except Exception:
        return None, 0


# ---------------------------------------------------------------------------
# enrichment #4 — recent-events feed (tail of autopilot.log)
# ---------------------------------------------------------------------------
def recent_events(n=8):
    try:
        if not LOG.exists():
            return []
        data = LOG.read_text(errors="replace").splitlines()
        return data[-n:]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# enrichment #2 — per-arm pass-rate vs baseline (summary line)
# ---------------------------------------------------------------------------
def arm_baseline_line(arm, color=True):
    label = _g(arm, "label", "?")
    pertask = _g(arm, "pertask", {}) or {}
    if not isinstance(pertask, dict):
        return None
    if BASELINE_ARM_HINT not in str(label):
        return None
    cur_pass = sum(_g(p, "pass", 0) or 0 for p in pertask.values() if isinstance(p, dict))
    cur_done = sum(_g(p, "done", 0) or 0 for p in pertask.values() if isinstance(p, dict))
    if cur_done == 0:
        return None
    cur_rate = cur_pass / cur_done
    base_rate = BASELINE_N10_TOTAL_PASS / BASELINE_N10_TOTAL_CELLS
    d = (cur_rate - base_rate) * 100
    col = (C['fg_grn'] if d >= 0 else C['fg_red']) if color else ""
    rs = C['reset'] if color else ""
    return (f"    {label} pass-rate: {cur_pass}/{cur_done} = {cur_rate*100:.1f}%   "
            f"baseline N=10 {BASELINE_N10_TOTAL_PASS}/{BASELINE_N10_TOTAL_CELLS} = {base_rate*100:.1f}%   "
            f"{col}Δ {d:+.1f}pp{rs}")


# ---------------------------------------------------------------------------
# enrichment #1 — oneline
# ---------------------------------------------------------------------------
def oneline(status, color=True):
    if status is None:
        return "bench: no status.json yet (autopilot not started?)"
    pct = _g(status, "pct", "?")
    gd = _g(status, "grand_done", "?"); gt = _g(status, "grand_total", "?")
    cur = _g(status, "current", {}) or {}
    up = _g(status, "endpoint_up", None)
    phase = _g(status, "phase", "?")
    if color:
        ep = (C['fg_grn']+"UP"+C['reset']) if up else (C['fg_red']+"DOWN"+C['reset'] if up is not None else "?")
    else:
        ep = "UP" if up else ("DOWN" if up is not None else "?")
    eta = human_eta(status)
    cell = _g(cur, "cell", "-") or "-"
    return (f"MMBT {phase} {pct}% [{gd}/{gt}]  ep={ep}  "
            f"cur={cell} iter={_g(cur,'iter','-')} frozen={_g(cur,'frozen_secs','-')}s  ETA {eta}")


# ---------------------------------------------------------------------------
# full terminal render
# ---------------------------------------------------------------------------
def render(status, color=True, show_events=True, show_spark=True):
    global STATUS_TASKS
    if status is None:
        return "no status yet (autopilot not started?)"
    STATUS_TASKS = _g(status, "tasks", []) or []
    L = []
    rs = C["reset"] if color else ""
    bar_w = 40
    pct = _g(status, "pct", 0) or 0
    filled = int(bar_w * pct/100)
    bar = "█"*filled + "░"*(bar_w-filled)
    up = _g(status, "endpoint_up", None)
    hp = "UP" if up else ("DOWN" if up is not None else "?")
    hcol = C["grn"] if (up and color) else (C["red"] if (up is not None and color) else "")
    L.append(f"{C['b'] if color else ''}MMBT bench autopilot — N={_g(status,'target_n','?')} — {_g(status,'phase','?')}{rs}")
    L.append(f"  {bar} {pct}%  ({_g(status,'grand_done','?')}/{_g(status,'grand_total','?')} cells)")
    cur = _g(status, "current", {}) or {}
    L.append(f"  endpoint: {hcol}{hp}{rs}   current: {C['cyan'] if color else ''}{_g(cur,'cell','-')}{rs} iter={_g(cur,'iter','-')} frozen={_g(cur,'frozen_secs','-')}s")
    L.append(f"  ETA: {human_eta(status)}   updated: {_g(status,'updated','?')}")
    if show_spark:
        spark, _ = completion_sparkline()
        if spark:
            L.append(f"  pace: {C['cyan'] if color else ''}{spark}{rs}")
    L.append("")
    arms = _g(status, "arms", []) or []
    for arm in arms:
        L.append(render_grid(arm, _g(status,'target_n',0) or 0, color))
        pertask = _g(arm, "pertask", {}) or {}
        subtotal = sum(_g(p,'pass',0) or 0 for p in pertask.values() if isinstance(p, dict))
        L.append(f"    {_g(arm,'label','?')} subtotal: {subtotal}/{_g(arm,'done','?')} pass  ({_g(arm,'done','?')}/{_g(arm,'total','?')} cells)")
        bl = arm_baseline_line(arm, color)
        if bl:
            L.append(bl)
        L.append("")
    if color:
        L.append(f"  legend: {C['grn']}✓{rs}pass {C['red']}✗{rs}fail {C['yel']}!{rs}grader {C['blu']}·{rs}ungraded {C['cyan']}▶{rs}running {C['gry']} {rs}pending")
    if show_events:
        ev = recent_events(8)
        if ev:
            L.append("")
            L.append(f"  {C['b'] if color else ''}recent events{rs} ({LOG}):")
            for line in ev:
                L.append(f"  {C['dim'] if color else ''}{line}{rs}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# HTML render (unchanged from enriched dashboard)
# ---------------------------------------------------------------------------
def to_html(status):
    if status is None:
        return ("<!doctype html><meta http-equiv=refresh content=15>"
                "<body style='background:#111;color:#ddd;font-family:system-ui'>"
                "<h2>MMBT bench autopilot</h2><p>no status.json yet "
                "(autopilot not started?)</p></body>")
    tasks_local = _g(status, "tasks", []) or []
    target_n = _g(status, "target_n", 0) or 0
    hc = {"pass":"#1a7f37","fail":"#b91c1c","err":"#b8860b","ungraded":"#1f5fbf","running":"#0aa","pending":"#444"}
    rows = []
    for arm in (_g(status, "arms", []) or []):
        label = _g(arm, "label", "?")
        pertask = _g(arm, "pertask", {}) or {}
        subtotal = sum(_g(p,'pass',0) or 0 for p in pertask.values() if isinstance(p, dict))
        bl = arm_baseline_line(arm, color=False)
        bl_html = f"<div style='color:#9cf;font:12px monospace'>{bl.strip()}</div>" if bl else ""
        rows.append(f"<h3>{label} — {subtotal}/{_g(arm,'done','?')} pass ({_g(arm,'done','?')}/{_g(arm,'total','?')})</h3>{bl_html}<table style='border-collapse:collapse'>")
        hdr = "<tr><th></th>" + "".join(f"<th style='font:11px monospace;color:#888'>{v}</th>" for v in range(1,target_n+1)) + "<th>p/d</th><th>Δ</th></tr>"
        rows.append(hdr)
        for t in tasks_local:
            cells = ""
            for v in range(1,target_n+1):
                st = verdict(f"{t}_{label}_v{v}")
                cells += f"<td title='{t}_v{v}:{st}' style='width:16px;height:16px;background:{hc[st]}'></td>"
            pt = pertask.get(t,{}) if isinstance(pertask, dict) else {}
            delta = ""
            if BASELINE_ARM_HINT in str(label):
                base = BASELINE_N10_NOTHINK.get(t)
                if base is not None and isinstance(_g(pt,"pass"), int):
                    d = pt["pass"] - base
                    dcol = "#5fd35f" if d > 0 else "#e06666" if d < 0 else "#888"
                    delta = f"<span style='color:{dcol}'>{d:+d} vs {base}/10</span>"
            rows.append(f"<tr><td style='font:12px monospace;padding-right:6px'>{t}</td>{cells}<td style='font:11px monospace;color:#aaa'>{_g(pt,'pass','?')}/{_g(pt,'done','?')}</td><td style='font:11px monospace'>{delta}</td></tr>")
        rows.append("</table>")
    spark, _ = completion_sparkline()
    spark_html = f"<p style='font:14px monospace;color:#9cf'>pace: {spark}</p>" if spark else ""
    ev = recent_events(8)
    ev_html = ""
    if ev:
        body = "<br>".join(_html_escape(x) for x in ev)
        ev_html = f"<h3>recent events</h3><pre style='background:#000;color:#9c9;padding:8px;font:12px monospace;white-space:pre-wrap'>{body}</pre>"
    cur = _g(status, "current", {}) or {}
    return f"""<!doctype html><meta http-equiv=refresh content=30><body style='background:#111;color:#ddd;font-family:system-ui'>
<h2>MMBT bench autopilot — N={target_n} — {_g(status,'phase','?')} — {_g(status,'pct','?')}%</h2>
<p>{_g(status,'grand_done','?')}/{_g(status,'grand_total','?')} cells · endpoint {'UP' if _g(status,'endpoint_up') else 'DOWN'} · current {_g(cur,'cell','-')} iter {_g(cur,'iter','-')} · updated {_g(status,'updated','?')}</p>
{spark_html}
{''.join(rows)}
<p style='color:#888'>green=pass red=fail yellow=grader-issue blue=ungraded teal=running grey=pending</p>
{ev_html}
</body>"""


def _html_escape(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))


# ---------------------------------------------------------------------------
# NEW: shared introspection over the live status (degrades to grade.json scan)
# ---------------------------------------------------------------------------
def status_tasks(status):
    """Ordered task list — from status.json if present, else the known TASKS order."""
    t = _g(status, "tasks", None)
    if isinstance(t, list) and t:
        return t
    return ["p1_bugfix","p1_testwrite","p1_refactor","p2_extract","p2_ci",
            "p2_hallucination","p2_triage","p3_doc","p3_business","p3_market",
            "p3_writing","p3_pm"]


def status_arms(status):
    """List of arm labels — from status.json arms if present, else the canonical two."""
    arms = _g(status, "arms", None)
    if isinstance(arms, list) and arms:
        labels = [_g(a, "label") for a in arms if _g(a, "label")]
        if labels:
            return labels
    return ["397b-nothink", "397b-think"]


def cell_verdicts(task, label, upto):
    """Ordered list of raw verdicts for v1..upto (None where ungraded/absent)."""
    return [raw_verdict(f"{task}_{label}_v{v}") for v in range(1, upto + 1)]


# ---------------------------------------------------------------------------
# NEW flag: --json  (compact machine-readable dump)
# ---------------------------------------------------------------------------
def json_dump(status):
    """Compact, derived-from-grade.json status. Works on the original schema."""
    tasks = status_tasks(status)
    arms = status_arms(status)
    target = int(_g(status, "target_n", 0) or 0)
    out = {
        "pct": _g(status, "pct"),
        "phase": _g(status, "phase"),
        "target_n": target or None,
        "grand_done": _g(status, "grand_done"),
        "grand_total": _g(status, "grand_total"),
        "endpoint_up": _g(status, "endpoint_up"),
        "updated": _g(status, "updated"),
        "current": _g(status, "current", {}) or {},
        "arms": {},
        "fails": [],
    }
    scan_n = target or 20
    for label in arms:
        per = {}
        for t in tasks:
            vs = cell_verdicts(t, label, scan_n)
            graded = [v for v in vs if v is not None]
            passes = sum(1 for v in graded if is_pass(v))
            per[t] = {"pass": passes, "done": len(graded)}
            for idx, vv in enumerate(vs, start=1):
                if vv is not None and not is_pass(vv):
                    out["fails"].append(f"{t}_{label}_v{idx}")
        out["arms"][label] = per
    return json.dumps(out, separators=(",", ":"), sort_keys=False)


# ---------------------------------------------------------------------------
# NEW flag: --trend  (cumulative-window pass-rate per task/arm)
# ---------------------------------------------------------------------------
def trend_table(status, color=True):
    tasks = status_tasks(status)
    arms = status_arms(status)
    target = int(_g(status, "target_n", 0) or 0) or 20
    windows = [w for w in TREND_WINDOWS if w <= max(target, max(TREND_WINDOWS))]
    # clamp display windows to target but always keep at least the smallest
    windows = [w for w in TREND_WINDOWS if w <= target] or [min(TREND_WINDOWS)]
    rs = C["reset"] if color else ""
    L = []
    L.append(f"{C['b'] if color else ''}TREND — cumulative pass-rate per task across rep windows{rs}")
    L.append(f"{C['dim'] if color else ''}  cell = passes/graded (rate%); '-' = no graded reps in window. "
             f"watch a rate that drifts as N grows (small-N was misleading).{rs}")
    for label in arms:
        L.append("")
        head = f"{label:<20}" + "".join(f"{('v1-'+str(w)):>12}" for w in windows)
        L.append(f"{C['cyan'] if color else ''}{head}{rs}")
        for t in tasks:
            vs_full = cell_verdicts(t, label, max(windows))
            row = f"{t:<20}"
            rates = []
            for w in windows:
                window = vs_full[:w]
                graded = [v for v in window if v is not None]
                if not graded:
                    cell = "-"
                    rates.append(None)
                else:
                    p = sum(1 for v in graded if is_pass(v))
                    rate = 100.0 * p / len(graded)
                    rates.append(rate)
                    cell = f"{p}/{len(graded)} {rate:.0f}%"
                # color: drift from the first computable window
                col = ""
                if color and rates[-1] is not None:
                    first = next((r for r in rates if r is not None), None)
                    if first is not None:
                        drift = rates[-1] - first
                        if drift <= -15:   col = C['fg_red']
                        elif drift >= 15:  col = C['fg_grn']
                        else:              col = ""
                row += f"{col}{cell:>12}{rs if col else ''}"
            L.append(row)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# NEW flag: --flips  (cells differing from the task/arm modal verdict)
# ---------------------------------------------------------------------------
def flips_map(status, color=True):
    tasks = status_tasks(status)
    arms = status_arms(status)
    target = int(_g(status, "target_n", 0) or 0) or 20
    rs = C["reset"] if color else ""
    L = []
    L.append(f"{C['b'] if color else ''}FLIPS — cells whose verdict differs from the task/arm modal verdict{rs}")
    L.append(f"{C['dim'] if color else ''}  '.' = matches mode  'X' = flipped  ' ' = ungraded. "
             f"trailing count = #flips/#graded (mode shown). High flips = high-variance cell.{rs}")
    for label in arms:
        L.append("")
        head = "  " + "".join(f"{v:>3}" for v in range(1, target + 1))
        L.append(f"{C['cyan'] if color else ''}{label:<18}{head}{rs}")
        for t in tasks:
            vs = cell_verdicts(t, label, target)
            graded = [v for v in vs if v is not None]
            if not graded:
                L.append(f"{t:<18}" + "   ·" * 0 + f"  {C['dim'] if color else ''}(no graded reps){rs}")
                continue
            mode_v, _ = Counter(graded).most_common(1)[0]
            mode_short = _short_verdict(mode_v)
            row = f"{t:<18}"
            flips = 0
            for v in vs:
                if v is None:
                    row += "   "  # ungraded
                elif v == mode_v:
                    row += f" {C['dim'] if color else ''}.{rs} "
                else:
                    flips += 1
                    row += f" {C['fg_red'] if color else ''}X{rs if color else ''} "
            row += f"  {flips}/{len(graded)} flips (mode={mode_short})"
            L.append(row)
    return "\n".join(L)


def _short_verdict(v):
    return {
        "PASS": "P", "STRUCTURAL_PASS": "SP",
        "FAIL": "F", "STRUCTURAL_FAIL": "SF",
        "BAD_GRADE": "BG", "GRADER_FAILED": "GF", "MISSING_OUTPUT": "MO",
    }.get(v, str(v)[:6] if v else "?")


# ---------------------------------------------------------------------------
def load_status():
    """Load status.json, tolerating missing/partial/corrupt files. Returns dict or None."""
    try:
        if not STATUS.exists():
            return None
        txt = STATUS.read_text()
        if not txt.strip():
            return None
        return json.loads(txt)
    except Exception:
        return None


def main():
    global LOGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--html", default=None)
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--oneline", action="store_true", help="single compact status line")
    ap.add_argument("--no-events", action="store_true", help="hide the recent-events feed")
    ap.add_argument("--no-sparkline", action="store_true", help="hide the completion sparkline")
    # NEW analysis flags (read-only; all degrade gracefully + exit rc=0)
    ap.add_argument("--json", action="store_true",
                    help="compact machine-readable status to stdout (derived from grade.json)")
    ap.add_argument("--trend", action="store_true",
                    help="per-task cumulative-window pass-rate table (v1-3/5/10/20) per arm")
    ap.add_argument("--flips", action="store_true",
                    help="per-task flip map: cells differing from the task/arm modal verdict")
    ap.add_argument("--logs", default=str(LOGS),
                    help="per-cell logs directory (default: logs in this checkout)")
    args = ap.parse_args()
    LOGS = Path(os.path.expanduser(args.logs)).resolve()

    def once():
        status = load_status()  # None if missing/partial — every renderer handles None
        if args.json:
            print(json_dump(status if status is not None else {}))
            return
        if args.trend:
            print(trend_table(status if status is not None else {}, color=not args.no_color))
            return
        if args.flips:
            print(flips_map(status if status is not None else {}, color=not args.no_color))
            return
        if args.oneline:
            print(oneline(status, color=not args.no_color))
            return
        if args.html:
            try:
                Path(args.html).write_text(to_html(status))
                print(f"wrote {args.html}")
            except Exception as e:
                print(f"failed to write {args.html}: {e}")
            return
        out = render(status, color=not args.no_color,
                     show_events=not args.no_events, show_spark=not args.no_sparkline)
        if args.watch:
            os.system("clear")
        print(out)

    if args.watch:
        while True:
            try:
                once()
            except Exception as e:
                print(f"[dashboard] transient render error: {e}")
            time.sleep(15)
    else:
        once()


if __name__ == "__main__":
    main()
