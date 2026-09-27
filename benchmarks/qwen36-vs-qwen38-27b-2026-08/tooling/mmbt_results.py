#!/usr/bin/env python3
"""
MMBT Qwen3.6-27B vs Qwen3.8-27B -- definitive results tables.

Single source of truth: /home/michael/mmbt-frozen-dataset-v2.csv (802 cells,
freeze #2, frozen 2026-08-16T14:23:09Z). Nothing here re-scans the live corpus.
Freeze #1 (mmbt-frozen-dataset.csv, 746 cells, 2026-08-16T11:49:14Z) is superseded.

All statistics are implemented in pure python (no scipy). Formulas are in
comments at each implementation.
"""
from __future__ import annotations

import csv
import json
import math
from fractions import Fraction
from collections import OrderedDict, defaultdict

CSV_PATH = "/home/michael/mmbt-frozen-dataset-v2.csv"
FROZEN_AT = "2026-08-16T14:23:09Z"  # freeze #2 stamp, /home/michael/FREEZE2_STAMP.txt
OUT_MD = "/home/michael/pr-staging/results-tables.md"
OUT_JSON = "/home/michael/pr-staging/results.json"

Z = 1.959963984540054  # standard normal 97.5th percentile -> 95% two-sided


# --------------------------------------------------------------------------
# STATISTICS (pure python)
# --------------------------------------------------------------------------

def wilson(x, n, z=Z):
    """Wilson score interval for a binomial proportion.

    Solves |p_hat - p| / sqrt(p(1-p)/n) = z for p. Closed form:

        center = (p_hat + z^2/(2n)) / (1 + z^2/n)
        half   = z * sqrt( p_hat(1-p_hat)/n + z^2/(4n^2) ) / (1 + z^2/n)
        CI     = center -/+ half

    Unlike the Wald interval this never leaves [0,1] and stays sensible at
    x = 0 or x = n, which matters here because several cells are 0/N or N/N.
    """
    if n == 0:
        return (None, None, None)
    p = x / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    lo, hi = center - half, center + half
    # At x=0 the two terms are algebraically equal, and at x=n they sum to
    # exactly 1; in floating point they miss by ~1e-16, which would leave the
    # interval failing to contain p_hat. Snap those exact boundary cases.
    if x == 0:
        lo = 0.0
    if x == n:
        hi = 1.0
    return (p, max(0.0, lo), min(1.0, hi))


def _hypergeom_pmf(a, r1, r2, c1):
    """P(X=a) for the central (non-central psi=1) hypergeometric:

        P(a) = C(r1, a) * C(r2, c1 - a) / C(r1 + r2, c1)

    Exact rational arithmetic -- no floating point until the final compare.
    """
    n = r1 + r2
    return Fraction(math.comb(r1, a) * math.comb(r2, c1 - a), math.comb(n, c1))


def fisher_exact_two_sided(a, b, c, d):
    """Two-sided Fisher exact test on the 2x2 table

            success   failure
        g1     a         b        (row total r1 = a+b)
        g2     c         d        (row total r2 = c+d)

    Conditioning on both margins, the count `a` follows the hypergeometric
    distribution above. The two-sided p-value is the standard "sum of small
    probabilities" (Fisher/Irwin) definition used by R's fisher.test:

        p = sum over all tables t with the same margins of P(t),
            for every t with P(t) <= P(observed) * (1 + eps)

    eps = 1e-9 guards against ties being dropped by rounding. Exact rationals
    make that guard nearly cosmetic, but it is kept for safety.
    """
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2
    if r1 == 0 or r2 == 0 or c1 == 0 or c1 == n:
        return 1.0
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    p_obs = _hypergeom_pmf(a, r1, r2, c1)
    tol = p_obs * Fraction(1000000001, 1000000000)
    total = Fraction(0)
    for x in range(lo, hi + 1):
        px = _hypergeom_pmf(x, r1, r2, c1)
        if px <= tol:
            total += px
    return min(1.0, float(total))


def newcombe_diff(x1, n1, x2, n2, z=Z):
    """Newcombe's method 10 ("hybrid score") 95% CI for p1 - p2.

    Let (l1,u1) and (l2,u2) be the Wilson intervals for p1 and p2. Then

        lower = (p1 - p2) - sqrt( (p1 - l1)^2 + (u2 - p2)^2 )
        upper = (p1 - p2) + sqrt( (u1 - p1)^2 + (p2 - l2)^2 )

    This propagates each group's *score* interval rather than a pooled Wald
    SE, so it behaves at boundary counts where Wald difference CIs break.
    """
    if n1 == 0 or n2 == 0:
        return (None, None, None)
    p1, l1, u1 = wilson(x1, n1, z)
    p2, l2, u2 = wilson(x2, n2, z)
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (d, max(-1.0, lower), min(1.0, upper))


def z_diff_mean(xs, ys, z=Z):
    """z-interval (normal approximation) on the difference of MEANS of
    bounded scores.

        d  = mean(xs) - mean(ys)
        se = sqrt( var(xs)/n1 + var(ys)/n2 )     (unbiased sample variances)
        CI = d -/+ z*se

    NOT a Welch t-interval: the critical value is the fixed normal z, with no
    Welch-Satterthwaite degrees of freedom. At the n here (>=51 per side) the
    difference is negligible, but the name should not overclaim.

    Used only for the half-credit scoring, where the per-cell score is in
    {0, 0.5, 1} and therefore NOT binomial -- Wilson/Newcombe do not apply.
    Labelled as such everywhere it is reported.
    """
    n1, n2 = len(xs), len(ys)
    if n1 < 2 or n2 < 2:
        return (None, None, None)
    m1 = sum(xs) / n1
    m2 = sum(ys) / n2
    v1 = sum((v - m1) ** 2 for v in xs) / (n1 - 1)
    v2 = sum((v - m2) ** 2 for v in ys) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    d = m1 - m2
    return (d, d - z * se, d + z * se)


