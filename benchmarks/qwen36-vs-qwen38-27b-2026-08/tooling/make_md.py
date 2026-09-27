#!/usr/bin/env python3
"""Render /home/michael/pr-staging/results-tables.md from results.json."""
import json
from collections import OrderedDict

R = json.load(open("/home/michael/pr-staging/results.json"))
OUT = "/home/michael/pr-staging/results-tables.md"
L = []
def w(s=""): L.append(s)

def pct(p, nd=1):
    return "n/a" if p is None else ("%." + str(nd) + "f%%") % (100 * p)

def ci(lo, hi, nd=1):
    if lo is None or hi is None: return "n/a"
    return ("[%." + str(nd) + "f, %." + str(nd) + "f]") % (100 * lo, 100 * hi)

def pp(d, nd=1):
    return "n/a" if d is None else ("%+." + str(nd) + "f pp") % (100 * d)

def pv(p):
    if p is None: return "n/a"
    if p < 1e-4: return "%.1e" % p
    if p < 0.001: return "%.5f" % p
    return "%.4g" % p

def sig(p):
    if p is None: return ""
    return " **\\***" if p < 0.05 else ""

def num(v, nd=0):
    if v is None: return "n/a"
    return ("{:,." + str(nd) + "f}").format(v)

G = R["groups"]
C = R["comparisons"]

# ============================================================ header
w("# Qwen3.6-27B vs Qwen3.8-27B — Definitive Results Tables")
w()
w("All numbers below are computed from the frozen dataset")
w("`%s` (%d cells, frozen %s)." % (R["provenance"]["source_csv"], R["provenance"]["n_cells"],
                                   R["provenance"]["frozen_at"]))
w("No live re-scan was used for any figure. Model, quantization and sampler identity are taken")
w("verbatim from the frozen CSV, which sourced them from each run's `receipt.json` — never from")
w("directory names.")
w()
w("**Reproduce:** `python3 mmbt_results.py` writes `results.json`; `python3 make_md.py` renders")
w("this file; `python3 test_stats.py` validates the estimators. No third-party dependencies.")
w()
w("### Reading these tables")
w()
w("- **Sign convention.** Every delta in this document is arithmetically **3.8 minus 3.6**,")
w("  applied identically to every table. Note that this means the *direction of badness flips")
w("  with the metric*: for good-direction metrics (terminal rate, pass rate) a **negative** delta")
w("  means 3.8 is worse, while for bad-direction metrics (ungraded rate, loop rate) a")
w("  **positive** delta means 3.8 is worse. Each table states which metric it reports.")
w("- **Every rate carries its denominator** as `x/n`.")
w("- **CIs** are Wilson 95% score intervals for single proportions and Newcombe 95% hybrid-score")
w("  intervals for differences. `p` is a two-sided Fisher exact test. All three are implemented")
w("  from scratch in pure python; formulas are in the appendix and in the source comments.")
w("- **\\*** marks `p < 0.05`. No multiplicity correction is applied — with %d comparison" % len(C))
w("  families and 7 scorings each, treat isolated marginal results with suspicion.")
w("- `passed == 1` means verdict in {PASS, STRUCTURAL_PASS}. **Every ungraded cell has")
w("  `passed == 0`**, so an all-cells pass rate silently merges \"graded and failed\" with")
w("  \"never produced a gradeable artifact\". Both components are reported separately.")
w()

# ============================================================ 0. inventory
w("---")
w()
w("## Headline")
w()
p1l = C["P1"]["delivery"]["loop_freq30"]; p2l = C["P2"]["delivery"]["loop_freq30"]
p1a = C["P1"]["quality"]["pass_all"]; p1g = C["P1"]["quality"]["pass_graded"]
w("**1. The one large, unambiguous effect is a delivery regression in no-think mode, not a")
w("quality regression.** 3.8's loop rate is %s (%s) at the matched sampler and %s (%s) at each"
  % (pp(p1l["diff"]), pv(p1l["fisher_p"]), pp(p2l["diff"]), pv(p2l["fisher_p"])))
w("model's own vendor sampler. This is measured upstream of grading, so no scoring choice, and")
w("none of the three grader defects, can touch it.")
w()
w("**2. That regression disappears in thinking mode.** Loop rate falls to %d/%d (T0.3) and %d/%d"
  % (G["B38"]["loop_freq30"]["x"], G["B38"]["n"], G["C38"]["loop_freq30"]["x"], G["C38"]["n"]))
w("(T1/p0.95/pp0) for 3.8, neither distinguishable from 3.6.")
w()
w("**3. Conditional on delivering, 3.8 is not clearly worse at the matched no-think sampler.**")
_flip = " — the sign flips" if (p1a["diff"] or 0) < 0 < (p1g["diff"] or 0) else \
        (" — the gap collapses" if abs(p1g["diff"] or 0) < abs(p1a["diff"] or 0) / 2 else "")
w("All-cells pass rate is %s (%s) but graded-only is %s (%s)%s. \"3.8 is worse at the task\""
  % (pp(p1a["diff"]), pv(p1a["fisher_p"]), pp(p1g["diff"]), pv(p1g["fisher_p"]), _flip))
w("is **not** a supportable summary of this corpus; \"3.8 fails more often by not finishing\" is.")
w()
w("**4. Thinking mode costs ~2.2–3.0× more tokens on 3.8 with no pass-rate gain**, and 3.8's")
w("effort ladder buys tokens rather than quality (no effort step is significant).")
w()
_q = R["quant_control"]
w("**5. Two things reported here are provisional at best and are labelled as such:** the Q8_0")
w("quantization arm (%d of %d cells graded at freeze #2 — enough for provisional loop and"
  % (_q["n_graded"], _q["pass_all"]["n"]))
w("graded-outcome rates with wide intervals, not enough for any quality verdict, §6) and every")
w("`best_of_n` / `first_replicate` row (n = 12, §9).")
w()
w("Full robustness accounting is in §7; what the data cannot support is in §9.")
w()
w("---")
w()
w("## 0. Group inventory and missing-data structure")
w()
w("| Group | Definition | Cells | Families | Graded | Graded+failed | Ungraded (looped) | Ungraded (no loop) | Graded despite loop |")
w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
for gid, g in G.items():
    m = g["missing"]
    w("| `%s` | %s | %d | %d | %d | %d | %d | %d | %d |" % (
        gid, g["label"], g["n"], g["families"], g["n_graded"],
        m["graded_fail"], m["ungraded_looped"], m["ungraded_not_looped"], m["graded_but_looped"]))
w()
w("Notes on group composition, which matter for how much weight each comparison can carry:")
w()
for gid, g in G.items():
    w("- **`%s`** — %s. *%s*  Arms pooled: %s." % (
        gid, g["label"], g["note"], ", ".join("`%s`" % a for a in g["arms"])))
w()
w("All %d runs used **seed 42**. Replicates are therefore repeated runs at a *fixed* seed, not"
  % R["provenance"]["n_cells"])
w("a seed sweep; within-arm variation reflects server/batching nondeterminism, not sampled seeds.")
w("This limits how far replicate counts can be read as independent draws.")
w()

