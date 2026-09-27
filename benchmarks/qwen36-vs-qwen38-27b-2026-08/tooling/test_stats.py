#!/usr/bin/env python3
"""Validation of the pure-python estimators used for the MMBT results tables.

Each test checks an estimator against its DEFINING EQUATION or an exact
independent enumeration, not against a remembered published digit string.
"""
import itertools
import os
import math
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmbt_results import (wilson, fisher_exact_two_sided, newcombe_diff,
                          _hypergeom_pmf, median, z_diff_mean, Z)

fails = []


def ck(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("  " + detail if detail else ""))
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- Wilson
# DEFINING PROPERTY: the Wilson limits are the two roots p of
#     (p_hat - p)^2 = z^2 * p(1-p)/n
# So evaluating the score statistic at lo and at hi must return exactly z.
print("== Wilson: roots of the score equation ==")
for (x, n) in [(81, 121), (36, 72), (95, 120), (37, 81), (5, 11), (0, 11), (11, 11), (1, 100)]:
    p, lo, hi = wilson(x, n)
    ok = True
    detail = []
    for lim in (lo, hi):
        if lim <= 0 or lim >= 1:
            continue  # boundary root at 0 or 1 is degenerate
        score = abs(p - lim) / math.sqrt(lim * (1 - lim) / n)
        detail.append("%.10f" % score)
        if abs(score - Z) > 1e-9:
            ok = False
    ck("wilson %d/%d score==z at both limits" % (x, n), ok, "scores=" + ",".join(detail))

ck("wilson 0/11 lower bound is exactly 0", wilson(0, 11)[1] == 0.0)
ck("wilson 11/11 upper bound is exactly 1", wilson(11, 11)[2] == 1.0)
_viol = [(x, n) for n in range(1, 200) for x in range(n + 1)
         if not (wilson(x, n)[1] <= wilson(x, n)[0] <= wilson(x, n)[2])]
ck("wilson interval always brackets p_hat (exactly, incl. x=0 and x=n)",
   not _viol, "violations=%d %s" % (len(_viol), _viol[:5]))
ck("wilson never leaves [0,1]",
   all(0 <= wilson(x, n)[1] and wilson(x, n)[2] <= 1
       for n in range(1, 60) for x in range(n + 1)))

# ---------------------------------------------------------------- hypergeometric
print("\n== Hypergeometric pmf ==")
for (r1, r2, c1) in [(4, 4, 4), (121, 72, 117), (10, 12, 7), (81, 120, 60)]:
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    s = sum(_hypergeom_pmf(x, r1, r2, c1) for x in range(lo, hi + 1))
    ck("pmf sums to exactly 1 (r1=%d r2=%d c1=%d)" % (r1, r2, c1), s == 1, "sum=%s" % s)

# Independent brute-force: probability that a random c1-subset of r1+r2 labelled
# items contains exactly `a` items from group 1, counted by explicit enumeration.
print("\n== Hypergeometric vs brute-force enumeration ==")
r1, r2, c1 = 5, 6, 4
items = ["g1"] * r1 + ["g2"] * r2
counts = {}
tot = 0
for combo in itertools.combinations(range(r1 + r2), c1):
    a = sum(1 for i in combo if items[i] == "g1")
    counts[a] = counts.get(a, 0) + 1
    tot += 1
ok = all(abs(float(_hypergeom_pmf(a, r1, r2, c1)) - counts[a] / tot) < 1e-15 for a in counts)
ck("pmf matches enumeration over C(11,4) subsets", ok)

# ---------------------------------------------------------------- Fisher
print("\n== Fisher exact ==")
# Fisher's tea-tasting: 4 cups each way, 3 correct. Exact two-sided p = 17/35.
p_tea = fisher_exact_two_sided(3, 1, 1, 3)
ck("tea-tasting [[3,1],[1,3]] == 17/35", abs(p_tea - 17 / 35) < 1e-12,
   "got %.10f expected %.10f" % (p_tea, 17 / 35))
# Perfect separation 4/4 vs 0/4: only the two extreme tables are <= P(obs).
p_sep = fisher_exact_two_sided(4, 0, 0, 4)
ck("[[4,0],[0,4]] == 2/70", abs(p_sep - 2 / 70) < 1e-12, "got %.10f" % p_sep)
ck("identical rows give p == 1.0", abs(fisher_exact_two_sided(5, 5, 5, 5) - 1.0) < 1e-12)
ck("degenerate margin gives p == 1.0", fisher_exact_two_sided(0, 5, 0, 5) == 1.0)
ck("fisher is symmetric under row swap",
   all(abs(fisher_exact_two_sided(a, b, c, d) - fisher_exact_two_sided(c, d, a, b)) < 1e-12
       for a, b, c, d in [(8, 3, 2, 9), (81, 40, 36, 36), (1, 20, 7, 4)]))
