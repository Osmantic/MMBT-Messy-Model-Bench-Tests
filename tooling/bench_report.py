#!/usr/bin/env python3
"""bench_report — standalone MMBT findings-markdown generator.

Reads <checkout>/logs/<task>_<label>_v<N>/{grade.json,summary.json} for two arms
selected by --config/--arm up to --n (default 20) and emits a complete MMBT
findings markdown to stdout (or --out FILE). It does NOT touch the live run's
status.json, the autopilot, or the dashboard — it only reads the per-cell logs,
so it is safe to run against a run in progress (partial data is fine; missing
cells render as blanks / "-").

Sections emitted (matching the style of
hardware-tests/qwen3.5-397b-vs-step3.7-flash-2026-05-29/findings.md):

  1. Scorecard table — 12 tasks x
       [no-think x/N, think x/N, Step low/med/high, 27B ref, Coder ref] + totals.
  2. "What N reveals" — per-task pass-rate stability across the
       v1-3 / v1-5 / v1-10 / v1-20 windows, flagging cells whose small-N verdict
       (pass-by-majority) FLIPPED relative to the full --n window.
  3. Think-vs-no-think redistribution — per-task pass-count delta (think - nothink).
  4. Runaway / stall summary — per-arm count of cells by summary.json finish_reason.

Usage:
  python3 bench_report.py                 # N=20, markdown to stdout
  python3 bench_report.py --n 10
  python3 bench_report.py --out /tmp/findings.md
  python3 bench_report.py --logs ~/bench/logs --n 20
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOGS = REPO / "logs"

# Canonical task order (matches autopilot / dashboard).
TASKS = ["p1_bugfix", "p1_testwrite", "p1_refactor", "p2_extract", "p2_ci",
         "p2_hallucination", "p2_triage", "p3_doc", "p3_business", "p3_market",
         "p3_writing", "p3_pm"]

# The two live arms. label -> column header.
ARMS = [("397b-nothink", "397B no-think"), ("397b-think", "397B think")]
NOTHINK_LABEL = "397b-nothink"
THINK_LABEL = "397b-think"
MODEL_NAME = "Qwen3.5-397B-A17B (GGUF, llama.cpp)"
SETUP_MODEL = ("Qwen3.5-397B-A17B, unsloth UD-Q3_K_XL GGUF (5 shards), "
               "2x RTX PRO 6000 Blackwell, llama.cpp")

PASS_VERDICTS = ("PASS", "STRUCTURAL_PASS")

# Stability windows for the "what N reveals" section.
WINDOWS = [3, 5, 10, 20]


def configure_campaign(*, config=None, arm_specs=None, model_name=None):
    """Configure report labels without changing historical CLI defaults."""
    global ARMS, NOTHINK_LABEL, THINK_LABEL, MODEL_NAME, SETUP_MODEL
    arm_specs = list(arm_specs or [])
    payload = None
    if config:
        payload = json.loads(Path(config).read_text())
        if not arm_specs:
            for arm in payload.get("arms", []):
                arm_specs.append({
                    "label": arm["label"],
                    "pretty": arm.get("pretty") or arm["label"],
                    "thinking": arm.get("thinking"),
                })
        model_name = model_name or payload.get("model")
    normalized = []
    for arm in arm_specs:
        if isinstance(arm, str):
            label, sep, pretty = arm.partition("=")
            arm = {"label": label, "pretty": pretty if sep else label, "thinking": None}
        normalized.append(arm)
    if normalized:
        if len(normalized) != 2:
            raise ValueError("bench_report requires exactly two think/no-think arms")
        nothink = next((arm for arm in normalized if arm.get("thinking") == "off"), None)
        think = next((arm for arm in normalized if arm.get("thinking") == "on"), None)
        nothink = nothink or next((arm for arm in normalized if "nothink" in arm["label"]), None)
        think = think or next((arm for arm in normalized
                               if "think" in arm["label"] and "nothink" not in arm["label"]), None)
        if nothink is None or think is None:
            raise ValueError("could not identify thinking=off/on arms from config or labels")
        NOTHINK_LABEL, THINK_LABEL = nothink["label"], think["label"]
        ARMS = [(NOTHINK_LABEL, nothink.get("pretty") or NOTHINK_LABEL),
                (THINK_LABEL, think.get("pretty") or THINK_LABEL)]
    if model_name:
        MODEL_NAME = model_name
        SETUP_MODEL = model_name
    return {"model": MODEL_NAME, "arms": ARMS}

# ---------------------------------------------------------------------------
# Static reference columns (carried from the published N=3 entry; these are the
# cross-model comparators, not re-derived from logs). Kept here so the doc is
# self-contained and the columns line up with the scorecard. Update if the
# reference entry is regraded (see tracking issue #29 in the N=3 findings).
# ---------------------------------------------------------------------------
STEP_REF = {  # task -> "low/med/high" glyphs
    "p1_bugfix": "✓/✓/✓", "p1_testwrite": "✗/✗/✗", "p1_refactor": "✓/✗/✗",
    "p2_extract": "✓/✓/✓", "p2_ci": "✓/✓/✓", "p2_hallucination": "✓/✓/✓",
    "p2_triage": "~/✓/✓", "p3_doc": "~/✓/✓", "p3_business": "✓/~/✗",
    "p3_market": "✗/✓/✓", "p3_writing": "✗/~/✗", "p3_pm": "✗/~/✓",
}
REF_27B = {  # task -> "x/3"
    "p1_bugfix": "3/3", "p1_testwrite": "0/3", "p1_refactor": "0/3",
    "p2_extract": "3/3", "p2_ci": "3/3", "p2_hallucination": "3/3",
    "p2_triage": "3/3", "p3_doc": "0/3", "p3_business": "2/3",
    "p3_market": "3/3", "p3_writing": "0/3", "p3_pm": "0/3",
}
REF_CODER = {  # task -> "x/3"
    "p1_bugfix": "2/3", "p1_testwrite": "0/3", "p1_refactor": "0/3",
    "p2_extract": "3/3", "p2_ci": "3/3", "p2_hallucination": "1/3",
    "p2_triage": "3/3", "p3_doc": "2/3", "p3_business": "3/3",
    "p3_market": "0/3", "p3_writing": "2/3", "p3_pm": "1/3",
}


# ---------------------------------------------------------------------------
# Per-cell readers (all defensive — return None / safe defaults on any error).
# ---------------------------------------------------------------------------
def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def cell_verdict(logs: Path, run: str):
    """Return 'pass' / 'fail' / None(=no grade yet) for a cell."""
    g = _read_json(logs / run / "grade.json")
    if not isinstance(g, dict):
        return None
    v = g.get("verdict")
    if v in PASS_VERDICTS:
        return "pass"
    if v is None:
        return None
    return "fail"


def cell_finish_reason(logs: Path, run: str):
    s = _read_json(logs / run / "summary.json")
    if isinstance(s, dict):
        return s.get("finish_reason")
    return None


def cell_finished(logs: Path, run: str) -> bool:
    """True if the harness considers the cell finished (summary.json present).
    This mirrors the autopilot's notion of a completed cell. A cell can be
    finished but not yet graded (no grade.json) — that gap is exactly where the
    autopilot scorecard (denominator = finished cells) and this report
    (denominator = graded cells) diverge, so we surface it as a footnote."""
    return (logs / run / "summary.json").exists()


def done_but_ungraded(logs: Path, label: str, n: int):
    """Run-names that are finished (summary.json) but have no grade.json yet,
    over all tasks v1..n for an arm. Empty at a clean COMPLETE run."""
    out = []
    for t in TASKS:
        for v in range(1, n + 1):
            run = f"{t}_{label}_v{v}"
            if cell_finished(logs, run) and cell_verdict(logs, run) is None:
                out.append(run)
    return out


def arm_task_cells(logs: Path, task: str, label: str, n: int):
    """List of (v, verdict) for v in 1..n where a grade.json exists. verdict in
    {'pass','fail'}; cells without a grade are skipped (treated as not-yet-run)."""
    out = []
    for v in range(1, n + 1):
        verdict = cell_verdict(logs, f"{task}_{label}_v{v}")
        if verdict is not None:
            out.append((v, verdict))
    return out


def passes_done(cells):
    """(#pass, #graded) for a list of (v, verdict)."""
    done = len(cells)
    passes = sum(1 for _, vd in cells if vd == "pass")
    return passes, done


def majority_pass(cells):
    """Majority verdict over graded cells: True if >50% pass, False if <50%,
    None on an exact tie or no data. Used for window-flip detection."""
    passes, done = passes_done(cells)
    if done == 0:
        return None
    if passes * 2 > done:
        return True
    if passes * 2 < done:
        return False
    return None  # exact tie — genuinely ambiguous


# ---------------------------------------------------------------------------
# Section 1 — scorecard
# ---------------------------------------------------------------------------
def section_scorecard(logs: Path, n: int):
    L = []
    nothink_pretty = dict(ARMS)[NOTHINK_LABEL]
    think_pretty = dict(ARMS)[THINK_LABEL]
    L.append(f"## Scorecard (N={n}, pass count per cell)")
    L.append("")
    L.append(f"| task | {nothink_pretty} | {think_pretty} | Step low/med/high | 27B (ref) | Coder (ref) |")
    L.append("|---|:--:|:--:|:--:|:--:|:--:|")
    tot = {NOTHINK_LABEL: [0, 0], THINK_LABEL: [0, 0]}
    for t in TASKS:
        nt = passes_done(arm_task_cells(logs, t, NOTHINK_LABEL, n))
        th = passes_done(arm_task_cells(logs, t, THINK_LABEL, n))
        tot[NOTHINK_LABEL][0] += nt[0]; tot[NOTHINK_LABEL][1] += nt[1]
        tot[THINK_LABEL][0] += th[0]; tot[THINK_LABEL][1] += th[1]
        nt_s = f"{nt[0]}/{nt[1]}" if nt[1] else "—"
        th_s = f"{th[0]}/{th[1]}" if th[1] else "—"
        L.append(f"| {t} | {nt_s} | {th_s} | {STEP_REF.get(t,'—')} "
                 f"| {REF_27B.get(t,'—')} | {REF_CODER.get(t,'—')} |")
    ntT = tot[NOTHINK_LABEL]; thT = tot[THINK_LABEL]
    L.append(f"| **Total** | **{ntT[0]}/{ntT[1]}** | **{thT[0]}/{thT[1]}** "
             f"| **7 / 8 / 8** | ~7/12 | ~7/12 |")
    L.append("")
    L.append("Pass = grade.json `verdict` of PASS or STRUCTURAL_PASS. Cells with no grade.json yet "
             "are excluded from the denominator (shown as `x/done`, not `x/N`); an em-dash means no "
             "graded replicate exists for that cell. Step/27B/Coder columns are the published "
             "comparators carried from the N=3 entry (see tracking issue #29 — phase-1 reference cells "
             "may be provisional).")
    # Reconciliation guard: surface finished-but-ungraded cells. These are the
    # exact cells where this report's denominator (graded) differs from the
    # autopilot --publish scorecard's denominator (finished). At a clean COMPLETE
    # run there should be none; if any appear in an auto-published artifact it
    # means grading lagged or partially failed and the two scorecards will not
    # agree on x/N — worth a human look before trusting the totals.
    ungraded = []
    for label in (NOTHINK_LABEL, THINK_LABEL):
        ungraded += done_but_ungraded(logs, label, n)
    if ungraded:
        L.append("")
        L.append(f"> ⚠️ **{len(ungraded)} finished-but-ungraded cell(s)** (summary.json present, no "
                 "grade.json): " + ", ".join(f"`{r}`" for r in ungraded[:30]) +
                 (" …" if len(ungraded) > 30 else "") +
                 ". These are EXCLUDED from the pass denominators above but ARE counted (as non-pass) "
                 "by the autopilot `--publish` scorecard's denominator — so the two artifacts will "
                 "disagree on `x/N` until grading completes. Expected to be empty on a clean COMPLETE "
                 "run; if present in a published doc, regrade before trusting the totals.")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Section 2 — what N reveals (stability across windows + flip flags)
# ---------------------------------------------------------------------------
def _window_cell(cells_all, w):
    """Restrict a precomputed (v,verdict) list to v<=w and format 'p/d'."""
    cells = [(v, vd) for (v, vd) in cells_all if v <= w]
    p, d = passes_done(cells)
    return f"{p}/{d}" if d else "·", majority_pass(cells)


def section_what_n_reveals(logs: Path, n: int):
    windows = [w for w in WINDOWS if w <= n] or [n]
    if n not in windows:
        windows.append(n)
    windows = sorted(set(windows))
    L = []
    L.append("## What N reveals — pass-rate stability across replicates")
    L.append("")
    L.append("Per task, the pass count over the first v1–3 / v1–5 / v1–10 / v1–" + str(n) +
             " replicates of each arm. A **⚑ flip** marks a cell whose small-N *majority verdict* "
             "(>50% pass) disagrees with its full-N=" + str(n) + " majority verdict — i.e. a small-N "
             "read that would have been overturned. `·` = no graded replicate in that window; a tie "
             "(exactly 50%) is treated as no-call and never flagged as a flip.")
    L.append("")
    hdr = "| task | arm | " + " | ".join(f"v1–{w}" for w in windows) + " | flip? |"
    L.append(hdr)
    L.append("|---|---|" + "|".join([":--:"] * len(windows)) + "|:--:|")
    flips = []
    for t in TASKS:
        for label, pretty in ARMS:
            cells_all = arm_task_cells(logs, t, label, n)
            full_majority = majority_pass(cells_all)
            cols = []
            small_flip = False
            for w in windows:
                cell_str, maj = _window_cell(cells_all, w)
                cols.append(cell_str)
                # a flip = a SMALLER window than n that has a definite majority
                # opposite to the full-n majority.
                if (w < n and maj is not None and full_majority is not None
                        and maj != full_majority):
                    small_flip = True
            flag = "⚑" if small_flip else ""
            if small_flip:
                flips.append((t, pretty))
            L.append(f"| {t} | {pretty} | " + " | ".join(cols) + f" | {flag} |")
    L.append("")
    if flips:
        names = ", ".join(f"{t} ({a})" for t, a in flips)
        L.append(f"**Flipped cells** ({len(flips)}): {names}. These are exactly the cells where a "
                 "small-N verdict would have been luck — trust the high-N read and treat them as "
                 "high-variance.")
    else:
        L.append("**No flips detected** in the available data — every cell's small-N majority verdict "
                 "agrees with its full-N read (or there is not yet enough data to tell).")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Section 3 — think vs no-think redistribution
# ---------------------------------------------------------------------------
def _pass_rate(cells):
    """(rate in [0,1] or None, #pass, #done) for a (v,verdict) list."""
    p, d = passes_done(cells)
    return (p / d if d else None, p, d)


def section_redistribution(logs: Path, n: int):
    L = []
    L.append("## Thinking vs no-think — per-task redistribution")
    L.append("")
    L.append("Pass-rate delta (think − no-think) per task. To stay honest while the arms are at "
             "different depths, each task's delta is computed on its **common window** — the first "
             "`k = min(no-think graded, think graded)` replicates of *both* arms — and also reported "
             "as a pass-count delta scaled to that common k. A net-zero aggregate can still hide real "
             "per-task swings; this surfaces *where* reasoning moves success.")
    L.append("")
    L.append("| task | k | no-think (≤k) | think (≤k) | Δ rate (pp) | Δ count |")
    L.append("|---|:--:|:--:|:--:|:--:|:--:|")
    helped = hurt = 0
    sum_dcount = 0.0
    for t in TASKS:
        nt_all = arm_task_cells(logs, t, NOTHINK_LABEL, n)
        th_all = arm_task_cells(logs, t, THINK_LABEL, n)
        k = min(len(nt_all), len(th_all))
        if k == 0:
            L.append(f"| {t} | 0 | — | — | — | — |")
            continue
        nt_k = nt_all[:k]
        th_k = th_all[:k]
        ntr, ntp, _ = _pass_rate(nt_k)
        thr, thp, _ = _pass_rate(th_k)
        d_rate = (thr - ntr) * 100
        d_count = thp - ntp  # both over k cells -> directly comparable
        sum_dcount += d_count
        if d_count > 0:
            helped += 1; dc = f"**+{d_count}**"
        elif d_count < 0:
            hurt += 1; dc = f"**{d_count}**"
        else:
            dc = "0"
        L.append(f"| {t} | {k} | {ntp}/{k} | {thp}/{k} | {d_rate:+.0f} | {dc} |")
    L.append("")
    L.append(f"On matched common windows, thinking **helps {helped}** task(s) and **hurts {hurt}** "
             f"(net {sum_dcount:+.0f} passes over matched cells). Read the per-task Δ, not a single "
             "aggregate — the interesting signal is the redistribution. (Raw per-arm totals at the "
             "current — possibly unequal — depths are in the scorecard above.)")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Section 4 — runaway / stall summary (finish_reason counts per arm)
# ---------------------------------------------------------------------------
def section_finish_reasons(logs: Path, n: int):
    L = []
    L.append("## Runaway / stall summary (finish_reason per arm)")
    L.append("")
    L.append("Count of completed cells by `summary.json` `finish_reason`, per arm, over v1–" +
             str(n) + ". `done_signal` = clean agent-declared completion. `model_stopped` = the model "
             "ended the turn without signalling done. `*_runaway` / `max_*` = over-generation. "
             "`stuck_*` = spinning without workspace progress until the stuck threshold. Anything that "
             "is not `done_signal` is a non-clean exit worth a look.")
    L.append("")
    # collect the union of finish_reasons across both arms
    per_arm = {}
    all_reasons = set()
    for label, pretty in ARMS:
        counts = {}
        n_cells = 0
        for t in TASKS:
            for v in range(1, n + 1):
                run = f"{t}_{label}_v{v}"
                # only count cells that have actually finished (summary.json present)
                fr = cell_finish_reason(logs, run)
                if fr is None and not (logs / run / "summary.json").exists():
                    continue
                fr = fr or "unknown"
                counts[fr] = counts.get(fr, 0) + 1
                all_reasons.add(fr)
                n_cells += 1
        per_arm[label] = (counts, n_cells)
    # order: done_signal first, then alphabetical
    ordered = (["done_signal"] if "done_signal" in all_reasons else []) + \
              sorted(r for r in all_reasons if r != "done_signal")
    L.append("| arm | cells | " + " | ".join(ordered) + " | non-clean |")
    L.append("|---|:--:|" + "|".join([":--:"] * len(ordered)) + "|:--:|")
    for label, pretty in ARMS:
        counts, n_cells = per_arm[label]
        cols = [str(counts.get(r, 0)) for r in ordered]
        nonclean = sum(c for r, c in counts.items() if r != "done_signal")
        L.append(f"| {pretty} | {n_cells} | " + " | ".join(cols) +
                 f" | {nonclean} |")
    L.append("")
    # narrative: list the actual non-clean cells (most useful for triage)
    bad = []
    for label, pretty in ARMS:
        for t in TASKS:
            for v in range(1, n + 1):
                run = f"{t}_{label}_v{v}"
                fr = cell_finish_reason(logs, run)
                if fr and fr != "done_signal":
                    bad.append(f"`{run}` ({fr})")
    if bad:
        L.append("**Non-clean exits:** " + "; ".join(bad) + ".")
    else:
        L.append("**No non-clean exits** in the available data — every finished cell exited "
                 "`done_signal`.")
    return "\n".join(L)


# ---------------------------------------------------------------------------
def build_report(logs: Path, n: int):
    parts = []
    parts.append(f"# {MODEL_NAME} — microbench N={n}, "
                 f"two arms (think / no-think)")
    parts.append("")
    parts.append(f"**N={n}** scorecard, replicate-stability analysis, think-vs-no-think "
                 "redistribution, and finish-reason audit — auto-generated by "
                 "`tooling/bench_report.py` from the per-cell `grade.json` / `summary.json` logs. "
                 "Partial data is rendered as-is (denominators reflect graded replicates, not the "
                 "target N).")
    parts.append("")
    parts.append("## Setup")
    parts.append(f"- **Model:** {SETUP_MODEL}. Exact model/runtime hashes and lane topology are "
                 "recorded in each run's serving manifest.")
    parts.append("- **Two arms:** `enable_thinking` off (no-think) and on (think).")
    parts.append("- **Comparators:** Step-3.7-Flash-NVFP4 low/med/high, and the published 27B / "
                 "Coder reference columns (carried from the N=3 entry).")
    parts.append("")
    parts.append(section_scorecard(logs, n))
    parts.append("")
    parts.append(section_what_n_reveals(logs, n))
    parts.append("")
    parts.append(section_redistribution(logs, n))
    parts.append("")
    parts.append(section_finish_reasons(logs, n))
    parts.append("")
    parts.append("---")
    parts.append("Generated by `tooling/bench_report.py` (read-only; does not touch the live "
                 "autopilot status.json or dashboard).")
    parts.append("")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description="MMBT findings-markdown generator (read-only).")
    ap.add_argument("--n", type=int, default=20, help="target N (max replicate per cell); default 20")
    ap.add_argument("--logs", default=str(DEFAULT_LOGS),
                    help="bench logs dir (default: logs in this checkout)")
    ap.add_argument("--config", default=None,
                    help="campaign JSON supplying model and exactly two arm labels")
    ap.add_argument("--arm", action="append", default=[], metavar="LABEL=PRETTY",
                    help="explicit arm label/title; pass exactly twice when --config is omitted")
    ap.add_argument("--model-name", default=None,
                    help="report display name; overrides the config model")
    ap.add_argument("--out", default=None, help="write markdown to FILE instead of stdout")
    args = ap.parse_args()
    try:
        configure_campaign(config=args.config, arm_specs=args.arm,
                           model_name=args.model_name)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"error: invalid campaign configuration: {exc}", file=sys.stderr)
        sys.exit(2)
    logs = Path(os.path.expanduser(args.logs))
    if not logs.exists():
        print(f"error: logs dir not found: {logs}", file=sys.stderr)
        sys.exit(2)
    md = build_report(logs, args.n)
    if args.out:
        Path(args.out).write_text(md)
        print(f"wrote {args.out} ({len(md)} bytes)")
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