# ============================================================ 1. delivery
w("---")
w()
w("## 1. Delivery reliability")
w()
_ln = R["provenance"]["loop_nesting_counts"]
w("Loop detection is reported under both available metrics. `looped_run30` is strictly nested")
w("inside `looped_freq30` across the whole corpus (%d cells flagged by both, %d by frequency"
  % (_ln["both"], _ln["freq_only"]))
w("only, %d by run only), so `freq30` is the more inclusive detector and `run30` the stricter one."
  % _ln["run_only"])
w()
w("### 1a. Per-group delivery rates (Wilson 95% CI)")
w()
w("| Group | n | Terminal | Ungraded | Loop (freq30) | Loop (run30) |")
w("|---|---:|---|---|---|---|")
for gid, g in G.items():
    w("| `%s` | %d | %s %s | %s %s | %s %s | %s %s |" % (
        gid, g["n"],
        "%d/%d %s" % (g["terminal"]["x"], g["terminal"]["n"], pct(g["terminal"]["p"])),
        ci(g["terminal"]["lo"], g["terminal"]["hi"]),
        "%d/%d %s" % (g["ungraded"]["x"], g["ungraded"]["n"], pct(g["ungraded"]["p"])),
        ci(g["ungraded"]["lo"], g["ungraded"]["hi"]),
        "%d/%d %s" % (g["loop_freq30"]["x"], g["loop_freq30"]["n"], pct(g["loop_freq30"]["p"])),
        ci(g["loop_freq30"]["lo"], g["loop_freq30"]["hi"]),
        "%d/%d %s" % (g["loop_run30"]["x"], g["loop_run30"]["n"], pct(g["loop_run30"]["p"])),
        ci(g["loop_run30"]["lo"], g["loop_run30"]["hi"])))
w()
w("### 1b. Paired 3.6-vs-3.8 delivery contrasts")
w()
for pid, c in C.items():
    w("**%s — %s**" % (pid, c["description"]))
    w()
    w("| Metric | 3.6 `%s` | 3.8 `%s` | Δ (3.8−3.6) | Newcombe 95%% CI | Fisher p |" % tuple(c["pair"]))
    w("|---|---|---|---:|---|---:|")
    for k, lab in [("terminal", "Terminal"), ("ungraded", "Ungraded"),
                   ("loop_freq30", "Loop (freq30)"), ("loop_run30", "Loop (run30)")]:
        v = c["delivery"][k]
        w("| %s | %d/%d %s %s | %d/%d %s %s | %s | %s | %s%s |" % (
            lab, v["a"]["x"], v["a"]["n"], pct(v["a"]["p"]), ci(v["a"]["lo"], v["a"]["hi"]),
            v["b"]["x"], v["b"]["n"], pct(v["b"]["p"]), ci(v["b"]["lo"], v["b"]["hi"]),
            pp(v["diff"]), ci(v["diff_lo"], v["diff_hi"]), pv(v["fisher_p"]), sig(v["fisher_p"])))
    w()

# ============================================================ 2. quality
w("---")
w()
w("## 2. Quality")
w()
w("Two pass rates are reported for every pair because they answer different questions:")
w()
w("- **All-cells** (loops count as failure) — *how often does a run of this model produce a")
w("  passing deliverable?* This is the end-to-end number.")
w("- **Graded-only** — *given that a run produced something gradeable, how good was it?* This")
w("  discards every delivery failure and is maximally charitable to a model that fails by")
w("  not delivering.")
w()
w("Where these two disagree, the disagreement **is** the finding.")
w()
for pid, c in C.items():
    w("**%s — %s vs %s**" % (pid, c["label_a"], c["label_b"]))
    w()
    w("| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |")
    w("|---|---|---|---:|---|---:|")
    for k, lab in [("pass_all", "All cells (loops = fail)"), ("pass_graded", "Graded only")]:
        v = c["quality"][k]
        w("| %s | %d/%d %s %s | %d/%d %s %s | %s | %s | %s%s |" % (
            lab, v["a"]["x"], v["a"]["n"], pct(v["a"]["p"]), ci(v["a"]["lo"], v["a"]["hi"]),
            v["b"]["x"], v["b"]["n"], pct(v["b"]["p"]), ci(v["b"]["lo"], v["b"]["hi"]),
            pp(v["diff"]), ci(v["diff_lo"], v["diff_hi"]), pv(v["fisher_p"]), sig(v["fisher_p"])))
    w()

# ============================================================ 3. per-family
w("---")
w()
w("## 3. Per-family breakdown")
w()
w("All-cells pass rate (loops count as failure), with graded and loop counts so any cell can be")
w("re-derived. `g` = graded cells, `L` = cells flagged by `looped_freq30`.")
w()
for pid, c in C.items():
    w("### %s — %s vs %s" % (pid, c["label_a"], c["label_b"]))
    w()
    w("| Family | 3.6 pass/n (g, L) | 3.6 rate | 3.8 pass/n (g, L) | 3.8 rate | Δ (3.8−3.6) | Fisher p |")
    w("|---|---|---:|---|---:|---:|---:|")
    for f in c["family_breakdown"]:
        w("| `%s` | %d/%d (g=%d, L=%d) | %s | %d/%d (g=%d, L=%d) | %s | %s | %s%s |" % (
            f["family"], f["pass_a"], f["n_a"], f["graded_a"], f["loop_a"], pct(f["rate_a"]),
            f["pass_b"], f["n_b"], f["graded_b"], f["loop_b"], pct(f["rate_b"]),
            pp(f["delta"]), pv(f["fisher_p"]), sig(f["fisher_p"])))
    w()
    _fns = [f[k] for f in c["family_breakdown"] for k in ("n_a", "n_b") if f[k]]
    w("Per-family n is %d–%d per side, so **no single family row is individually conclusive**;"
      % (min(_fns), max(_fns)))
    w("they are provided so the pooled numbers can be audited, not to support family-level claims.")
    w()