ck("fisher is symmetric under column swap",
   all(abs(fisher_exact_two_sided(a, b, c, d) - fisher_exact_two_sided(b, a, d, c)) < 1e-12
       for a, b, c, d in [(8, 3, 2, 9), (81, 40, 36, 36), (1, 20, 7, 4)]))
ck("fisher p in (0,1] everywhere",
   all(0 < fisher_exact_two_sided(a, b, c, d) <= 1.0000000001
       for a in range(6) for b in range(6) for c in range(6) for d in range(6)))

# Large-sample agreement with the chi-square approximation (no scipy: compare the
# chi-square statistic's normal tail via erfc, which is in the stdlib).
def chisq_p(a, b, c, d):
    n = a + b + c + d
    num = n * (a * d - b * c) ** 2
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        return 1.0
    x2 = num / den
    return math.erfc(math.sqrt(x2 / 2.0))  # 2-sided normal tail, chi2_1 = Z^2

for (a, b, c, d) in [(400, 200, 350, 250), (81, 40, 36, 36), (300, 300, 260, 340)]:
    pf = fisher_exact_two_sided(a, b, c, d)
    pc = chisq_p(a, b, c, d)
    ck("fisher ~ chi-square at large n [[%d,%d],[%d,%d]]" % (a, b, c, d),
       abs(math.log10(pf) - math.log10(pc)) < 0.35,
       "fisher=%.5g chisq=%.5g" % (pf, pc))

# ---------------------------------------------------------------- Newcombe
print("\n== Newcombe method 10 ==")
# DEFINING PROPERTY: built from the two Wilson intervals via
#   lower = (p1-p2) - sqrt((p1-l1)^2 + (u2-p2)^2)
#   upper = (p1-p2) + sqrt((u1-p1)^2 + (p2-l2)^2)
for (x1, n1, x2, n2) in [(36, 72, 81, 121), (37, 81, 95, 120), (5, 11, 5, 11), (0, 20, 20, 20)]:
    p1, l1, u1 = wilson(x1, n1)
    p2, l2, u2 = wilson(x2, n2)
    exp_lo = (p1 - p2) - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    exp_hi = (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    d, lo, hi = newcombe_diff(x1, n1, x2, n2)
    ck("newcombe %d/%d - %d/%d matches construction" % (x1, n1, x2, n2),
       abs(d - (p1 - p2)) < 1e-12 and abs(lo - max(-1.0, exp_lo)) < 1e-12
       and abs(hi - min(1.0, exp_hi)) < 1e-12)

ck("newcombe brackets the point difference",
   all(newcombe_diff(x1, 40, x2, 50)[1] <= newcombe_diff(x1, 40, x2, 50)[0]
       <= newcombe_diff(x1, 40, x2, 50)[2] for x1 in range(0, 41, 5) for x2 in range(0, 51, 5)))
ck("newcombe antisymmetric under group swap",
   all(abs(newcombe_diff(a, 40, b, 50)[0] + newcombe_diff(b, 50, a, 40)[0]) < 1e-12
       and abs(newcombe_diff(a, 40, b, 50)[1] + newcombe_diff(b, 50, a, 40)[2]) < 1e-12
       for a in (0, 7, 20, 40) for b in (0, 13, 25, 50)))
ck("newcombe stays in [-1,1]",
   all(-1 <= newcombe_diff(x1, 30, x2, 30)[1] and newcombe_diff(x1, 30, x2, 30)[2] <= 1
       for x1 in range(31) for x2 in range(31)))
# Newcombe CI excluding 0 should broadly track a significant Fisher p.
agree = 0
tot = 0
for x1 in range(0, 41, 2):
    for x2 in range(0, 41, 2):
        d, lo, hi = newcombe_diff(x1, 40, x2, 40)
        pf = fisher_exact_two_sided(x1, 40 - x1, x2, 40 - x2)
        tot += 1
        if (lo > 0 or hi < 0) == (pf < 0.05):
            agree += 1
ck("newcombe zero-exclusion agrees with Fisher p<0.05 (>=90% of grid)",
   agree / tot >= 0.90, "agreement=%.3f over %d tables" % (agree / tot, tot))

# ---------------------------------------------------------------- misc
print("\n== median / z-interval on difference of means ==")
ck("median odd", median([3, 1, 2]) == 2.0)
ck("median even", median([4, 1, 2, 3]) == 2.5)
ck("median empty is None", median([]) is None)
ck("z_diff_mean on identical samples gives d=0", abs(z_diff_mean([1, 0, 1, 0], [1, 0, 1, 0])[0]) < 1e-12)
ck("z_diff_mean too-small sample returns None", z_diff_mean([1], [0])[0] is None)

print("\n%d checks failed" % len(fails))
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL VALIDATION CHECKS PASSED")