def median(vals):
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return None
    if n % 2:
        return float(v[n // 2])
    return (v[n // 2 - 1] + v[n // 2]) / 2.0


# --------------------------------------------------------------------------
# DATA
# --------------------------------------------------------------------------

def load():
    with open(CSV_PATH, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("graded", "passed", "terminal", "looped_freq30", "looped_run30",
                  "replicate", "n_tools", "max_freq", "max_run"):
            r[k] = int(r[k])
        for k in ("completion_tokens", "elapsed_s"):
            r[k] = float(r[k]) if r[k].strip() != "" else None
    return rows


ROWS = load()

# Group keys are (model, quant, mode, regime) -- exactly the identity fields
# the frozen CSV carries from receipt.json. Never derived from paths.
GROUPS = OrderedDict([
    ("A36", dict(label="3.6 no-think T0.3/p0.8/pp0",
                 note="off-spec for 3.6 (its card is T1/p0.95/pp0); sampler-matched to A38",
                 key=("3.6", "UD-Q4_K_XL", "no-think", "T0.3/p0.8/pp0"))),
    ("A38", dict(label="3.8 no-think T0.3/p0.8/pp0",
                 note="off-spec for 3.8 (its card is T0.7/p0.8/pp1.5); sampler-matched to A36",
                 key=("3.8", "UD-Q4_K_XL", "no-think", "T0.3/p0.8/pp0"))),
    ("V36", dict(label="3.6 no-think T1/p0.95/pp0",
                 note="3.6 VENDOR point",
                 key=("3.6", "UD-Q4_K_XL", "no-think", "T1/p0.95/pp0"))),
    ("V38", dict(label="3.8 no-think T0.7/p0.8/pp1.5",
                 note="3.8 VENDOR point",
                 key=("3.8", "UD-Q4_K_XL", "no-think", "T0.7/p0.8/pp1.5"))),
    ("B36", dict(label="3.6 think T0.3/p0.8/pp0",
                 note="off-spec for 3.6; sampler-matched to B38",
                 key=("3.6", "UD-Q4_K_XL", "think", "T0.3/p0.8/pp0"))),
    ("B38", dict(label="3.8 think T0.3/p0.8/pp0",
                 note="off-spec for 3.8; sampler-matched to B36; MIXED effort (low/medium/xhigh)",
                 key=("3.8", "UD-Q4_K_XL", "think", "T0.3/p0.8/pp0"))),
    ("C36", dict(label="3.6 think T1/p0.95/pp0",
                 note="3.6 VENDOR point",
                 key=("3.6", "UD-Q4_K_XL", "think", "T1/p0.95/pp0"))),
    ("C38", dict(label="3.8 think T1/p0.95/pp0",
                 note="this is 3.6's vendor point, NOT 3.8's; sampler-matched to C36 but off-spec "
                      "for 3.8; MIXED effort (low/medium/xhigh)",
                 key=("3.8", "UD-Q4_K_XL", "think", "T1/p0.95/pp0"))),
    ("Q8", dict(label="3.8 Q8_0 no-think T0.3/p0.8/pp0",
                note="quantization control; 19 cells over all 12 families "
                     "(2 replicates on the 7 phase-1/2 families, 1 on the 5 phase-3)",
                key=("3.8", "Q8_0", "no-think", "T0.3/p0.8/pp0"))),
])

for gid, g in GROUPS.items():
    m, q, md, rg = g["key"]
    g["rows"] = [r for r in ROWS
                 if r["model"] == m and r["quant"] == q and r["mode"] == md and r["regime"] == rg]

PAIRS = [
    ("P1", "A36", "A38", "No-think, SAMPLER-MATCHED (both T0.3/p0.8/pp0). Off-spec for both "
                         "models; the cleanest controlled-sampler contrast."),
    ("P2", "V36", "V38", "No-think, VENDOR-MATCHED (each model at its own model-card sampler: "
                         "3.6 T1/p0.95/pp0, 3.8 T0.7/p0.8/pp1.5). Best-foot-forward contrast; "
                         "sampler differs by construction."),
    ("P3", "B36", "B38", "Thinking, SAMPLER-MATCHED (both T0.3/p0.8/pp0). Off-spec for both. "
                         "3.8 side pools three effort levels."),
    ("P4", "C36", "C38", "Thinking at T1/p0.95/pp0. Sampler-matched, but that triple is 3.6's "
                         "vendor point and is NOT 3.8's -- 3.8 is running off-spec here and this "
                         "pair is biased in 3.6's favour. 3.8 side pools three effort levels."),
]

FAMILIES = sorted(set(r["family"] for r in ROWS))
LENGTH_GATED = ["p3_business", "p3_doc", "p3_pm", "p3_writing"]  # verified: hard word gate
TRIAGE = ["p2_triage"]
PM = ["p3_pm"]


# --------------------------------------------------------------------------
# METRIC BLOCKS
# --------------------------------------------------------------------------

def rate_block(rows, pred, denom_rows=None):
    dr = rows if denom_rows is None else denom_rows
    n = len(dr)
    x = sum(1 for r in dr if pred(r))
    p, lo, hi = wilson(x, n)
    return dict(x=x, n=n, p=p, lo=lo, hi=hi)


def cmp_block(rows_a, rows_b, pred, denom_a=None, denom_b=None):
    """SIGN CONVENTION, used identically everywhere in this file:
        diff = p_b - p_a   (i.e. 3.8 minus 3.6)
    so a NEGATIVE diff always means the newer model is worse on that metric.
    Group `a` is always the 3.6 arm and group `b` always the 3.8 arm.
    """
    A = rate_block(rows_a, pred, denom_a)
    B = rate_block(rows_b, pred, denom_b)
    if A["n"] == 0 or B["n"] == 0:
        return dict(a=A, b=B, fisher_p=None, diff=None, diff_lo=None, diff_hi=None)
    p = fisher_exact_two_sided(A["x"], A["n"] - A["x"], B["x"], B["n"] - B["x"])
    d, lo, hi = newcombe_diff(B["x"], B["n"], A["x"], A["n"])
    return dict(a=A, b=B, fisher_p=p, diff=d, diff_lo=lo, diff_hi=hi)


IS_TERMINAL = lambda r: r["terminal"] == 1
IS_UNGRADED = lambda r: r["graded"] == 0
IS_LOOP_F = lambda r: r["looped_freq30"] == 1
IS_LOOP_R = lambda r: r["looped_run30"] == 1
IS_PASS = lambda r: r["passed"] == 1


def group_summary(rows):
    graded = [r for r in rows if r["graded"] == 1]
    return dict(
        n=len(rows),
        # Missing-data structure. "passed==0" pools two very different things:
        # a cell that was graded and failed, and a cell that was never graded at
        # all. Anyone treating all-cells pass rate as a quality measure needs
        # these counts, so they are carried explicitly.
        missing=dict(
            graded_fail=sum(1 for r in rows if r["graded"] == 1 and r["passed"] == 0),
            ungraded_looped=sum(1 for r in rows if r["graded"] == 0 and r["looped_freq30"] == 1),
            ungraded_not_looped=sum(1 for r in rows
                                    if r["graded"] == 0 and r["looped_freq30"] == 0),
            graded_but_looped=sum(1 for r in rows
                                  if r["graded"] == 1 and r["looped_freq30"] == 1)),
        terminal=rate_block(rows, IS_TERMINAL),
        ungraded=rate_block(rows, IS_UNGRADED),
        loop_freq30=rate_block(rows, IS_LOOP_F),
        loop_run30=rate_block(rows, IS_LOOP_R),
        pass_graded=rate_block(graded, IS_PASS),
        pass_all=rate_block(rows, IS_PASS),
        n_graded=len(graded),
        families=len(set(r["family"] for r in rows)),
        arms=sorted(set(r["arm"] for r in rows)),
        cost_missing=sum(1 for r in rows if r["completion_tokens"] is None),
    )


# --------------------------------------------------------------------------
# COST, MATCHED BY FAMILY
# --------------------------------------------------------------------------

def cost_by_family(rows_a, rows_b, field):
    """Per-family medians restricted to families present in BOTH groups.

    Rationale: an unmatched pooled median silently reweights toward whichever
    families a group happens to have more replicates of. Earlier in this
    project that produced two contradictory cost claims from the same corpus.

    Cost data is MISSING exactly when a cell was never graded, and looping is the
    dominant cause of that. So missingness is not random: it is concentrated in
    the runs that would have been most expensive. A family is therefore only
    treated as cost-comparable when BOTH sides retain >=3 cells with cost data
    AND >=50% of that side's cells in the family. Uncovered families are still
    printed, but excluded from the summary ratio.
    """
    fa = set(r["family"] for r in rows_a)
    fb = set(r["family"] for r in rows_b)
    shared = sorted(fa & fb)
    per = []
    for f in shared:
        ca = [r for r in rows_a if r["family"] == f]
        cb = [r for r in rows_b if r["family"] == f]
        va = [r[field] for r in ca if r[field] is not None]
        vb = [r[field] for r in cb if r[field] is not None]
        ma, mb = median(va), median(vb)
        cov_a = len(va) / len(ca) if ca else 0.0
        cov_b = len(vb) / len(cb) if cb else 0.0
        ok = (len(va) >= 3 and len(vb) >= 3 and cov_a >= 0.5 and cov_b >= 0.5)
        per.append(dict(family=f, n_a=len(va), n_b=len(vb),
                        cells_a=len(ca), cells_b=len(cb),
                        coverage_a=cov_a, coverage_b=cov_b, comparable=ok,
                        median_a=ma, median_b=mb,
                        delta=(mb - ma) if (ma is not None and mb is not None) else None,
                        ratio=(mb / ma) if (ma not in (None, 0) and mb is not None) else None))
    good = [p for p in per if p["comparable"]]
    deltas = [p["delta"] for p in good if p["delta"] is not None]
    ratios = [p["ratio"] for p in good if p["ratio"] is not None]
    all_ratios = [p["ratio"] for p in per if p["ratio"] is not None]
    pooled_a = median([r[field] for r in rows_a if r["family"] in shared and r[field] is not None])
    pooled_b = median([r[field] for r in rows_b if r["family"] in shared and r[field] is not None])
    tot_a = sum(1 for r in rows_a if r["family"] in shared)
    tot_b = sum(1 for r in rows_b if r["family"] in shared)
    have_a = sum(1 for r in rows_a if r["family"] in shared and r[field] is not None)
    have_b = sum(1 for r in rows_b if r["family"] in shared and r[field] is not None)
    return dict(shared_families=shared, per_family=per,
                n_comparable_families=len(good),
                comparable_families=[p["family"] for p in good],
                excluded_families=[p["family"] for p in per if not p["comparable"]],
                median_of_family_deltas=median(deltas) if deltas else None,
                median_of_family_ratios=median(ratios) if ratios else None,
                median_of_family_ratios_ALL=median(all_ratios) if all_ratios else None,
                pooled_median_a=pooled_a, pooled_median_b=pooled_b,
                pooled_is_censored=(have_a < tot_a or have_b < tot_b),
                coverage_a=have_a / tot_a if tot_a else None,
                coverage_b=have_b / tot_b if tot_b else None,
                cells_a=tot_a, cells_b=tot_b, with_data_a=have_a, with_data_b=have_b,
                n_families=len(shared))


def tokens_per_success(rows, families=None):
    """Total completion tokens spent / number of PASSing cells.

    Denominator is passes among the SAME cell set. Cells with no token
    accounting (all of them ungraded, hence non-passing) are excluded from
    the numerator and reported separately -- this makes the figure a lower
    bound on true cost per success.
    """
    sel = rows if families is None else [r for r in rows if r["family"] in families]
    toks = [r["completion_tokens"] for r in sel if r["completion_tokens"] is not None]
    passes = sum(1 for r in sel if r["passed"] == 1)
    miss = len(sel) - len(toks)
    return dict(total_tokens=sum(toks), n_cells_with_tokens=len(toks),
                n_cells=len(sel), n_missing_tokens=miss,
                token_coverage=len(toks) / len(sel) if sel else None,
                passes=passes,
                tokens_per_success=(sum(toks) / passes) if passes else None,
                # Tokens burned by cells that produced no grade at all: pure waste
                # that IS captured when the tokens were recorded.
                tokens_on_ungraded=sum(r["completion_tokens"] for r in sel
                                       if r["graded"] == 0 and r["completion_tokens"] is not None),
                is_lower_bound=miss > 0,
                lower_bound_note=("%d of %d cell%s no token accounting (all of them "
                                  "ungraded), so total tokens and tokens-per-success are "
                                  "UNDERSTATED for this arm."
                                  % (miss, len(sel), " has" if miss == 1 else "s have"))
                if miss else None)


# --------------------------------------------------------------------------
# SENSITIVITY SCORINGS
# --------------------------------------------------------------------------

def order_key(r):
    return (r["arm"], r["replicate"], r["cell"])


def depth_matched(rows_a, rows_b):
    """Equal replicates per family: for each shared family take the first
    k = min(n_a, n_b) cells from each side, ordered deterministically by
    (arm, replicate, cell). No randomness, fully reproducible."""
    fa = defaultdict(list)
    fb = defaultdict(list)
    for r in rows_a:
        fa[r["family"]].append(r)
    for r in rows_b:
        fb[r["family"]].append(r)
    out_a, out_b = [], []
    for f in sorted(set(fa) & set(fb)):
        k = min(len(fa[f]), len(fb[f]))
        out_a += sorted(fa[f], key=order_key)[:k]
        out_b += sorted(fb[f], key=order_key)[:k]
    return out_a, out_b


def best_of_n(rows):
    """Per family: 1 if ANY cell in the group passed, else 0."""
    fam = defaultdict(list)
    for r in rows:
        fam[r["family"]].append(r)
    return {f: (1 if any(r["passed"] == 1 for r in v) else 0) for f, v in fam.items()}


def sensitivity(rows_a, rows_b):
    out = OrderedDict()

    # 1. loops-as-failure = all-cells pass rate (ungraded/looped cells score 0)
    out["loops_as_failure"] = dict(
        definition="All cells in the group; passed==1 is success. Loops and ungraded "
                   "cells score 0. This is the headline scoring.",
        stat="binomial (Wilson/Newcombe/Fisher)",
        **cmp_block(rows_a, rows_b, IS_PASS))

    # 2. loops-excluded
    ea = [r for r in rows_a if r["looped_freq30"] == 0]
    eb = [r for r in rows_b if r["looped_freq30"] == 0]
    out["loops_excluded"] = dict(
        definition="Cells with looped_freq30==1 dropped entirely, then pass rate over "
                   "the remainder. Charitable to whichever model loops more. NOTE: cells "
                   "that are ungraded WITHOUT having looped are retained here and score 0.",
        stat="binomial (Wilson/Newcombe/Fisher)",
        **cmp_block(ea, eb, IS_PASS))

    # 2b. graded-only: drops loops AND ungraded cells. This is the pure
    # "when it produced something gradeable, how good was it" view.
    ga = [r for r in rows_a if r["graded"] == 1]
    gb = [r for r in rows_b if r["graded"] == 1]
    out["graded_only"] = dict(
        definition="Only graded==1 cells. Removes every delivery failure (loops and "
                   "ungraded alike) and measures output quality conditional on delivery. "
                   "Maximally charitable to a model that fails by not delivering.",
        stat="binomial (Wilson/Newcombe/Fisher)",
        **cmp_block(ga, gb, IS_PASS))

    # 3. loops-as-half-credit  (NOT binomial -> mean-difference CI)
    sa = [1.0 if r["passed"] == 1 else (0.5 if r["looped_freq30"] == 1 else 0.0) for r in rows_a]
    sb = [1.0 if r["passed"] == 1 else (0.5 if r["looped_freq30"] == 1 else 0.0) for r in rows_b]
    d, lo, hi = z_diff_mean(sb, sa)  # sign convention: 3.8 minus 3.6
    out["loops_half_credit"] = dict(
        definition="Score 1.0 for pass, 0.5 for a non-passing looped cell, 0.0 otherwise; "
                   "compare MEAN scores. Scores are not 0/1 so Wilson and Fisher do not "
                   "apply; CI is a z-interval on the difference of means.",
        stat="z-interval on difference of means -- NOT Wilson/Fisher, NOT Welch-t",
        a=dict(mean=sum(sa) / len(sa) if sa else None, n=len(sa)),
        b=dict(mean=sum(sb) / len(sb) if sb else None, n=len(sb)),
        diff=d, diff_lo=lo, diff_hi=hi, fisher_p=None)

    # 4. best-of-N per family
    ba, bb = best_of_n(rows_a), best_of_n(rows_b)
    shared = sorted(set(ba) & set(bb))
    xa = sum(ba[f] for f in shared)
    xb = sum(bb[f] for f in shared)
    n = len(shared)
    pa, la, ua = wilson(xa, n)
    pb, lb, ub = wilson(xb, n)
    fp = fisher_exact_two_sided(xa, n - xa, xb, n - xb)
    dd, dlo, dhi = newcombe_diff(xb, n, xa, n)  # sign convention: 3.8 minus 3.6
    out["best_of_n_per_family"] = dict(
        definition="One Bernoulli trial per SHARED family: 1 if any cell in that group/family "
                   "passed. Measures 'can the model ever do this task', not reliability. "
                   "n = number of families, so it is structurally low-powered.",
        stat="binomial over families (Wilson/Newcombe/Fisher)",
        a=dict(x=xa, n=n, p=pa, lo=la, hi=ua),
        b=dict(x=xb, n=n, p=pb, lo=lb, hi=ub),
        fisher_p=fp, diff=dd, diff_lo=dlo, diff_hi=dhi,
        per_family={f: dict(a=ba[f], b=bb[f]) for f in shared})

    # 5. first-replicate-only
    ra = [r for r in rows_a if r["replicate"] == 1]
    rb = [r for r in rows_b if r["replicate"] == 1]
    out["first_replicate_only"] = dict(
        definition="Only rows with replicate==1 (one run per family per arm). Removes any "
                   "weighting from unequal repeat depth; retains one row per arm, so n is "
                   "families x arms, not families.",
        stat="binomial (Wilson/Newcombe/Fisher)",
        **cmp_block(ra, rb, IS_PASS))

    # 6. depth-matched
    da, db = depth_matched(rows_a, rows_b)
    out["depth_matched"] = dict(
        definition="Per shared family, the first k=min(n_a,n_b) cells from each side ordered "
                   "by (arm, replicate, cell). Both sides then have identical family x depth "
                   "composition.",
        stat="binomial (Wilson/Newcombe/Fisher)",
        **cmp_block(da, db, IS_PASS))

    return out


def family_breakdown(rows_a, rows_b):
    fa = set(r["family"] for r in rows_a)
    fb = set(r["family"] for r in rows_b)
    out = []
    for f in sorted(fa | fb):
        A = [r for r in rows_a if r["family"] == f]
        B = [r for r in rows_b if r["family"] == f]
        ga = [r for r in A if r["graded"] == 1]
        gb = [r for r in B if r["graded"] == 1]
        rec = dict(family=f,
                   n_a=len(A), pass_a=sum(1 for r in A if r["passed"] == 1),
                   graded_a=len(ga), loop_a=sum(1 for r in A if r["looped_freq30"] == 1),
                   n_b=len(B), pass_b=sum(1 for r in B if r["passed"] == 1),
                   graded_b=len(gb), loop_b=sum(1 for r in B if r["looped_freq30"] == 1))
        rec["rate_a"] = rec["pass_a"] / rec["n_a"] if rec["n_a"] else None
        rec["rate_b"] = rec["pass_b"] / rec["n_b"] if rec["n_b"] else None
        rec["delta"] = (rec["rate_b"] - rec["rate_a"]) if (rec["rate_a"] is not None and rec["rate_b"] is not None) else None
        if rec["n_a"] and rec["n_b"]:
            rec["fisher_p"] = fisher_exact_two_sided(
                rec["pass_a"], rec["n_a"] - rec["pass_a"],
                rec["pass_b"], rec["n_b"] - rec["pass_b"])
        else:
            rec["fisher_p"] = None
        out.append(rec)
    return out


# --------------------------------------------------------------------------
# EFFORT LADDER (3.8 thinking only)
# --------------------------------------------------------------------------

def effort_ladder():
    out = []
    think38 = [r for r in ROWS if r["model"] == "3.8" and r["mode"] == "think"]
    for regime in [None, "T0.3/p0.8/pp0", "T1/p0.95/pp0"]:
        sel0 = think38 if regime is None else [r for r in think38 if r["regime"] == regime]
        for eff in ["low", "medium", "xhigh"]:
            sel = [r for r in sel0 if r["effort"] == eff]
            if not sel:
                continue
            graded = [r for r in sel if r["graded"] == 1]
            toks = [r["completion_tokens"] for r in sel if r["completion_tokens"] is not None]
            el = [r["elapsed_s"] for r in sel if r["elapsed_s"] is not None]
            pa = rate_block(sel, IS_PASS)
            pg = rate_block(graded, IS_PASS)
            out.append(dict(regime=regime or "ALL (pooled)", effort=eff, n=len(sel),
                            families=len(set(r["family"] for r in sel)),
                            n_graded=len(graded),
                            loop_freq30=sum(1 for r in sel if r["looped_freq30"] == 1),
                            pass_all=pa, pass_graded=pg,
                            median_tokens=median(toks), n_tokens=len(toks),
                            median_elapsed=median(el)))
    # pairwise low vs xhigh within each regime
    pw = []
    for regime in ["T0.3/p0.8/pp0", "T1/p0.95/pp0", None]:
        sel0 = think38 if regime is None else [r for r in think38 if r["regime"] == regime]
        for e1, e2 in [("low", "medium"), ("medium", "xhigh"), ("low", "xhigh")]:
            s1 = [r for r in sel0 if r["effort"] == e1]
            s2 = [r for r in sel0 if r["effort"] == e2]
            if not s1 or not s2:
                continue
            c = cmp_block(s1, s2, IS_PASS)
            pw.append(dict(regime=regime or "ALL (pooled)", lo=e1, hi=e2, **c))
    return out, pw


# --------------------------------------------------------------------------
# GRADER-DEFECT EXPOSURE
# --------------------------------------------------------------------------

def defect_exposure():
    """How much of each group's cell budget sits in a family with a verified
    grader defect. Numbers below are AS-GRADED; the overlay is separate."""
    out = {}
    for gid, g in GROUPS.items():
        rows = g["rows"]
        n = len(rows)
        d1 = [r for r in rows if r["family"] in LENGTH_GATED]
        d2 = [r for r in rows if r["family"] in PM]
        d3 = [r for r in rows if r["family"] in TRIAGE]
        out[gid] = dict(
            n=n,
            d1_length_gated=dict(n=len(d1), passes=sum(1 for r in d1 if r["passed"] == 1),
                                 graded=sum(1 for r in d1 if r["graded"] == 1)),
            d2_p3_pm=dict(n=len(d2), passes=sum(1 for r in d2 if r["passed"] == 1),
                          graded=sum(1 for r in d2 if r["graded"] == 1)),
            d3_p2_triage=dict(n=len(d3), passes=sum(1 for r in d3 if r["passed"] == 1),
                              graded=sum(1 for r in d3 if r["graded"] == 1)),
            union=dict(n=sum(1 for r in rows
                             if r["family"] in set(LENGTH_GATED) | set(TRIAGE)),
                       passes=sum(1 for r in rows
                                  if r["family"] in set(LENGTH_GATED) | set(TRIAGE)
                                  and r["passed"] == 1)))
    return out


def defect_free_subset():
    """Pass rate restricted to families with NO verified grader defect:
    everything except the 4 length-gated phase-3 families and p2_triage."""
    bad = set(LENGTH_GATED) | set(TRIAGE)
    clean = [f for f in FAMILIES if f not in bad]
    out = {}
    for pid, ga, gb, desc in PAIRS:
        ra = [r for r in GROUPS[ga]["rows"] if r["family"] in clean]
        rb = [r for r in GROUPS[gb]["rows"] if r["family"] in clean]
        out[pid] = dict(clean_families=clean, **cmp_block(ra, rb, IS_PASS))
    return out


# --------------------------------------------------------------------------
# POWER SCREEN
# --------------------------------------------------------------------------

def power_note(block):
    """Flag comparisons too imprecise to carry a claim.

    Rule applied uniformly: a comparison is reported as UNDERPOWERED if either
    arm has n < 30, or if the Newcombe 95% CI on the difference is wider than
    0.30 (30 percentage points) -- i.e. the interval cannot separate a small
    effect from a large one in either direction.
    """
    a, b = block.get("a", {}), block.get("b", {})
    na, nb = a.get("n", 0) or 0, b.get("n", 0) or 0
    lo, hi = block.get("diff_lo"), block.get("diff_hi")
    reasons = []
    if na < 30 or nb < 30:
        reasons.append("n<30 in an arm (n_a=%d, n_b=%d)" % (na, nb))
    if lo is not None and hi is not None and (hi - lo) > 0.30:
        reasons.append("Newcombe CI width %.1f pp" % (100 * (hi - lo)))
    straddles = (lo is not None and hi is not None and lo < 0 < hi)
    return dict(underpowered=bool(reasons), reasons=reasons, ci_straddles_zero=straddles)


# --------------------------------------------------------------------------
# BUILD
# --------------------------------------------------------------------------

R = OrderedDict()
_LOOP_BOTH = sum(1 for r in ROWS if r["looped_run30"] == 1 and r["looped_freq30"] == 1)
_LOOP_FREQ_ONLY = sum(1 for r in ROWS if r["looped_freq30"] == 1 and r["looped_run30"] == 0)
_LOOP_RUN_ONLY = sum(1 for r in ROWS if r["looped_run30"] == 1 and r["looped_freq30"] == 0)
_COST_MISSING = [r for r in ROWS if r["completion_tokens"] is None]
R["provenance"] = dict(
    source_csv=CSV_PATH,
    frozen_at=FROZEN_AT,
    n_cells=len(ROWS),
    seeds=sorted(set(r["seed"] for r in ROWS)),
    note="Model/quant/sampler identity taken verbatim from the frozen CSV, which sourced it "
         "from receipt.json. No live re-scan. No identity inferred from directory names.",
    columns_used=["family", "model", "quant", "mode", "effort", "regime", "replicate", "arm",
                  "graded", "passed", "terminal", "looped_freq30", "looped_run30",
                  "completion_tokens", "elapsed_s"],
    passed_semantics="passed==1 corresponds to verdict in {PASS, STRUCTURAL_PASS}; every "
                     "ungraded cell (graded==0) has passed==0.",
    loop_nesting="looped_run30==1 implies looped_freq30==1 (%d cells both, %d freq-only, "
                 "%d run-only)." % (_LOOP_BOTH, _LOOP_FREQ_ONLY, _LOOP_RUN_ONLY),
    loop_nesting_counts=dict(both=_LOOP_BOTH, freq_only=_LOOP_FREQ_ONLY,
                             run_only=_LOOP_RUN_ONLY),
    cost_missing=dict(n=len(_COST_MISSING),
                      all_ungraded=all(r["graded"] == 0 for r in _COST_MISSING)),
    depth_range=(lambda c: dict(min=min(c.values()), max=max(c.values())))(
        {(gid, r["family"]): sum(1 for x in g["rows"] if x["family"] == r["family"])
         for gid, g in GROUPS.items() for r in g["rows"]}),
)
R["groups"] = {gid: dict(label=g["label"], note=g["note"],
                         key=dict(zip(["model", "quant", "mode", "regime"], g["key"])),
                         **group_summary(g["rows"])) for gid, g in GROUPS.items()}

R["comparisons"] = OrderedDict()
for pid, ga, gb, desc in PAIRS:
    ra, rb = GROUPS[ga]["rows"], GROUPS[gb]["rows"]
    gra = [r for r in ra if r["graded"] == 1]
    grb = [r for r in rb if r["graded"] == 1]
    ent = dict(
        pair=[ga, gb], description=desc,
        label_a=GROUPS[ga]["label"], label_b=GROUPS[gb]["label"],
        delivery=dict(
            terminal=cmp_block(ra, rb, IS_TERMINAL),
            ungraded=cmp_block(ra, rb, IS_UNGRADED),
            loop_freq30=cmp_block(ra, rb, IS_LOOP_F),
            loop_run30=cmp_block(ra, rb, IS_LOOP_R)),
        quality=dict(
            pass_graded=cmp_block(gra, grb, IS_PASS),
            pass_all=cmp_block(ra, rb, IS_PASS)),
        family_breakdown=family_breakdown(ra, rb),
        cost=dict(
            tokens=cost_by_family(ra, rb, "completion_tokens"),
            elapsed=cost_by_family(ra, rb, "elapsed_s")),
        sensitivity=sensitivity(ra, rb),
    )
    shared = set(ent["cost"]["tokens"]["shared_families"])
    ent["cost"]["tokens_per_success_a"] = tokens_per_success(ra, shared)
    ent["cost"]["tokens_per_success_b"] = tokens_per_success(rb, shared)
    ent["power"] = dict(
        pass_all=power_note(ent["quality"]["pass_all"]),
        pass_graded=power_note(ent["quality"]["pass_graded"]),
        loop_freq30=power_note(ent["delivery"]["loop_freq30"]),
        loop_run30=power_note(ent["delivery"]["loop_run30"]),
        ungraded=power_note(ent["delivery"]["ungraded"]),
    )
    for sk, sv in ent["sensitivity"].items():
        if sv.get("diff_lo") is not None:
            ent["power"]["sens_" + sk] = power_note(sv)
    R["comparisons"][pid] = ent

ladder, ladder_pw = effort_ladder()
R["effort_ladder"] = dict(rows=ladder, pairwise=ladder_pw,
                          note="Effort is populated only for 3.8 thinking cells; all 3.6 cells "
                               "and all no-think cells have an empty effort field.")

# --- Q8 control ---
q8 = GROUPS["Q8"]["rows"]
q8_fams = set(r["family"] for r in q8)
a38 = GROUPS["A38"]["rows"]
a36 = GROUPS["A36"]["rows"]
a38m = [r for r in a38 if r["family"] in q8_fams]
a36m = [r for r in a36 if r["family"] in q8_fams]
Q8_GRADED = sum(1 for r in q8 if r["graded"] == 1)
Q8_TERMINAL = sum(1 for r in q8 if r["terminal"] == 1)
Q8_WITH_TOKENS = sum(1 for r in q8 if r["completion_tokens"] is not None)

OVERLAY_MANIFEST = "/home/michael/pr-staging/overlay/manifest.json"


def post_freeze_drift(q8_rows):
    """Post-freeze grading drift for the Q8_0 arm, read from the overlay
    manifest's post_freeze_divergence ledger (never from a live re-scan of the
    corpus, and never folded into any statistic -- disclosure only)."""
    try:
        with open(OVERLAY_MANIFEST) as fh:
            man = json.load(fh)
        div = man.get("post_freeze_divergence", [])
    except (OSError, ValueError):
        return None
    frozen = {r["cell"]: r["family"] for r in q8_rows}
    ent = [d for d in div if d.get("cell") in frozen]
    return dict(
        source=OVERLAY_MANIFEST,
        n_cells=len(ent),
        n_pass=sum(1 for d in ent if d.get("on_disk_verdict") == "PASS"),
        n_fail=sum(1 for d in ent if d.get("on_disk_verdict") == "FAIL"),
        cells=[dict(cell=d["cell"], family=frozen[d["cell"]],
                    on_disk_verdict=d.get("on_disk_verdict")) for d in ent],
        note="Verdicts written to disk AFTER the freeze; excluded from every "
             "number in this document and disclosed as drift.")


Q8_DRIFT = post_freeze_drift(q8)
q8_graded = [r for r in q8 if r["graded"] == 1]
a38m_graded = [r for r in a38m if r["graded"] == 1]
_q8_reps = defaultdict(int)
for r in q8:
    _q8_reps[r["family"]] += 1
R["quant_control"] = dict(
    note="Q8_0 arm at freeze #2 is %d cells over all %d families: 2 replicates on the "
         "%d phase-1/phase-2 families, 1 on the %d phase-3 families."
         % (len(q8), len(q8_fams),
            sum(1 for v in _q8_reps.values() if v == 2),
            sum(1 for v in _q8_reps.values() if v == 1)),
    quality_provisional=True,
    quality_note=(
        "%d of the %d Q8_0 cells are graded in the frozen CSV (freeze #2), so the arm "
        "now carries PROVISIONAL quality information: as-graded pass-given-delivery is "
        "%d/%d. The Wilson interval on that rate spans tens of percentage points, so no "
        "quality conclusion is drawn -- the graded outcomes are published as data, not "
        "as a quantization verdict. Delivery metrics (terminal, loop rates) cover all "
        "%d cells and are the arm's primary evidence."
        % (Q8_GRADED, len(q8), sum(1 for r in q8_graded if r["passed"] == 1),
           Q8_GRADED, len(q8))),
    n_graded=Q8_GRADED,
    n_pass_graded=sum(1 for r in q8_graded if r["passed"] == 1),
    n_fail_graded=sum(1 for r in q8_graded if r["passed"] == 0),
    n_terminal=Q8_TERMINAL,
    n_with_tokens=Q8_WITH_TOKENS,
    pass_graded=rate_block(q8_graded, IS_PASS),
    pass_all=rate_block(q8, IS_PASS),
    loop_freq30=rate_block(q8, IS_LOOP_F),
    loop_run30=rate_block(q8, IS_LOOP_R),
    post_freeze_drift=Q8_DRIFT,
    q8_families=sorted(q8_fams),
    reportable_metrics=["terminal", "looped_freq30", "looped_run30",
                        "completion_tokens", "elapsed_s",
                        "pass_graded (provisional, n=%d)" % Q8_GRADED],
    unscored_qualitative=dict(
        cell="p3_doc_qwen38q8-nothink-matched_v2",
        status="quarantined in-flight at freeze #2; NOT a row in the frozen CSV; "
               "excluded from every rate and every denominator in this document",
        observation="139 iterations rewriting brief.md, context grown to ~228k tokens "
                    "when quarantined",
        note="UNSCORED qualitative evidence only. It documents that the Q8_0 arm can "
             "also exhibit a rewrite-loop failure shape (distinct from the "
             "identical-call loop the loop metrics count); it carries no weight in any "
             "rate above and is not part of the loop_freq30/loop_run30 counts."),
    vs_38_q4_same_sampler=dict(
        comparator="A38 (3.8 Q4 no-think T0.3/p0.8/pp0) restricted to the %d Q8 families"
                   % len(q8_fams),
        loop_freq30=cmp_block(a38m, q8, IS_LOOP_F),
        loop_run30=cmp_block(a38m, q8, IS_LOOP_R),
        terminal=cmp_block(a38m, q8, IS_TERMINAL),
        pass_graded=dict(
            note="PROVISIONAL: graded-only pass rate, Q8 n=%d. Underpowered by the "
                 "power screen; direction only." % len(q8_graded),
            **cmp_block(a38m_graded, q8_graded, IS_PASS)),
        tokens=cost_by_family(a38m, q8, "completion_tokens"),
        elapsed=cost_by_family(a38m, q8, "elapsed_s")),
    vs_36_q4_same_sampler=dict(
        comparator="A36 (3.6 Q4 no-think T0.3/p0.8/pp0) restricted to the %d Q8 families"
                   % len(q8_fams),
        loop_freq30=cmp_block(a36m, q8, IS_LOOP_F),
        loop_run30=cmp_block(a36m, q8, IS_LOOP_R),
        terminal=cmp_block(a36m, q8, IS_TERMINAL),
        tokens=cost_by_family(a36m, q8, "completion_tokens"),
        elapsed=cost_by_family(a36m, q8, "elapsed_s")),
    q8_cells=[dict(cell=r["cell"], family=r["family"], replicate=r["replicate"],
                   verdict=r["verdict"],
                   graded=r["graded"], passed=r["passed"], terminal=r["terminal"],
                   loop_f=r["looped_freq30"], loop_r=r["looped_run30"],
                   tokens=r["completion_tokens"], elapsed=r["elapsed_s"]) for r in
              sorted(q8, key=lambda r: (r["family"], r["replicate"]))],
)

R["defect_exposure"] = defect_exposure()
R["defect_free_subset"] = defect_free_subset()

# family-level as-graded pass rates pooled by model, for the defect narrative
R["family_pass_asgraded"] = {}
for f in FAMILIES:
    rec = {}
    for m in ["3.6", "3.8"]:
        sel = [r for r in ROWS if r["family"] == f and r["model"] == m]
        g = [r for r in sel if r["graded"] == 1]
        rec[m] = dict(n=len(sel), graded=len(g), passes=sum(1 for r in sel if r["passed"] == 1))
    R["family_pass_asgraded"][f] = rec

# Everything above is pure computation. The WRITE is guarded so that importing
# this module (test_stats.py imports it for the estimators) cannot clobber
# results.json -- in particular it must not drop the defect_diagnostics block
# that defect_diag.py appends after this script runs.
# Pipeline order is: mmbt_results.py -> defect_diag.py -> make_md.py
if __name__ == "__main__":
    with open(OUT_JSON, "w") as fh:
        json.dump(R, fh, indent=2, sort_keys=False)

    print("wrote", OUT_JSON)
    print("cells:", len(ROWS))
    for pid, ga, gb, d in PAIRS:
        q = R["comparisons"][pid]["quality"]["pass_all"]
        print(pid, ga, gb, "pass_all %d/%d vs %d/%d  d=%+.3f [%.3f,%.3f] p=%.4g" % (
            q["a"]["x"], q["a"]["n"], q["b"]["x"], q["b"]["n"],
            q["diff"], q["diff_lo"], q["diff_hi"], q["fisher_p"]))