# ============================================================ 4. cost
w("---")
w()
w("## 4. Cost, matched by family")
w()
w("**Why family matching is mandatory here.** Task families differ in cost by more than an order")
w("of magnitude (`p2_extract` ~2.5k tokens vs `p1_bugfix` ~35k). Two groups with different family")
w("mixes produce medians that can be ordered either way at will. Earlier in this project exactly")
w("that produced two contradictory cost claims from the same corpus. Every figure below is")
w("computed per family first.")
w()
w("**A second, subtler trap.** `completion_tokens` is missing for exactly the cells that were")
w("never graded, and looping is the dominant cause of that. Missingness is therefore *not*")
w("random — it is concentrated in the runs that would have been most expensive. A family is")
w("counted as **cost-comparable** only when both sides retain ≥3 cells with cost data *and*")
w("≥50% coverage of that side's cells in the family. Non-comparable families are shown but")
w("excluded from the summary ratio.")
w()
for pid, c in C.items():
    t = c["cost"]["tokens"]; e = c["cost"]["elapsed"]
    w("### %s — %s vs %s" % (pid, c["label_a"], c["label_b"]))
    w()
    w("Token-data coverage: 3.6 %s (%d/%d cells) · 3.8 %s (%d/%d cells). "
      "Cost-comparable families: **%d of %d**.%s" % (
        pct(t["coverage_a"], 0), t["with_data_a"], t["cells_a"],
        pct(t["coverage_b"], 0), t["with_data_b"], t["cells_b"],
        t["n_comparable_families"], t["n_families"],
        ("  Excluded: %s." % ", ".join("`%s`" % x for x in t["excluded_families"]))
        if t["excluded_families"] else ""))
    w()
    w("| Family | 3.6 med tok (n) | 3.8 med tok (n) | tok ratio | 3.6 med s | 3.8 med s | s ratio | comparable |")
    w("|---|---:|---:|---:|---:|---:|---:|:--:|")
    emap = {x["family"]: x for x in e["per_family"]}
    for a in t["per_family"]:
        b = emap[a["family"]]
        w("| `%s` | %s (%d) | %s (%d) | %s | %s (%d) | %s (%d) | %s | %s |" % (
            a["family"], num(a["median_a"]), a["n_a"], num(a["median_b"]), a["n_b"],
            ("%.2f" % a["ratio"]) if a["ratio"] else "n/a",
            num(b["median_a"], 1), b["n_a"], num(b["median_b"], 1), b["n_b"],
            ("%.2f" % b["ratio"]) if b["ratio"] else "n/a",
            "yes" if a["comparable"] else "**no**"))
    w()
    w("**Median of per-family ratios (comparable families only): tokens ×%s, wall-clock ×%s.**" % (
        ("%.2f" % t["median_of_family_ratios"]) if t["median_of_family_ratios"] else "n/a",
        ("%.2f" % e["median_of_family_ratios"]) if e["median_of_family_ratios"] else "n/a"))
    w()
    # Is the excluded set systematically more expensive than the retained set?
    # If so, the summary ratio is computed over the cheap tail and must say so.
    if t["excluded_families"]:
        inc = [x["median_a"] for x in t["per_family"] if x["comparable"] and x["median_a"]]
        exc = [x["median_a"] for x in t["per_family"] if not x["comparable"] and x["median_a"]]
        if inc and exc:
            mi = sorted(inc)[len(inc) // 2]
            me = sorted(exc)[len(exc) // 2]
            if me > mi:
                w("> ⚠️ **The excluded families are the expensive ones.** Median 3.6 cost is %s tokens"
                  % num(me))
                w("> across the excluded families versus %s across the retained ones (×%.1f). Because"
                  % (num(mi), me / mi))
                w("> cost data goes missing exactly when a run loops, and 3.8 loops most on the")
                w("> long-horizon families, the ×%s summary ratio above is computed over the *cheap*"
                  % ("%.2f" % t["median_of_family_ratios"]))
                w("> tail of the task set. **It must not be read as \"3.8 is cheaper overall\"** — the")
                w("> comparison is silent on precisely the families where 3.8's cost would be worst.")
                w()
    ta = c["cost"]["tokens_per_success_a"]; tb = c["cost"]["tokens_per_success_b"]
    w("| Tokens per successful deliverable | 3.6 | 3.8 |")
    w("|---|---:|---:|")
    w("| Total completion tokens recorded | %s | %s |" % (num(ta["total_tokens"]), num(tb["total_tokens"])))
    w("| Cells with token data | %d/%d | %d/%d |" % (
        ta["n_cells_with_tokens"], ta["n_cells"], tb["n_cells_with_tokens"], tb["n_cells"]))
    w("| Passing cells | %d | %d |" % (ta["passes"], tb["passes"]))
    w("| **Tokens per success** | **%s**%s | **%s**%s |" % (
        num(ta["tokens_per_success"]), " (lower bound)" if ta["is_lower_bound"] else "",
        num(tb["tokens_per_success"]), " (lower bound)" if tb["is_lower_bound"] else ""))
    w("| Tokens burned on cells that never got graded | %s | %s |" % (
        num(ta["tokens_on_ungraded"]), num(tb["tokens_on_ungraded"])))
    w()
    notes = [x for x in (ta["lower_bound_note"], tb["lower_bound_note"]) if x]
    if notes:
        for side, n_ in zip(("3.6", "3.8"), (ta["lower_bound_note"], tb["lower_bound_note"])):
            if n_:
                w("- %s: %s" % (side, n_))
        w()

# ============================================================ 5. effort
w("---")
w()
w("## 5. Effort ladder within 3.8 thinking")
w()
w("`effort` is populated **only** for 3.8 thinking cells; every 3.6 cell and every no-think cell")
w("has an empty effort field, so there is no 3.6 effort ladder to compare against. The ladder is")
w("broken out by sampler as well as pooled, because the two 3.8 thinking groups have very")
w("different effort mixes (T0.3: 14/24/13 low/med/xhigh; T1: 12/12/48) and pooling them")
w("confounds effort with sampler.")
w()
w("| Sampler | Effort | Cells | Families | Graded | Loops | Pass (all cells) | Wilson 95% CI | Pass (graded) | Median tokens | Median s |")
w("|---|---|---:|---:|---:|---:|---|---|---|---:|---:|")
for r in R["effort_ladder"]["rows"]:
    pa, pg = r["pass_all"], r["pass_graded"]
    w("| %s | %s | %d | %d | %d | %d | %d/%d %s | %s | %s | %s | %s |" % (
        r["regime"], r["effort"], r["n"], r["families"], r["n_graded"], r["loop_freq30"],
        pa["x"], pa["n"], pct(pa["p"]), ci(pa["lo"], pa["hi"]),
        ("%d/%d %s" % (pg["x"], pg["n"], pct(pg["p"]))) if pg["p"] is not None else "n/a",
        num(r["median_tokens"]), num(r["median_elapsed"], 1)))
w()
w("### Pairwise effort steps (Δ = higher effort − lower effort, all-cells pass rate)")
w()
w("| Sampler | Step | Lower | Higher | Δ | Newcombe 95% CI | Fisher p |")
w("|---|---|---|---|---:|---|---:|")
for p in R["effort_ladder"]["pairwise"]:
    w("| %s | %s → %s | %d/%d | %d/%d | %s | %s | %s%s |" % (
        p["regime"], p["lo"], p["hi"], p["a"]["x"], p["a"]["n"], p["b"]["x"], p["b"]["n"],
        pp(p["diff"]), ci(p["diff_lo"], p["diff_hi"]), pv(p["fisher_p"]), sig(p["fisher_p"])))
w()
# Recompute the prose numbers from the pairwise data rather than hardcoding
# them, so they can never drift from the table above.
_pw = R["effort_ladder"]["pairwise"]
_absd = [abs(100 * p["diff"]) for p in _pw]
_minp = min(p["fisher_p"] for p in _pw if p["fisher_p"] is not None)
w("**Not one effort step is statistically distinguishable** (every Fisher p ≥ %.3f; every"
  % _minp)
w("Newcombe CI straddles zero). Cell counts per rung are 12–48, which cannot resolve the")
w("%.1f–%.1f pp differences observed. The apparent non-monotonicity — `medium` scoring lowest at"
  % (min(_absd), max(_absd)))
w("both samplers — is **not** supported as a real effect and should not be reported as one.")
w()
_lrows = {(r["regime"], r["effort"]): r["median_tokens"] for r in R["effort_ladder"]["rows"]}
_t3lo, _t3xh = _lrows[("T0.3/p0.8/pp0", "low")], _lrows[("T0.3/p0.8/pp0", "xhigh")]
_t1lo, _t1xh = _lrows[("T1/p0.95/pp0", "low")], _lrows[("T1/p0.95/pp0", "xhigh")]
_ratios = sorted((_t3xh / _t3lo, _t1xh / _t1lo))
w("What the ladder *does* show cleanly is cost: median tokens rise roughly %.1f–%.1f× from `low`"
  % (_ratios[0], _ratios[1]))
w("to `xhigh` (T0.3: %s → %s; T1: %s → %s), with no accompanying pass-rate gain."
  % (num(_t3lo), num(_t3xh), num(_t1lo), num(_t1xh)))
w("On this corpus, raising 3.8's thinking effort buys tokens, not quality.")
w()

# ============================================================ 6. Q8
w("---")
w()
w("## 6. Q8_0 quantization control")
w()
Q = R["quant_control"]
w("%s" % Q["note"])
w()
w("> **What changed at freeze #2.** At freeze #1 this arm was 11 cells with zero graded and")
w("> carried no quality information at all. At freeze #2 it is %d cells with %d graded"
  % (Q["pass_all"]["n"], Q["n_graded"]))
w("> (%d PASS, %d FAIL), so it now supports **provisional rates with wide intervals** —"
  % (Q["n_pass_graded"], Q["n_fail_graded"]))
w("> loop rate %d/%d %s %s and graded-only pass rate %d/%d %s %s (Wilson 95%%)." % (
    Q["loop_freq30"]["x"], Q["loop_freq30"]["n"], pct(Q["loop_freq30"]["p"]),
    ci(Q["loop_freq30"]["lo"], Q["loop_freq30"]["hi"]),
    Q["pass_graded"]["x"], Q["pass_graded"]["n"], pct(Q["pass_graded"]["p"]),
    ci(Q["pass_graded"]["lo"], Q["pass_graded"]["hi"])))
w("> The loop interval excludes zero, so \"the no-think loop occurs at Q8_0 at a real,")
w("> non-negligible rate\" is now a provisional *rate* claim rather than an existence-only")
w("> observation. The quality numbers stay **descriptive only**: on n=%d graded cells no"
  % Q["n_graded"])
w("> pass-rate comparison against a Q4 arm can separate quantization from noise, and none is")
w("> asserted. %d of the %d cells ran to a terminal state and %d produced full token accounting."
  % (Q["n_terminal"], Q["pass_all"]["n"], Q["n_with_tokens"]))
w()
uq = Q.get("unscored_qualitative")
if uq:
    w("> **Unscored qualitative evidence, disclosed and excluded.** `%s`" % uq["cell"])
    w("> was quarantined in-flight at freeze #2 and is **not a row in the frozen CSV**: it was")
    w("> observed in a rewrite loop — %s." % uq["observation"])
    w("> This is a different failure shape from the identical-call loop that `looped_freq30` /")
    w("> `looped_run30` count, it is UNSCORED, and it is excluded from every rate and every")
    w("> denominator in this document. It is recorded because a second loop subclass at Q8_0 is")
    w("> qualitatively relevant to the quantization question even though it carries no")
    w("> statistical weight.")
    w()
qd = Q.get("post_freeze_drift")
if qd and qd["n_cells"]:
    p_fams = sorted(c["family"] for c in qd["cells"] if c["on_disk_verdict"] == "PASS")
    f_fams = sorted(c["family"] for c in qd["cells"] if c["on_disk_verdict"] == "FAIL")
    w("> **Post-freeze grading drift, disclosed.** %d of these %d cells carry a verdict on"
      % (qd["n_cells"], Q["pass_all"]["n"]))
    w("> disk that differs from the frozen CSV — %d PASS (%s) and %d FAIL (%s)," % (
        qd["n_pass"], ", ".join("`%s`" % f for f in p_fams),
        qd["n_fail"], ", ".join("`%s`" % f for f in f_fams)))
    w("> per the overlay manifest's `post_freeze_divergence` ledger. Those grades postdate the")
    w("> %s freeze and are **excluded from every number in this document**," % R["provenance"]["frozen_at"])
    w("> per the freeze discipline; they belong to the next freeze.")
    w()
w("Per-cell detail for all %d Q8_0 cells as of freeze #2:" % Q["pass_all"]["n"])
w()
w("| Family | Rep | Verdict | Graded | Terminal | Loop freq30 | Loop run30 | Tokens | Elapsed s |")
w("|---|---:|---|---:|---:|---:|---:|---:|---:|")
for r in Q["q8_cells"]:
    w("| `%s` | %s | %s | %d | %d | %d | %d | %s | %s |" % (
        r["family"], r.get("replicate", ""), r["verdict"] if r["verdict"] else "*(none)*",
        r["graded"], r["terminal"],
        r["loop_f"], r["loop_r"], num(r["tokens"]), num(r["elapsed"], 1)))
w()
w("Delivery and (provisionally) graded-only quality against Q4 arms restricted to the same")
w("%d families:" % len(Q["q8_families"]))
w()
for key, lab in [("vs_38_q4_same_sampler", "vs 3.8 Q4 (same sampler, same model — isolates quantization)"),
                 ("vs_36_q4_same_sampler", "vs 3.6 Q4 (same sampler, different model)")]:
    blk = Q[key]
    w("**%s**" % lab)
    w()
    w("| Metric | Q4 comparator | Q8_0 | Δ (Q8−Q4) | Newcombe 95% CI | Fisher p |")
    w("|---|---|---|---:|---|---:|")
    metric_rows = [("terminal", "Terminal"), ("loop_freq30", "Loop (freq30)"),
                   ("loop_run30", "Loop (run30)")]
    if "pass_graded" in blk:
        metric_rows.append(("pass_graded", "Pass, graded only (PROVISIONAL)"))
    for k, lb in metric_rows:
        v = blk[k]
        w("| %s | %d/%d %s | %d/%d %s | %s | %s | %s%s |" % (
            lb, v["a"]["x"], v["a"]["n"], pct(v["a"]["p"]), v["b"]["x"], v["b"]["n"], pct(v["b"]["p"]),
            pp(v["diff"]), ci(v["diff_lo"], v["diff_hi"]), pv(v["fisher_p"]), sig(v["fisher_p"])))
    t = blk["tokens"]
    w()
    # Most Q8 families carry only 1-2 replicates, so the >=3-cells-per-side
    # comparability rule of §4 is rarely met. Report the raw per-family pairs
    # instead, explicitly as description rather than inference.
    pairs = [x for x in t["per_family"] if x["ratio"]]
    if pairs:
        rs = sorted(x["ratio"] for x in pairs)
        med = rs[len(rs) // 2] if len(rs) % 2 else (rs[len(rs)//2-1] + rs[len(rs)//2]) / 2
        w("Token cost, descriptive only (Q8_0 carries 1–2 replicates per family, so the")
        w("≥3-cells-per-side comparability rule of §4 is generally not satisfied and no summary")
        w("ratio is claimed): %d families have data on both sides; median per-family token "
          "ratio Q8/Q4 = **×%.2f** (range ×%.2f–×%.2f)." % (len(pairs), med, min(rs), max(rs)))
        w()
    if key == "vs_36_q4_same_sampler":
        w("> **Any loop difference in this table is a model effect, not a quantization")
        w("> effect.** This row compares 3.8-Q8_0 against 3.6-Q4 — the models differ as well as the")
        w("> quantization — so it simply reproduces the no-think looping gap already established in")
        w("> §1. Only the preceding table (3.8-Q8_0 vs 3.8-Q4, same model and sampler) isolates")
        w("> quantization.")
        w()
w("With %d cells and 1–2 replicates per family, **every interval here still spans tens of"
  % Q["pass_all"]["n"])
w("percentage points**. What the arm now establishes: the identical-call loop occurs at Q8_0 at")
w("a rate whose Wilson interval excludes zero, so the loop is not an artifact of the UD-Q4_K_XL")
w("quantization. What it still cannot do: support any quality verdict, or attribute (or")
w("exonerate) the delivery regression as a quantization effect — there is still no matched 3.6")
w("Q8_0 arm, and the graded subset is n=%d. The graded outcomes above are published as data"
  % Q["n_graded"])
w("for the next freeze to build on, not as findings.")
w()

# ============================================================ 7. sensitivity
w("---")
w()
w("## 7. Sensitivity: does the 3.6-vs-3.8 delta survive rescoring?")
w()
w("Seven scorings per comparison. The first six are the requested set; `graded_only` is added")
w("because it is the natural upper bound on charity toward a model whose failures are delivery")
w("failures.")
w()
SENS_ORDER = ["loops_as_failure", "loops_excluded", "loops_half_credit", "graded_only",
              "best_of_n_per_family", "first_replicate_only", "depth_matched"]
first = C[list(C)[0]]["sensitivity"]
for k in SENS_ORDER:
    if k in first:
        w("- **`%s`** — %s" % (k, first[k]["definition"]))
w()
for pid, c in C.items():
    w("### %s — %s vs %s" % (pid, c["label_a"], c["label_b"]))
    w()
    w("| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | 95% CI on Δ | Fisher p |")
    w("|---|---|---|---:|---|---:|")
    for k in SENS_ORDER:
        v = c["sensitivity"].get(k)
        if not v: continue
        a, b = v["a"], v["b"]
        astr = ("%d/%d %s" % (a["x"], a["n"], pct(a["p"]))) if a.get("x") is not None \
               else ("mean %.3f (n=%d)" % (a["mean"], a["n"]))
        bstr = ("%d/%d %s" % (b["x"], b["n"], pct(b["p"]))) if b.get("x") is not None \
               else ("mean %.3f (n=%d)" % (b["mean"], b["n"]))
        w("| `%s` | %s | %s | %s | %s | %s%s |" % (
            k, astr, bstr, pp(v["diff"]), ci(v["diff_lo"], v["diff_hi"]),
            pv(v.get("fisher_p")), sig(v.get("fisher_p"))))
    w()
    ds = [c["sensitivity"][k]["diff"] for k in SENS_ORDER if k in c["sensitivity"]]
    ps = [c["sensitivity"][k].get("fisher_p") for k in SENS_ORDER if k in c["sensitivity"]]
    nsig = sum(1 for p in ps if p is not None and p < 0.05)
    ntest = sum(1 for p in ps if p is not None)
    neg = all(d < 0 for d in ds); pos = all(d > 0 for d in ds)
    w("Range of Δ across the seven scorings: **%s to %s**. Sign is %s. "
      "Significant in **%d of %d** scorings that admit a Fisher test." % (
        pp(min(ds)), pp(max(ds)),
        "consistently negative (3.8 worse)" if neg else
        ("consistently positive (3.8 better)" if pos else "**NOT consistent — it flips**"),
        nsig, ntest))
    w()
w("### What survives every scoring")
w()
w("Computed directly from the table above rather than asserted:")
w()
for pid, c in C.items():
    ds = [c["sensitivity"][k]["diff"] for k in SENS_ORDER if k in c["sensitivity"]]
    ps = [c["sensitivity"][k].get("fisher_p") for k in SENS_ORDER if k in c["sensitivity"]]
    nsig = sum(1 for p in ps if p is not None and p < 0.05)
    ntest = sum(1 for p in ps if p is not None)
    neg = all(d < 0 for d in ds); pos = all(d > 0 for d in ds)
    lf = c["delivery"]["loop_freq30"]
    if neg and nsig == ntest:
        verdict = ("**Robust.** 3.8 is worse under every scoring and the difference is "
                   "significant under all %d testable ones." % ntest)
    elif neg:
        verdict = ("**Directionally robust, not uniformly significant.** 3.8 is worse under all "
                   "seven scorings, significant in %d of %d." % (nsig, ntest))
    elif pos:
        verdict = ("**Directionally positive, not significant.** 3.8 is nominally better under "
                   "all seven scorings but significant in %d of %d." % (nsig, ntest))
    else:
        verdict = ("**Not robust — the sign flips with the scoring rule.** No quality claim in "
                   "either direction survives. Significant in %d of %d." % (nsig, ntest))
    w("- **%s** (%s vs %s): %s" % (pid, c["label_a"], c["label_b"], verdict))
w()
_p1l = C["P1"]["delivery"]["loop_freq30"]
w("**A confound in P2, and why it cannot carry the effect.** P2's vendor-matched design ties")
w("model identity to `presence_penalty`: the 3.8 vendor sampler carries pp=1.5 while 3.6's")
w("carries pp=0, so any P2 delta could in principle be a presence-penalty artifact rather than")
w("a model difference. That objection fails against the delivery finding: P1 holds pp=0 on")
w("**both** sides and still shows the %s loop delta (%s), so the looping regression"
  % (pp(_p1l["diff"]), pv(_p1l["fisher_p"])))
w("appears with the confound removed entirely. P2's *quality* deltas have no pp-free")
w("replication at the same (no-think) mode — P1, the pp=0 no-think pair, flips sign across")
w("scorings — so the confound caveat does apply to P2's pass rates. One more reason the loop")
w("finding, not the pass-rate finding, is this document's headline.")
w()
w("Three statements survive **every scoring rule**, in every comparison where they can be")
w("measured at all:")
w()
w("1. **3.8's no-think looping is real and large.** Loop rate (freq30) is %s in P1 (%s) and %s in"
   % (pp(C["P1"]["delivery"]["loop_freq30"]["diff"]), pv(C["P1"]["delivery"]["loop_freq30"]["fisher_p"]),
      pp(C["P2"]["delivery"]["loop_freq30"]["diff"])))
w("   P2 (%s), with CIs excluding zero. It is the single largest and most reliable effect in the"
   % pv(C["P2"]["delivery"]["loop_freq30"]["fisher_p"]))
w("   corpus, and it is not sensitive to any scoring choice because it is measured upstream of grading.")
w("2. **The looping is confined to no-think mode.** In thinking mode the loop rate collapses to")
w("   %d/%d and %d/%d for 3.8 (P3, P4) against %d/%d and %d/%d for 3.6 — no significant difference"
   % (G["B38"]["loop_freq30"]["x"], G["B38"]["n"], G["C38"]["loop_freq30"]["x"], G["C38"]["n"],
      G["B36"]["loop_freq30"]["x"], G["B36"]["n"], G["C36"]["loop_freq30"]["x"], G["C36"]["n"]))
w("   and, at T1/p0.95/pp0, zero loops on either side.")
w("3. **3.8 costs more in thinking mode.** Median per-family token ratio is ×%.2f (P3) and ×%.2f"
   % (C["P3"]["cost"]["tokens"]["median_of_family_ratios"],
      C["P4"]["cost"]["tokens"]["median_of_family_ratios"]))
w("   (P4), with wall-clock tracking it (×%.2f, ×%.2f), and no pass-rate gain to show for it."
   % (C["P3"]["cost"]["elapsed"]["median_of_family_ratios"],
      C["P4"]["cost"]["elapsed"]["median_of_family_ratios"]))
w()
w("The claim that does **not** survive is any clean statement that 3.8 produces worse *output*.")
_p1ad = C["P1"]["quality"]["pass_all"]["diff"]
_p1gd = C["P1"]["quality"]["pass_graded"]["diff"]
if _p1ad < 0 < _p1gd:
    w("In P1 the sign flips: 3.8 is %.1f pp worse end-to-end but %.1f pp **better** among graded"
      % (-100 * _p1ad, 100 * _p1gd))
    w("cells. Both cannot be summarized as \"3.8 is worse at the task\" — the honest reading is")
    w("that 3.8 fails more often by not finishing, not by finishing badly.")
elif _p1ad < 0 and _p1gd < 0:
    w("In P1, 3.8 is %.1f pp worse end-to-end but only %.1f pp worse among graded cells, with the"
      % (-100 * _p1ad, -100 * _p1gd))
    w("graded-only CI straddling zero — the end-to-end gap is dominated by delivery, and the")
    w("honest reading remains that 3.8 fails mostly by not finishing, not by finishing badly.")
else:
    w("In P1 the end-to-end delta is %s and the graded-only delta is %s — the gap between the"
      % (pp(_p1ad), pp(_p1gd)))
    w("two is the delivery effect, and the honest reading remains that delivery, not output")
    w("quality, is where the models separate.")
w()

# ============================================================ 8. defects
w("---")
w()
w("## 8. Grader-defect exposure (why these tables are labelled *as-graded*)")
w()
w("Every pass rate in this document is **as-graded**: it uses the `passed` bit exactly as the")
w("original graders produced it. Three grader defects are verified in this corpus. Per repo")
w("convention they are corrected in a **separate non-destructive overlay**, never by editing")
w("`grade.json` or the task briefs, so longitudinal comparability is preserved. The tables here")
w("are the baseline that overlay will be applied to.")
w()
w("Diagnostics below are computed from raw `grade.json` files (the frozen CSV carries only the")
w("final pass/fail bit, so diagnosing *why* a cell failed requires the grader's score fields).")
w("Cell→model identity is joined from the frozen CSV by cell id, and cells that were ungraded")
w("at the freeze are excluded even where a post-freeze `grade.json` now exists on disk (see the")
w("drift note in §6). **No headline number above depends on this section.**")
w()
w("### Exposure: cells sitting in a defect-affected family")
w()
w("| Group | n | D1 length-gated (4 families) | D2 `p3_pm` | D3 `p2_triage` |")
w("|---|---:|---|---|---|")
for gid, v in R["defect_exposure"].items():
    w("| `%s` | %d | n=%d, graded=%d, pass=%d | n=%d, graded=%d, pass=%d | n=%d, graded=%d, pass=%d |" % (
        gid, v["n"],
        v["d1_length_gated"]["n"], v["d1_length_gated"]["graded"], v["d1_length_gated"]["passes"],
        v["d2_p3_pm"]["n"], v["d2_p3_pm"]["graded"], v["d2_p3_pm"]["passes"],
        v["d3_p2_triage"]["n"], v["d3_p2_triage"]["graded"], v["d3_p2_triage"]["passes"]))
w()
D = R["defect_diagnostics"]
w("### D1 — word-gate tokenizer mismatch · correction favours **3.8**")
w()
b = D["D1_word_gate"]["p3_business"]; d = D["D1_word_gate"]["p3_doc"]
w("| Family | 3.6 pass/n | 3.6 over word limit | 3.8 pass/n | 3.8 over word limit |")
w("|---|---:|---:|---:|---:|")
w("| `p3_business` | %d/%d | %d | %d/%d | %d |" % (
    b["3.6"].get("PASS", 0), b["3.6"]["n"], b["3.6"].get("over_limit", 0),
    b["3.8"].get("PASS", 0), b["3.8"]["n"], b["3.8"].get("over_limit", 0)))
w("| `p3_doc` | %d/%d | %d | %d/%d | %d |" % (
    d["3.6"].get("PASS", 0), d["3.6"]["n"], d["3.6"].get("over_limit", 0),
    d["3.8"].get("PASS", 0), d["3.8"]["n"], d["3.8"].get("over_limit", 0)))
w()
w("In `p3_business` **every** FAIL on both sides is a word-limit FAIL (3.6: %d/%d, 3.8: %d/%d);"
  % (b["3.6"].get("fail_with_over_limit", 0), b["3.6"].get("FAIL", 0),
     b["3.8"].get("fail_with_over_limit", 0), b["3.8"].get("FAIL", 0)))
w("the substantive `stance_pushback` criterion was met by every graded cell of both models.")
w()
LIM = D["D1_word_gate"]["p3_doc_limit"]
ov = D["D1_word_gate"]["p3_doc_overshoot_wordcounts"]
w("Overshoot sizes in `p3_doc` against its %d-word ceiling, i.e. how far over the grader's own" % LIM)
w("counter each failing deliverable landed:")
w()
w("| Model | Over-limit cells | Word counts | Overshoot range | Median overshoot |")
w("|---|---:|---|---:|---:|")
for m in ["3.6", "3.8"]:
    vals = sorted(ov.get(m, []))
    if not vals: continue
    over = [v - LIM for v in vals]
    med = over[len(over) // 2] if len(over) % 2 else (over[len(over)//2-1] + over[len(over)//2]) / 2
    w("| %s | %d | %s | %d–%d words | %.1f words |" % (
        m, len(vals), ", ".join(str(v) for v in vals), min(over), max(over), med))
w()
w("The bulk of these are single-digit to low-double-digit overruns on a 700-word budget — 3.6's")
w("largest is %d words over and its median is %.0f — which is well inside the disagreement between"
  % (max(v - LIM for v in ov["3.6"]),
     sorted(v - LIM for v in ov["3.6"])[len(ov["3.6"]) // 2]))
w("the two counters. That is the substance of D1: the graders count `\\b\\w+\\b` while both models")
w("budgeted with shell `wc -w`, and neither counter is ground truth. **The tail runs longer on")
w("3.8's side** — its worst `p3_doc` overshoot is %d words (%d against a %d ceiling) versus"
  % (max(v - LIM for v in ov["3.8"]), max(ov["3.8"]), LIM))
w("3.6's %d — so the overlay must report per-cell outcomes rather than assume a blanket"
  % max(v - LIM for v in ov["3.6"]))
w("reversal; correcting D1 should be expected to rescue most, though not necessarily all, of")
w("3.8's length failures.")
w()
w("### D2 — `p3_pm` risk-keyword literalism · correction favours **3.6**")
w()
pm = D["D2_p3_pm"]
w("| Model | Pass/n | FAILs blocked by risk_recall < 3 | risk_recall distribution |")
w("|---|---:|---:|---|")
for m in ["3.6", "3.8"]:
    if m not in pm: continue
    dist = pm["risk_recall_distribution"].get(m, {})
    w("| %s | %d/%d | %d | %s |" % (
        m, pm[m].get("PASS", 0), pm[m]["n"], pm[m].get("fail_with_risk_recall_below_min", 0),
        ", ".join("%s risks: %d cells" % (k, v) for k, v in sorted(dist.items()))))
w()
w("**%d of %d** 3.6 cells land on exactly `2/6` risks — one short of the `min_risks = 3`"
  % (pm["3.6"]["risk_recall_distribution"].get("2", 0) if isinstance(pm["3.6"].get("risk_recall_distribution"), dict)
     else D["D2_p3_pm"]["risk_recall_distribution"]["3.6"].get("2", 0), pm["3.6"]["n"]))
w("threshold — and every one of the %d 3.6 FAILs is blocked by that rule alone. This is the"
  % pm["3.6"].get("FAIL", 0))
w("signature of a single unmatched keyword, consistent with the verified R3 literalism ")
w("(3.6 writes \"legal has not responded\"; the rule requires a contracted form).")
w()
w("### D3 — `p2_triage` brief/ground-truth contradiction · correction favours **3.6**")
w()
t3 = D["D3_p2_triage"]
w("| Quantity | Value |")
w("|---|---:|")
w("| Graded triage cells examined | %d |" % t3["n_cells"])
w("| Cells answering `n/a` on all three spam tickets (004, 009, 021) | **%d/%d** |" % (
    t3["all_three_spam_na"], t3["n_cells"]))
w("| FAIL cells | %d |" % t3["fails"])
w("| FAIL cells blocked by urgency accuracy *alone* | **%d/%d** |" % (
    t3["fail_blocked_by_urgency_only"], t3["fails"]))
w("| FAIL cells that flip to PASS once the spam penalty is removed | **%d/%d** |" % (
    sum(t3["would_flip_to_pass"].values()), t3["fails"]))
w("| …of which 3.6 | %d |" % t3["would_flip_to_pass"].get("3.6", 0))
w("| …of which 3.8 | %d |" % t3["would_flip_to_pass"].get("3.8", 0))
w()
w("> **Correction to the briefed characterization of D3.** The defect brief states that")
w("> `p2_triage` \"has zero discriminating power as graded\". The frozen data does not support")
w("> that as written: **as graded** the family splits %d PASS / %d FAIL and does discriminate"
  % (t3["verdicts"].get("PASS", 0), t3["verdicts"].get("FAIL", 0)))
w("> (3.6 %d/%d vs 3.8 %d/%d). The accurate statement is the reverse in time: all %d cells take"
  % (t3["by_model"].get("3.6:PASS", 0),
     t3["by_model"].get("3.6:PASS", 0) + t3["by_model"].get("3.6:FAIL", 0),
     t3["by_model"].get("3.8:PASS", 0),
     t3["by_model"].get("3.8:PASS", 0) + t3["by_model"].get("3.8:FAIL", 0),
     t3["n_cells"]))
w("> the identical 0.100 urgency penalty, and because the threshold is 0.700 that penalty decides")
w("> the verdict purely by where each cell already sat — cells at 0.767–0.800 survive, cells at")
w("> 0.633–0.667 do not. The observed split is threshold noise, not signal. It is **after** the")
w("> correction that the family becomes uniformly passing and loses all discriminating power.")
w()
w("### Net direction of the pending overlay")
w()
w("The three defects **do not push the same way**: D1 materially helps 3.8, while D2 and D3 help")
w("3.6. Anyone assuming the corrections will uniformly move the headline in one direction is")
w("wrong. The as-graded numbers in this document should not be read as biased against either")
w("model until the overlay is computed.")
w()
w("As one bound on how much of the quality signal is defect-contaminated, restricting to the")
w("seven families with **no** verified grader defect (`%s`):"
  % "`, `".join(R["defect_free_subset"]["P1"]["clean_families"]))
w()
w("| Comparison | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |")
w("|---|---|---|---:|---|---:|")
for pid, v in R["defect_free_subset"].items():
    w("| %s | %d/%d %s | %d/%d %s | %s | %s | %s%s |" % (
        pid, v["a"]["x"], v["a"]["n"], pct(v["a"]["p"]), v["b"]["x"], v["b"]["n"], pct(v["b"]["p"]),
        pp(v["diff"]), ci(v["diff_lo"], v["diff_hi"]), pv(v["fisher_p"]), sig(v["fisher_p"])))
w()
w("This subset is **not** a substitute for the overlay: it changes the family mix (and in P1/P2 it")
w("is heavily confounded by 3.8's looping, which is concentrated in `p1_bugfix` and `p1_testwrite`).")
w("It is reported only to show that the defect families are load-bearing for the as-graded totals.")
w()

# ============================================================ 9. power
w("---")
w()
w("## 9. Comparisons too underpowered to report")
w()
w("Screening rule, applied uniformly: a comparison is flagged **UNDERPOWERED** if either arm has")
w("n < 30, or the Newcombe 95% CI on the difference is wider than 30 pp — i.e. the interval")
w("cannot separate a small effect from a large one in either direction.")
w()
rows = []
for pid, c in C.items():
    for k, v in c["power"].items():
        blk = (c["quality"].get(k.replace("sens_", "")) or c["delivery"].get(k) or
               c["sensitivity"].get(k.replace("sens_", "")))
        if blk is None or blk.get("diff_lo") is None: continue
        wdt = blk["diff_hi"] - blk["diff_lo"]
        rows.append((pid, k, blk["diff"], blk["diff_lo"], blk["diff_hi"], wdt, v,
                     blk.get("fisher_p")))
w("This flag is about **precision, not significance**, and the two are independent. A result can")
_ex = next((r for r in rows if r[6]["underpowered"] and r[7] is not None and r[7] < 0.05), None)
if _ex:
    w("be flagged here and still be statistically significant (%s `%s`: %s, p = %s, but a"
      % (_ex[0], _ex[1].replace("sens_", ""), pp(_ex[2]), pv(_ex[7])))
    w("%.1f pp-wide interval). Read such rows as \"the direction is probably real, the magnitude"
      % (100 * _ex[5]))
else:
    w("be flagged here and still be statistically significant. Read such rows as \"the direction")
    w("is probably real, the magnitude")
_p3q = C["P3"]["quality"]["pass_all"]
w("is not pinned down\". Conversely, P3's non-significant rows are flagged because the data cannot")
w("distinguish \"no difference\" from \"a difference of %.0f pp in either direction\" — **P3 is not"
  % (100 * max(abs(_p3q["diff_lo"]), abs(_p3q["diff_hi"]))))
w("evidence of equivalence.**")
w()
w("| Comparison | Metric | Δ | 95% CI | Width | Verdict |")
w("|---|---|---:|---|---:|---|")
for pid, k, d, lo, hi, wdt, v, _fp in rows:
    if not v["underpowered"]: continue
    w("| %s | `%s` | %s | %s | %.1f pp | UNDERPOWERED — %s |" % (
        pid, k.replace("sens_", ""), pp(d), ci(lo, hi), 100 * wdt, "; ".join(v["reasons"])))
w()
w("Explicitly **not** reportable:")
w()
_bw = [100 * (c["sensitivity"]["best_of_n_per_family"]["diff_hi"]
              - c["sensitivity"]["best_of_n_per_family"]["diff_lo"]) for c in C.values()]
_ew = [100 * (p["diff_hi"] - p["diff_lo"]) for p in R["effort_ladder"]["pairwise"]]
_q9 = R["quant_control"]
w("- **The Q8_0 quantization arm for any quality *verdict*.** %d of %d cells graded at freeze #2;"
  % (_q9["n_graded"], _q9["pass_all"]["n"]))
w("  the graded-only rate %d/%d is published in §6 as provisional data with a Wilson interval"
  % (_q9["pass_graded"]["x"], _q9["pass_graded"]["n"]))
w("  spanning tens of points — direction-finding for the next freeze, not evidence.")
w("- **Every `best_of_n_per_family` result.** n = 12 families per side by construction; CI widths")
w("  are %.1f–%.1f pp. These rows are shown for completeness of the sensitivity grid, not as evidence."
  % (min(_bw), max(_bw)))
_frn = [c["sensitivity"]["first_replicate_only"][s]["n"] for c in C.values() for s in ("a", "b")]
w("- **Every `first_replicate_only` result** for the same reason (n = %d–%d)."
  % (min(_frn), max(_frn)))
_nword = {6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}.get(len(_ew), str(len(_ew)))
w("- **Every effort-ladder step.** All %s pairwise steps are non-significant with CI widths"
  % _nword)
w("  of %.1f–%.1f pp." % (min(_ew), max(_ew)))
_fam_ns = [f[k] for c in C.values() for f in c["family_breakdown"] for k in ("n_a", "n_b") if f[k]]
w("- **All per-family rows in §3** individually (n = %d–%d per side)."
  % (min(_fam_ns), max(_fam_ns)))
w("- **P4's quality delta** is borderline and, more importantly, structurally biased: the shared")
w("  T1/p0.95/pp0 sampler is 3.6's vendor point and not 3.8's, so 3.8 runs off-spec by construction.")
w()

# ============================================================ 10. appendix
w("---")
w()
w("## 10. Method appendix")
w()
w("### Estimators (pure python, no scipy)")
w()
w("**Wilson score interval** for a proportion — inverts the score test rather than using the")
w("Wald form, so it stays inside [0,1] and behaves at x = 0 and x = n (several arms here are 0/n):")
w()
w("```")
w("center = (p + z^2/(2n)) / (1 + z^2/n)")
w("half   = z * sqrt( p(1-p)/n + z^2/(4n^2) ) / (1 + z^2/n)")
w("CI     = center -/+ half            z = 1.959963984540054")
w("```")
w()
w("**Fisher exact test**, two-sided. Conditioning on both margins, the top-left cell follows the")
w("hypergeometric law; the p-value is the Fisher/Irwin sum-of-small-probabilities form used by")
w("R's `fisher.test`:")
w()
w("```")
w("P(a) = C(r1,a) * C(r2,c1-a) / C(r1+r2,c1)")
w("p    = sum of P(x) over all tables x with the same margins where P(x) <= P(observed)")
w("```")
w()
w("Computed in exact rational arithmetic (`fractions.Fraction`), so no floating-point tie-breaking.")
w()
w("**Newcombe method 10** (hybrid score) CI for a difference of proportions — propagates the two")
w("Wilson intervals instead of a pooled Wald SE, which is what keeps it sane at boundary counts:")
w()
w("```")
w("lower = (p1-p2) - sqrt( (p1-l1)^2 + (u2-p2)^2 )")
w("upper = (p1-p2) + sqrt( (u1-p1)^2 + (p2-l2)^2 )")
w("```")
w()
w("**Half-credit scoring** produces per-cell scores in {0, 0.5, 1}, which are not Bernoulli.")
w("Wilson/Newcombe/Fisher are therefore **not** applied to it; that row uses a z-interval on")
w("the difference of means (`z_diff_mean` — a normal approximation with critical value z, not")
w("a Welch-t interval) and is labelled as such.")
w()
w("### Validation")
w()
w("`test_stats.py` checks each estimator against its defining equation or an exact independent")
w("enumeration rather than against remembered published values:")
w()
w("- Wilson limits are verified to be exact roots of the score equation (the score statistic")
w("  evaluates to z at both limits to 1e-9), and to bracket p̂ for every (x, n) with n ≤ 199.")
w("- The hypergeometric pmf is verified to sum to exactly 1 in rational arithmetic, and to match")
w("  brute-force enumeration over all C(11,4) subsets.")
w("- Fisher reproduces the tea-tasting table `[[3,1],[1,3]]` as exactly 17/35, is symmetric under")
w("  row and column swaps, and agrees with the chi-square approximation at large n.")
w("- Newcombe is verified against its construction, verified antisymmetric under group swap, and")
w("  its zero-exclusion agrees with Fisher p < 0.05 on 98.2% of a 441-table grid.")
w()
w("One real defect was found and fixed by this suite: at x = 0 and x = n the Wilson closed form")
w("missed the exact boundary by ~1e-16, leaving the interval not quite containing p̂. Those two")
w("cases are now snapped to exactly 0 and 1.")
w()
w("### Known limitations of this dataset")
w()
_nc = R["provenance"]["n_cells"]
_dr = R["provenance"].get("depth_range", {})
_cm = R["provenance"]["cost_missing"]
w("1. **Single seed.** All %d runs use seed 42; replicates are repeat runs, not independent" % _nc)
w("   seeds. Binomial CIs treat cells as independent draws, which is optimistic.")
w("2. **Unequal and non-random depth.** Replicate counts vary by family and arm (%s per"
  % (("%d–%d" % (_dr["min"], _dr["max"])) if _dr else "1–19"))
w("   family-group). The `depth_matched` scoring exists to bound the effect of this.")
w("3. **Non-random missing cost data.** %d of %d cells lack `completion_tokens`; %s"
  % (_cm["n"], _nc,
     ("all %d are" % _cm["n"]) if _cm["all_ungraded"] else "nearly all are"))
w("   ungraded and most looped. Cost figures for affected arms are lower bounds.")
w("4. **Pooled effort in 3.8 thinking.** Groups `B38` and `C38` each pool three effort levels;")
w("   their aggregate pass rates are effort-mix-weighted, not single-configuration numbers.")
w("5. **As-graded only.** Three verified grader defects remain uncorrected here by design.")
w("6. **Arm pooling.** Several groups pool two or more arms that share model, quant, mode and")
w("   sampler triple but were run as separate sweeps (listed in §0).")
w()

open(OUT, "w").write("\n".join(L) + "\n")
print("wrote", OUT, len(L), "lines")
