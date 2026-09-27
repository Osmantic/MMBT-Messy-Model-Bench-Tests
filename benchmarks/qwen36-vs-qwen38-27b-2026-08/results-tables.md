# Qwen3.6-27B vs Qwen3.8-27B — Definitive Results Tables

All numbers below are computed from the frozen dataset
`/home/michael/mmbt-frozen-dataset-v2.csv` (802 cells, frozen 2026-08-16T14:23:09Z).
No live re-scan was used for any figure. Model, quantization and sampler identity are taken
verbatim from the frozen CSV, which sourced them from each run's `receipt.json` — never from
directory names.

**Reproduce:** `python3 mmbt_results.py` writes `results.json`; `python3 make_md.py` renders
this file; `python3 test_stats.py` validates the estimators. No third-party dependencies.

### Reading these tables

- **Sign convention.** Every delta in this document is arithmetically **3.8 minus 3.6**,
  applied identically to every table. Note that this means the *direction of badness flips
  with the metric*: for good-direction metrics (terminal rate, pass rate) a **negative** delta
  means 3.8 is worse, while for bad-direction metrics (ungraded rate, loop rate) a
  **positive** delta means 3.8 is worse. Each table states which metric it reports.
- **Every rate carries its denominator** as `x/n`.
- **CIs** are Wilson 95% score intervals for single proportions and Newcombe 95% hybrid-score
  intervals for differences. `p` is a two-sided Fisher exact test. All three are implemented
  from scratch in pure python; formulas are in the appendix and in the source comments.
- **\*** marks `p < 0.05`. No multiplicity correction is applied — with 4 comparison
  families and 7 scorings each, treat isolated marginal results with suspicion.
- `passed == 1` means verdict in {PASS, STRUCTURAL_PASS}. **Every ungraded cell has
  `passed == 0`**, so an all-cells pass rate silently merges "graded and failed" with
  "never produced a gradeable artifact". Both components are reported separately.

---

## Headline

**1. The one large, unambiguous effect is a delivery regression in no-think mode, not a
quality regression.** 3.8's loop rate is +28.0 pp (4.9e-09) at the matched sampler and +29.2 pp (1.1e-11) at each
model's own vendor sampler. This is measured upstream of grading, so no scoring choice, and
none of the three grader defects, can touch it.

**2. That regression disappears in thinking mode.** Loop rate falls to 2/51 (T0.3) and 0/72
(T1/p0.95/pp0) for 3.8, neither distinguishable from 3.6.

**3. Conditional on delivering, 3.8 is not clearly worse at the matched no-think sampler.**
All-cells pass rate is -13.3 pp (0.05052) but graded-only is +7.4 pp (0.2959) — the sign flips. "3.8 is worse at the task"
is **not** a supportable summary of this corpus; "3.8 fails more often by not finishing" is.

**4. Thinking mode costs ~2.2–3.0× more tokens on 3.8 with no pass-rate gain**, and 3.8's
effort ladder buys tokens rather than quality (no effort step is significant).

**5. Two things reported here are provisional at best and are labelled as such:** the Q8_0
quantization arm (8 of 19 cells graded at freeze #2 — enough for provisional loop and
graded-outcome rates with wide intervals, not enough for any quality verdict, §6) and every
`best_of_n` / `first_replicate` row (n = 12, §9).

Full robustness accounting is in §7; what the data cannot support is in §9.

---

## 0. Group inventory and missing-data structure

| Group | Definition | Cells | Families | Graded | Graded+failed | Ungraded (looped) | Ungraded (no loop) | Graded despite loop |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `A36` | 3.6 no-think T0.3/p0.8/pp0 | 121 | 12 | 114 | 33 | 3 | 4 | 0 |
| `A38` | 3.8 no-think T0.3/p0.8/pp0 | 95 | 12 | 65 | 14 | 25 | 5 | 4 |
| `V36` | 3.6 no-think T1/p0.95/pp0 | 120 | 12 | 120 | 25 | 0 | 0 | 0 |
| `V38` | 3.8 no-think T0.7/p0.8/pp1.5 | 96 | 12 | 79 | 31 | 13 | 4 | 15 |
| `B36` | 3.6 think T0.3/p0.8/pp0 | 108 | 12 | 107 | 40 | 1 | 0 | 0 |
| `B38` | 3.8 think T0.3/p0.8/pp0 | 51 | 12 | 48 | 15 | 2 | 1 | 0 |
| `C36` | 3.6 think T1/p0.95/pp0 | 120 | 12 | 120 | 15 | 0 | 0 | 0 |
| `C38` | 3.8 think T1/p0.95/pp0 | 72 | 12 | 72 | 18 | 0 | 0 | 0 |
| `Q8` | 3.8 Q8_0 no-think T0.3/p0.8/pp0 | 19 | 12 | 8 | 3 | 6 | 5 | 0 |

Notes on group composition, which matter for how much weight each comparison can carry:

- **`A36`** — 3.6 no-think T0.3/p0.8/pp0. *off-spec for 3.6 (its card is T1/p0.95/pp0); sampler-matched to A38*  Arms pooled: `qwen36-27b-udq4xl-t03-nothink`, `qwen36-nothink-offspec`.
- **`A38`** — 3.8 no-think T0.3/p0.8/pp0. *off-spec for 3.8 (its card is T0.7/p0.8/pp1.5); sampler-matched to A36*  Arms pooled: `qwen38-27b-udq4xl-t03-nothink`, `qwen38-nothink-offspec`.
- **`V36`** — 3.6 no-think T1/p0.95/pp0. *3.6 VENDOR point*  Arms pooled: `qwen36-nothink-card`.
- **`V38`** — 3.8 no-think T0.7/p0.8/pp1.5. *3.8 VENDOR point*  Arms pooled: `qwen38-27b-udq4xl-nothink`, `qwen38-nothink-card`.
- **`B36`** — 3.6 think T0.3/p0.8/pp0. *off-spec for 3.6; sampler-matched to B38*  Arms pooled: `qwen36-think-offspec`.
- **`B38`** — 3.8 think T0.3/p0.8/pp0. *off-spec for 3.8; sampler-matched to B36; MIXED effort (low/medium/xhigh)*  Arms pooled: `qwen38-think-low-offspec`, `qwen38-think-medium-offspec`, `qwen38-think-xhigh-offspec`.
- **`C36`** — 3.6 think T1/p0.95/pp0. *3.6 VENDOR point*  Arms pooled: `qwen36-think-card`.
- **`C38`** — 3.8 think T1/p0.95/pp0. *this is 3.6's vendor point, NOT 3.8's; sampler-matched to C36 but off-spec for 3.8; MIXED effort (low/medium/xhigh)*  Arms pooled: `qwen38-27b-udq4xl-think-xhigh`, `qwen38-think-low-card`, `qwen38-think-medium-card`, `qwen38-think-xhigh-card`.
- **`Q8`** — 3.8 Q8_0 no-think T0.3/p0.8/pp0. *quantization control; 19 cells over all 12 families (2 replicates on the 7 phase-1/2 families, 1 on the 5 phase-3)*  Arms pooled: `qwen38q8-nothink-matched`.

All 802 runs used **seed 42**. Replicates are therefore repeated runs at a *fixed* seed, not
a seed sweep; within-arm variation reflects server/batching nondeterminism, not sampled seeds.
This limits how far replicate counts can be read as independent draws.

---

## 1. Delivery reliability

Loop detection is reported under both available metrics. `looped_run30` is strictly nested
inside `looped_freq30` across the whole corpus (47 cells flagged by both, 22 by frequency
only, 0 by run only), so `freq30` is the more inclusive detector and `run30` the stricter one.

### 1a. Per-group delivery rates (Wilson 95% CI)

| Group | n | Terminal | Ungraded | Loop (freq30) | Loop (run30) |
|---|---:|---|---|---|---|
| `A36` | 121 | 118/121 97.5% [93.0, 99.2] | 7/121 5.8% [2.8, 11.5] | 3/121 2.5% [0.8, 7.0] | 3/121 2.5% [0.8, 7.0] |
| `A38` | 95 | 93/95 97.9% [92.6, 99.4] | 30/95 31.6% [23.1, 41.5] | 29/95 30.5% [22.2, 40.4] | 23/95 24.2% [16.7, 33.7] |
| `V36` | 120 | 120/120 100.0% [96.9, 100.0] | 0/120 0.0% [0.0, 3.1] | 0/120 0.0% [0.0, 3.1] | 0/120 0.0% [0.0, 3.1] |
| `V38` | 96 | 96/96 100.0% [96.2, 100.0] | 17/96 17.7% [11.4, 26.5] | 28/96 29.2% [21.0, 38.9] | 13/96 13.5% [8.1, 21.8] |
| `B36` | 108 | 108/108 100.0% [96.6, 100.0] | 1/108 0.9% [0.2, 5.1] | 1/108 0.9% [0.2, 5.1] | 1/108 0.9% [0.2, 5.1] |
| `B38` | 51 | 50/51 98.0% [89.7, 99.7] | 3/51 5.9% [2.0, 15.9] | 2/51 3.9% [1.1, 13.2] | 2/51 3.9% [1.1, 13.2] |
| `C36` | 120 | 120/120 100.0% [96.9, 100.0] | 0/120 0.0% [0.0, 3.1] | 0/120 0.0% [0.0, 3.1] | 0/120 0.0% [0.0, 3.1] |
| `C38` | 72 | 72/72 100.0% [94.9, 100.0] | 0/72 0.0% [0.0, 5.1] | 0/72 0.0% [0.0, 5.1] | 0/72 0.0% [0.0, 5.1] |
| `Q8` | 19 | 19/19 100.0% [83.2, 100.0] | 11/19 57.9% [36.3, 76.9] | 6/19 31.6% [15.4, 54.0] | 5/19 26.3% [11.8, 48.8] |

### 1b. Paired 3.6-vs-3.8 delivery contrasts

**P1 — No-think, SAMPLER-MATCHED (both T0.3/p0.8/pp0). Off-spec for both models; the cleanest controlled-sampler contrast.**

| Metric | 3.6 `A36` | 3.8 `A38` | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| Terminal | 118/121 97.5% [93.0, 99.2] | 93/95 97.9% [92.6, 99.4] | +0.4 pp | [-5.1, 5.2] | 1 |
| Ungraded | 7/121 5.8% [2.8, 11.5] | 30/95 31.6% [23.1, 41.5] | +25.8 pp | [15.6, 36.1] | 8.2e-07 **\*** |
| Loop (freq30) | 3/121 2.5% [0.8, 7.0] | 29/95 30.5% [22.2, 40.4] | +28.0 pp | [18.5, 38.0] | 4.9e-09 **\*** |
| Loop (run30) | 3/121 2.5% [0.8, 7.0] | 23/95 24.2% [16.7, 33.7] | +21.7 pp | [13.0, 31.4] | 8.7e-07 **\*** |

**P2 — No-think, VENDOR-MATCHED (each model at its own model-card sampler: 3.6 T1/p0.95/pp0, 3.8 T0.7/p0.8/pp1.5). Best-foot-forward contrast; sampler differs by construction.**

| Metric | 3.6 `V36` | 3.8 `V38` | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| Terminal | 120/120 100.0% [96.9, 100.0] | 96/96 100.0% [96.2, 100.0] | +0.0 pp | [-3.8, 3.1] | 1 |
| Ungraded | 0/120 0.0% [0.0, 3.1] | 17/96 17.7% [11.4, 26.5] | +17.7 pp | [10.6, 26.5] | 4.4e-07 **\*** |
| Loop (freq30) | 0/120 0.0% [0.0, 3.1] | 28/96 29.2% [21.0, 38.9] | +29.2 pp | [20.4, 38.9] | 1.1e-11 **\*** |
| Loop (run30) | 0/120 0.0% [0.0, 3.1] | 13/96 13.5% [8.1, 21.8] | +13.5 pp | [7.3, 21.8] | 1.6e-05 **\*** |

**P3 — Thinking, SAMPLER-MATCHED (both T0.3/p0.8/pp0). Off-spec for both. 3.8 side pools three effort levels.**

| Metric | 3.6 `B36` | 3.8 `B38` | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| Terminal | 108/108 100.0% [96.6, 100.0] | 50/51 98.0% [89.7, 99.7] | -2.0 pp | [-10.3, 1.8] | 0.3208 |
| Ungraded | 1/108 0.9% [0.2, 5.1] | 3/51 5.9% [2.0, 15.9] | +5.0 pp | [-0.7, 15.0] | 0.09748 |
| Loop (freq30) | 1/108 0.9% [0.2, 5.1] | 2/51 3.9% [1.1, 13.2] | +3.0 pp | [-2.0, 12.3] | 0.2412 |
| Loop (run30) | 1/108 0.9% [0.2, 5.1] | 2/51 3.9% [1.1, 13.2] | +3.0 pp | [-2.0, 12.3] | 0.2412 |

**P4 — Thinking at T1/p0.95/pp0. Sampler-matched, but that triple is 3.6's vendor point and is NOT 3.8's -- 3.8 is running off-spec here and this pair is biased in 3.6's favour. 3.8 side pools three effort levels.**

| Metric | 3.6 `C36` | 3.8 `C38` | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| Terminal | 120/120 100.0% [96.9, 100.0] | 72/72 100.0% [94.9, 100.0] | +0.0 pp | [-5.1, 3.1] | 1 |
| Ungraded | 0/120 0.0% [0.0, 3.1] | 0/72 0.0% [0.0, 5.1] | +0.0 pp | [-3.1, 5.1] | 1 |
| Loop (freq30) | 0/120 0.0% [0.0, 3.1] | 0/72 0.0% [0.0, 5.1] | +0.0 pp | [-3.1, 5.1] | 1 |
| Loop (run30) | 0/120 0.0% [0.0, 3.1] | 0/72 0.0% [0.0, 5.1] | +0.0 pp | [-3.1, 5.1] | 1 |

---

## 2. Quality

Two pass rates are reported for every pair because they answer different questions:

- **All-cells** (loops count as failure) — *how often does a run of this model produce a
  passing deliverable?* This is the end-to-end number.
- **Graded-only** — *given that a run produced something gradeable, how good was it?* This
  discards every delivery failure and is maximally charitable to a model that fails by
  not delivering.

Where these two disagree, the disagreement **is** the finding.

**P1 — 3.6 no-think T0.3/p0.8/pp0 vs 3.8 no-think T0.3/p0.8/pp0**

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| All cells (loops = fail) | 81/121 66.9% [58.2, 74.7] | 51/95 53.7% [43.7, 63.4] | -13.3 pp | [-25.9, -0.2] | 0.05052 |
| Graded only | 81/114 71.1% [62.1, 78.6] | 51/65 78.5% [67.0, 86.7] | +7.4 pp | [-6.3, 19.5] | 0.2959 |

**P2 — 3.6 no-think T1/p0.95/pp0 vs 3.8 no-think T0.7/p0.8/pp1.5**

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| All cells (loops = fail) | 95/120 79.2% [71.1, 85.5] | 48/96 50.0% [40.2, 59.8] | -29.2 pp | [-40.8, -16.4] | 1.1e-05 **\*** |
| Graded only | 95/120 79.2% [71.1, 85.5] | 48/79 60.8% [49.7, 70.8] | -18.4 pp | [-31.1, -5.5] | 0.006102 **\*** |

**P3 — 3.6 think T0.3/p0.8/pp0 vs 3.8 think T0.3/p0.8/pp0**

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| All cells (loops = fail) | 67/108 62.0% [52.6, 70.6] | 33/51 64.7% [51.0, 76.4] | +2.7 pp | [-13.5, 17.7] | 0.8607 |
| Graded only | 67/107 62.6% [53.2, 71.2] | 33/48 68.8% [54.7, 80.1] | +6.1 pp | [-10.4, 20.9] | 0.5863 |

**P4 — 3.6 think T1/p0.95/pp0 vs 3.8 think T1/p0.95/pp0**

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| All cells (loops = fail) | 105/120 87.5% [80.4, 92.3] | 54/72 75.0% [63.9, 83.6] | -12.5 pp | [-24.6, -1.4] | 0.03081 **\*** |
| Graded only | 105/120 87.5% [80.4, 92.3] | 54/72 75.0% [63.9, 83.6] | -12.5 pp | [-24.6, -1.4] | 0.03081 **\*** |

---

## 3. Per-family breakdown

All-cells pass rate (loops count as failure), with graded and loop counts so any cell can be
re-derived. `g` = graded cells, `L` = cells flagged by `looped_freq30`.

### P1 — 3.6 no-think T0.3/p0.8/pp0 vs 3.8 no-think T0.3/p0.8/pp0

| Family | 3.6 pass/n (g, L) | 3.6 rate | 3.8 pass/n (g, L) | 3.8 rate | Δ (3.8−3.6) | Fisher p |
|---|---|---:|---|---:|---:|---:|
| `p1_bugfix` | 18/19 (g=18, L=0) | 94.7% | 0/12 (g=1, L=10) | 0.0% | -94.7 pp | 9.2e-08 **\*** |
| `p1_refactor` | 5/9 (g=9, L=0) | 55.6% | 3/7 (g=5, L=1) | 42.9% | -12.7 pp | 1 |
| `p1_testwrite` | 9/12 (g=10, L=0) | 75.0% | 0/13 (g=2, L=10) | 0.0% | -75.0 pp | 0.00011 **\*** |
| `p2_ci` | 9/9 (g=9, L=0) | 100.0% | 7/7 (g=7, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_extract` | 9/9 (g=9, L=0) | 100.0% | 7/7 (g=7, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_hallucination` | 9/9 (g=9, L=0) | 100.0% | 7/7 (g=7, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_triage` | 0/9 (g=9, L=0) | 0.0% | 7/7 (g=7, L=0) | 100.0% | +100.0 pp | 8.7e-05 **\*** |
| `p3_business` | 7/9 (g=9, L=0) | 77.8% | 0/7 (g=6, L=1) | 0.0% | -77.8 pp | 0.003234 **\*** |
| `p3_doc` | 8/9 (g=9, L=0) | 88.9% | 6/7 (g=6, L=1) | 85.7% | -3.2 pp | 1 |
| `p3_market` | 4/9 (g=5, L=3) | 44.4% | 0/7 (g=3, L=6) | 0.0% | -44.4 pp | 0.08846 |
| `p3_pm` | 1/9 (g=9, L=0) | 11.1% | 7/7 (g=7, L=0) | 100.0% | +88.9 pp | 0.001399 **\*** |
| `p3_writing` | 2/9 (g=9, L=0) | 22.2% | 7/7 (g=7, L=0) | 100.0% | +77.8 pp | 0.003234 **\*** |

Per-family n is 7–19 per side, so **no single family row is individually conclusive**;
they are provided so the pooled numbers can be audited, not to support family-level claims.

### P2 — 3.6 no-think T1/p0.95/pp0 vs 3.8 no-think T0.7/p0.8/pp1.5

| Family | 3.6 pass/n (g, L) | 3.6 rate | 3.8 pass/n (g, L) | 3.8 rate | Δ (3.8−3.6) | Fisher p |
|---|---|---:|---|---:|---:|---:|
| `p1_bugfix` | 10/10 (g=10, L=0) | 100.0% | 4/8 (g=4, L=5) | 50.0% | -50.0 pp | 0.02288 **\*** |
| `p1_refactor` | 8/10 (g=10, L=0) | 80.0% | 4/8 (g=8, L=3) | 50.0% | -30.0 pp | 0.3213 |
| `p1_testwrite` | 9/10 (g=10, L=0) | 90.0% | 0/8 (g=7, L=7) | 0.0% | -90.0 pp | 0.00041 **\*** |
| `p2_ci` | 10/10 (g=10, L=0) | 100.0% | 8/8 (g=8, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_extract` | 10/10 (g=10, L=0) | 100.0% | 8/8 (g=8, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_hallucination` | 10/10 (g=10, L=0) | 100.0% | 8/8 (g=8, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_triage` | 7/10 (g=10, L=0) | 70.0% | 5/8 (g=8, L=0) | 62.5% | -7.5 pp | 1 |
| `p3_business` | 10/10 (g=10, L=0) | 100.0% | 2/8 (g=6, L=3) | 25.0% | -75.0 pp | 0.001508 **\*** |
| `p3_doc` | 10/10 (g=10, L=0) | 100.0% | 1/8 (g=8, L=0) | 12.5% | -87.5 pp | 0.00025 **\*** |
| `p3_market` | 10/10 (g=10, L=0) | 100.0% | 0/8 (g=2, L=5) | 0.0% | -100.0 pp | 2.3e-05 **\*** |
| `p3_pm` | 1/10 (g=10, L=0) | 10.0% | 8/8 (g=8, L=0) | 100.0% | +90.0 pp | 0.00041 **\*** |
| `p3_writing` | 0/10 (g=10, L=0) | 0.0% | 0/8 (g=4, L=5) | 0.0% | +0.0 pp | 1 |

Per-family n is 8–10 per side, so **no single family row is individually conclusive**;
they are provided so the pooled numbers can be audited, not to support family-level claims.

### P3 — 3.6 think T0.3/p0.8/pp0 vs 3.8 think T0.3/p0.8/pp0

| Family | 3.6 pass/n (g, L) | 3.6 rate | 3.8 pass/n (g, L) | 3.8 rate | Δ (3.8−3.6) | Fisher p |
|---|---|---:|---|---:|---:|---:|
| `p1_bugfix` | 9/9 (g=9, L=0) | 100.0% | 4/6 (g=5, L=0) | 66.7% | -33.3 pp | 0.1429 |
| `p1_refactor` | 4/9 (g=9, L=0) | 44.4% | 3/4 (g=4, L=0) | 75.0% | +30.6 pp | 0.5594 |
| `p1_testwrite` | 9/9 (g=9, L=0) | 100.0% | 4/5 (g=5, L=0) | 80.0% | -20.0 pp | 0.3571 |
| `p2_ci` | 9/9 (g=9, L=0) | 100.0% | 4/4 (g=4, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_extract` | 9/9 (g=9, L=0) | 100.0% | 4/4 (g=4, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_hallucination` | 9/9 (g=9, L=0) | 100.0% | 4/4 (g=4, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_triage` | 0/9 (g=9, L=0) | 0.0% | 4/4 (g=4, L=0) | 100.0% | +100.0 pp | 0.001399 **\*** |
| `p3_business` | 8/9 (g=9, L=0) | 88.9% | 2/4 (g=4, L=0) | 50.0% | -38.9 pp | 0.2028 |
| `p3_doc` | 0/9 (g=9, L=0) | 0.0% | 1/4 (g=4, L=0) | 25.0% | +25.0 pp | 0.3077 |
| `p3_market` | 8/9 (g=8, L=1) | 88.9% | 1/4 (g=2, L=2) | 25.0% | -63.9 pp | 0.05175 |
| `p3_pm` | 0/9 (g=9, L=0) | 0.0% | 1/4 (g=4, L=0) | 25.0% | +25.0 pp | 0.3077 |
| `p3_writing` | 2/9 (g=9, L=0) | 22.2% | 1/4 (g=4, L=0) | 25.0% | +2.8 pp | 1 |

Per-family n is 4–9 per side, so **no single family row is individually conclusive**;
they are provided so the pooled numbers can be audited, not to support family-level claims.

### P4 — 3.6 think T1/p0.95/pp0 vs 3.8 think T1/p0.95/pp0

| Family | 3.6 pass/n (g, L) | 3.6 rate | 3.8 pass/n (g, L) | 3.8 rate | Δ (3.8−3.6) | Fisher p |
|---|---|---:|---|---:|---:|---:|
| `p1_bugfix` | 10/10 (g=10, L=0) | 100.0% | 6/6 (g=6, L=0) | 100.0% | +0.0 pp | 1 |
| `p1_refactor` | 7/10 (g=10, L=0) | 70.0% | 6/6 (g=6, L=0) | 100.0% | +30.0 pp | 0.25 |
| `p1_testwrite` | 9/10 (g=10, L=0) | 90.0% | 6/6 (g=6, L=0) | 100.0% | +10.0 pp | 1 |
| `p2_ci` | 10/10 (g=10, L=0) | 100.0% | 6/6 (g=6, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_extract` | 10/10 (g=10, L=0) | 100.0% | 6/6 (g=6, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_hallucination` | 10/10 (g=10, L=0) | 100.0% | 6/6 (g=6, L=0) | 100.0% | +0.0 pp | 1 |
| `p2_triage` | 10/10 (g=10, L=0) | 100.0% | 6/6 (g=6, L=0) | 100.0% | +0.0 pp | 1 |
| `p3_business` | 10/10 (g=10, L=0) | 100.0% | 0/6 (g=6, L=0) | 0.0% | -100.0 pp | 0.00012 **\*** |
| `p3_doc` | 10/10 (g=10, L=0) | 100.0% | 1/6 (g=6, L=0) | 16.7% | -83.3 pp | 0.001374 **\*** |
| `p3_market` | 10/10 (g=10, L=0) | 100.0% | 6/6 (g=6, L=0) | 100.0% | +0.0 pp | 1 |
| `p3_pm` | 2/10 (g=10, L=0) | 20.0% | 5/6 (g=6, L=0) | 83.3% | +63.3 pp | 0.03497 **\*** |
| `p3_writing` | 7/10 (g=10, L=0) | 70.0% | 0/6 (g=6, L=0) | 0.0% | -70.0 pp | 0.01136 **\*** |

Per-family n is 6–10 per side, so **no single family row is individually conclusive**;
they are provided so the pooled numbers can be audited, not to support family-level claims.

---

## 4. Cost, matched by family

**Why family matching is mandatory here.** Task families differ in cost by more than an order
of magnitude (`p2_extract` ~2.5k tokens vs `p1_bugfix` ~35k). Two groups with different family
mixes produce medians that can be ordered either way at will. Earlier in this project exactly
that produced two contradictory cost claims from the same corpus. Every figure below is
computed per family first.

**A second, subtler trap.** `completion_tokens` is missing for exactly the cells that were
never graded, and looping is the dominant cause of that. Missingness is therefore *not*
random — it is concentrated in the runs that would have been most expensive. A family is
counted as **cost-comparable** only when both sides retain ≥3 cells with cost data *and*
≥50% coverage of that side's cells in the family. Non-comparable families are shown but
excluded from the summary ratio.

### P1 — 3.6 no-think T0.3/p0.8/pp0 vs 3.8 no-think T0.3/p0.8/pp0

Token-data coverage: 3.6 94% (114/121 cells) · 3.8 68% (65/95 cells). Cost-comparable families: **9 of 12**.  Excluded: `p1_bugfix`, `p1_testwrite`, `p3_market`.

| Family | 3.6 med tok (n) | 3.8 med tok (n) | tok ratio | 3.6 med s | 3.8 med s | s ratio | comparable |
|---|---:|---:|---:|---:|---:|---:|:--:|
| `p1_bugfix` | 31,183 (18) | 102,609 (1) | 3.29 | 894.2 (18) | 4,860.3 (1) | 5.44 | **no** |
| `p1_refactor` | 11,033 (9) | 11,468 (5) | 1.04 | 212.7 (9) | 195.0 (5) | 0.92 | yes |
| `p1_testwrite` | 36,840 (10) | 30,596 (2) | 0.83 | 638.1 (10) | 684.0 (2) | 1.07 | **no** |
| `p2_ci` | 4,600 (9) | 3,748 (7) | 0.81 | 82.6 (9) | 71.7 (7) | 0.87 | yes |
| `p2_extract` | 2,871 (9) | 2,666 (7) | 0.93 | 45.5 (9) | 42.8 (7) | 0.94 | yes |
| `p2_hallucination` | 5,101 (9) | 4,377 (7) | 0.86 | 83.1 (9) | 72.4 (7) | 0.87 | yes |
| `p2_triage` | 7,707 (9) | 6,289 (7) | 0.82 | 118.3 (9) | 97.0 (7) | 0.82 | yes |
| `p3_business` | 9,503 (9) | 10,344 (6) | 1.09 | 146.3 (9) | 157.9 (6) | 1.08 | yes |
| `p3_doc` | 7,801 (9) | 7,108 (6) | 0.91 | 120.1 (9) | 108.5 (6) | 0.90 | yes |
| `p3_market` | 40,432 (5) | 103,162 (3) | 2.55 | 943.4 (5) | 2,914.9 (3) | 3.09 | **no** |
| `p3_pm` | 4,634 (9) | 3,308 (7) | 0.71 | 71.5 (9) | 50.7 (7) | 0.71 | yes |
| `p3_writing` | 6,427 (9) | 4,927 (7) | 0.77 | 104.0 (9) | 77.4 (7) | 0.74 | yes |

**Median of per-family ratios (comparable families only): tokens ×0.86, wall-clock ×0.87.**

> ⚠️ **The excluded families are the expensive ones.** Median 3.6 cost is 36,840 tokens
> across the excluded families versus 6,427 across the retained ones (×5.7). Because
> cost data goes missing exactly when a run loops, and 3.8 loops most on the
> long-horizon families, the ×0.86 summary ratio above is computed over the *cheap*
> tail of the task set. **It must not be read as "3.8 is cheaper overall"** — the
> comparison is silent on precisely the families where 3.8's cost would be worst.

| Tokens per successful deliverable | 3.6 | 3.8 |
|---|---:|---:|
| Total completion tokens recorded | 1,680,139 | 815,989 |
| Cells with token data | 114/121 | 65/95 |
| Passing cells | 81 | 51 |
| **Tokens per success** | **20,742** (lower bound) | **16,000** (lower bound) |
| Tokens burned on cells that never got graded | 0 | 0 |

- 3.6: 7 of 121 cells have no token accounting (all of them ungraded), so total tokens and tokens-per-success are UNDERSTATED for this arm.
- 3.8: 30 of 95 cells have no token accounting (all of them ungraded), so total tokens and tokens-per-success are UNDERSTATED for this arm.

### P2 — 3.6 no-think T1/p0.95/pp0 vs 3.8 no-think T0.7/p0.8/pp1.5

Token-data coverage: 3.6 100% (120/120 cells) · 3.8 82% (79/96 cells). Cost-comparable families: **11 of 12**.  Excluded: `p3_market`.

| Family | 3.6 med tok (n) | 3.8 med tok (n) | tok ratio | 3.6 med s | 3.8 med s | s ratio | comparable |
|---|---:|---:|---:|---:|---:|---:|:--:|
| `p1_bugfix` | 34,135 (10) | 57,052 (4) | 1.67 | 989.0 (10) | 4,126.5 (4) | 4.17 | yes |
| `p1_refactor` | 11,324 (10) | 13,288 (8) | 1.17 | 212.9 (10) | 241.6 (8) | 1.13 | yes |
| `p1_testwrite` | 33,248 (10) | 25,923 (7) | 0.78 | 563.6 (10) | 772.8 (7) | 1.37 | yes |
| `p2_ci` | 5,597 (10) | 4,090 (8) | 0.73 | 98.4 (10) | 76.9 (8) | 0.78 | yes |
| `p2_extract` | 1,502 (10) | 2,980 (8) | 1.98 | 24.9 (10) | 49.7 (8) | 1.99 | yes |
| `p2_hallucination` | 6,214 (10) | 4,240 (8) | 0.68 | 104.1 (10) | 77.1 (8) | 0.74 | yes |
| `p2_triage` | 7,010 (10) | 5,998 (8) | 0.86 | 107.8 (10) | 99.2 (8) | 0.92 | yes |
| `p3_business` | 7,404 (10) | 9,501 (6) | 1.28 | 112.0 (10) | 158.4 (6) | 1.41 | yes |
| `p3_doc` | 8,097 (10) | 10,830 (8) | 1.34 | 124.2 (10) | 177.8 (8) | 1.43 | yes |
| `p3_market` | 32,928 (10) | 52,876 (2) | 1.61 | 785.0 (10) | 1,491.3 (2) | 1.90 | **no** |
| `p3_pm` | 4,182 (10) | 4,530 (8) | 1.08 | 65.2 (10) | 74.8 (8) | 1.15 | yes |
| `p3_writing` | 7,104 (10) | 14,931 (4) | 2.10 | 113.5 (10) | 254.2 (4) | 2.24 | yes |

**Median of per-family ratios (comparable families only): tokens ×1.17, wall-clock ×1.37.**

> ⚠️ **The excluded families are the expensive ones.** Median 3.6 cost is 32,928 tokens
> across the excluded families versus 7,104 across the retained ones (×4.6). Because
> cost data goes missing exactly when a run loops, and 3.8 loops most on the
> long-horizon families, the ×1.17 summary ratio above is computed over the *cheap*
> tail of the task set. **It must not be read as "3.8 is cheaper overall"** — the
> comparison is silent on precisely the families where 3.8's cost would be worst.

| Tokens per successful deliverable | 3.6 | 3.8 |
|---|---:|---:|
| Total completion tokens recorded | 1,628,275 | 1,661,867 |
| Cells with token data | 120/120 | 79/96 |
| Passing cells | 95 | 48 |
| **Tokens per success** | **17,140** | **34,622** (lower bound) |
| Tokens burned on cells that never got graded | 0 | 0 |

- 3.8: 17 of 96 cells have no token accounting (all of them ungraded), so total tokens and tokens-per-success are UNDERSTATED for this arm.

### P3 — 3.6 think T0.3/p0.8/pp0 vs 3.8 think T0.3/p0.8/pp0

Token-data coverage: 3.6 99% (107/108 cells) · 3.8 94% (48/51 cells). Cost-comparable families: **11 of 12**.  Excluded: `p3_market`.

| Family | 3.6 med tok (n) | 3.8 med tok (n) | tok ratio | 3.6 med s | 3.8 med s | s ratio | comparable |
|---|---:|---:|---:|---:|---:|---:|:--:|
| `p1_bugfix` | 32,044 (9) | 86,053 (5) | 2.69 | 899.6 (9) | 2,378.7 (5) | 2.64 | yes |
| `p1_refactor` | 12,387 (9) | 27,969 (4) | 2.26 | 220.2 (9) | 666.1 (4) | 3.03 | yes |
| `p1_testwrite` | 42,849 (9) | 31,491 (5) | 0.73 | 730.9 (9) | 940.5 (5) | 1.29 | yes |
| `p2_ci` | 6,675 (9) | 6,881 (4) | 1.03 | 115.6 (9) | 113.8 (4) | 0.98 | yes |
| `p2_extract` | 3,865 (9) | 4,870 (4) | 1.26 | 60.7 (9) | 112.5 (4) | 1.85 | yes |
| `p2_hallucination` | 7,234 (9) | 8,621 (4) | 1.19 | 117.8 (9) | 135.8 (4) | 1.15 | yes |
| `p2_triage` | 7,681 (9) | 9,907 (4) | 1.29 | 116.9 (9) | 149.9 (4) | 1.28 | yes |
| `p3_business` | 8,137 (9) | 17,730 (4) | 2.18 | 122.5 (9) | 269.4 (4) | 2.20 | yes |
| `p3_doc` | 7,304 (9) | 42,730 (4) | 5.85 | 111.9 (9) | 686.8 (4) | 6.14 | yes |
| `p3_market` | 26,516 (8) | 78,524 (2) | 2.96 | 529.8 (8) | 1,779.8 (2) | 3.36 | **no** |
| `p3_pm` | 3,729 (9) | 10,202 (4) | 2.74 | 58.0 (9) | 154.9 (4) | 2.67 | yes |
| `p3_writing` | 6,315 (9) | 17,228 (4) | 2.73 | 99.7 (9) | 265.3 (4) | 2.66 | yes |

**Median of per-family ratios (comparable families only): tokens ×2.18, wall-clock ×2.20.**

> ⚠️ **The excluded families are the expensive ones.** Median 3.6 cost is 26,516 tokens
> across the excluded families versus 7,304 across the retained ones (×3.6). Because
> cost data goes missing exactly when a run loops, and 3.8 loops most on the
> long-horizon families, the ×2.18 summary ratio above is computed over the *cheap*
> tail of the task set. **It must not be read as "3.8 is cheaper overall"** — the
> comparison is silent on precisely the families where 3.8's cost would be worst.

| Tokens per successful deliverable | 3.6 | 3.8 |
|---|---:|---:|
| Total completion tokens recorded | 1,540,103 | 1,392,807 |
| Cells with token data | 107/108 | 48/51 |
| Passing cells | 67 | 33 |
| **Tokens per success** | **22,987** (lower bound) | **42,206** (lower bound) |
| Tokens burned on cells that never got graded | 0 | 0 |

- 3.6: 1 of 108 cell has no token accounting (all of them ungraded), so total tokens and tokens-per-success are UNDERSTATED for this arm.
- 3.8: 3 of 51 cells have no token accounting (all of them ungraded), so total tokens and tokens-per-success are UNDERSTATED for this arm.

### P4 — 3.6 think T1/p0.95/pp0 vs 3.8 think T1/p0.95/pp0

Token-data coverage: 3.6 100% (120/120 cells) · 3.8 100% (72/72 cells). Cost-comparable families: **12 of 12**.

| Family | 3.6 med tok (n) | 3.8 med tok (n) | tok ratio | 3.6 med s | 3.8 med s | s ratio | comparable |
|---|---:|---:|---:|---:|---:|---:|:--:|
| `p1_bugfix` | 34,634 (10) | 119,290 (6) | 3.44 | 910.8 (10) | 3,073.9 (6) | 3.37 | yes |
| `p1_refactor` | 12,830 (10) | 46,639 (6) | 3.64 | 234.1 (10) | 828.4 (6) | 3.54 | yes |
| `p1_testwrite` | 38,600 (10) | 75,152 (6) | 1.95 | 657.0 (10) | 1,487.0 (6) | 2.26 | yes |
| `p2_ci` | 6,800 (10) | 16,928 (6) | 2.49 | 119.7 (10) | 277.4 (6) | 2.32 | yes |
| `p2_extract` | 4,722 (10) | 10,504 (6) | 2.22 | 73.8 (10) | 162.4 (6) | 2.20 | yes |
| `p2_hallucination` | 7,320 (10) | 16,217 (6) | 2.22 | 120.2 (10) | 259.0 (6) | 2.15 | yes |
| `p2_triage` | 9,285 (10) | 18,494 (6) | 1.99 | 140.7 (10) | 284.9 (6) | 2.02 | yes |
| `p3_business` | 12,102 (10) | 29,340 (6) | 2.42 | 182.9 (10) | 465.1 (6) | 2.54 | yes |
| `p3_doc` | 10,542 (10) | 42,326 (6) | 4.02 | 160.9 (10) | 686.3 (6) | 4.27 | yes |
| `p3_market` | 30,441 (10) | 116,924 (6) | 3.84 | 634.0 (10) | 3,293.9 (6) | 5.20 | yes |
| `p3_pm` | 5,020 (10) | 21,210 (6) | 4.23 | 78.4 (10) | 329.5 (6) | 4.20 | yes |
| `p3_writing` | 8,030 (10) | 36,736 (6) | 4.57 | 127.5 (10) | 592.6 (6) | 4.65 | yes |

**Median of per-family ratios (comparable families only): tokens ×2.97, wall-clock ×2.96.**

| Tokens per successful deliverable | 3.6 | 3.8 |
|---|---:|---:|
| Total completion tokens recorded | 1,798,295 | 2,989,297 |
| Cells with token data | 120/120 | 72/72 |
| Passing cells | 105 | 54 |
| **Tokens per success** | **17,127** | **55,357** |
| Tokens burned on cells that never got graded | 0 | 0 |

---

## 5. Effort ladder within 3.8 thinking

`effort` is populated **only** for 3.8 thinking cells; every 3.6 cell and every no-think cell
has an empty effort field, so there is no 3.6 effort ladder to compare against. The ladder is
broken out by sampler as well as pooled, because the two 3.8 thinking groups have very
different effort mixes (T0.3: 14/24/13 low/med/xhigh; T1: 12/12/48) and pooling them
confounds effort with sampler.

| Sampler | Effort | Cells | Families | Graded | Loops | Pass (all cells) | Wilson 95% CI | Pass (graded) | Median tokens | Median s |
|---|---|---:|---:|---:|---:|---|---|---|---:|---:|
| ALL (pooled) | low | 26 | 12 | 26 | 0 | 21/26 80.8% | [62.1, 91.5] | 21/26 80.8% | 16,333 | 261.7 |
| ALL (pooled) | medium | 36 | 12 | 34 | 2 | 21/36 58.3% | [42.2, 72.9] | 21/34 61.8% | 13,252 | 223.8 |
| ALL (pooled) | xhigh | 61 | 12 | 60 | 0 | 45/61 73.8% | [61.6, 83.2] | 45/60 75.0% | 36,736 | 592.6 |
| T0.3/p0.8/pp0 | low | 14 | 12 | 14 | 0 | 11/14 78.6% | [52.4, 92.4] | 11/14 78.6% | 17,366 | 265.5 |
| T0.3/p0.8/pp0 | medium | 24 | 12 | 22 | 2 | 13/24 54.2% | [35.1, 72.1] | 13/22 59.1% | 10,898 | 223.8 |
| T0.3/p0.8/pp0 | xhigh | 13 | 12 | 12 | 0 | 9/13 69.2% | [42.4, 87.3] | 9/12 75.0% | 32,094 | 501.9 |
| T1/p0.95/pp0 | low | 12 | 12 | 12 | 0 | 10/12 83.3% | [55.2, 95.3] | 10/12 83.3% | 14,514 | 231.9 |
| T1/p0.95/pp0 | medium | 12 | 12 | 12 | 0 | 8/12 66.7% | [39.1, 86.2] | 8/12 66.7% | 14,358 | 225.6 |
| T1/p0.95/pp0 | xhigh | 48 | 12 | 48 | 0 | 36/48 75.0% | [61.2, 85.1] | 36/48 75.0% | 38,506 | 623.3 |

### Pairwise effort steps (Δ = higher effort − lower effort, all-cells pass rate)

| Sampler | Step | Lower | Higher | Δ | Newcombe 95% CI | Fisher p |
|---|---|---|---|---:|---|---:|
| T0.3/p0.8/pp0 | low → medium | 11/14 | 13/24 | -24.4 pp | [-48.0, 7.3] | 0.175 |
| T0.3/p0.8/pp0 | medium → xhigh | 13/24 | 9/13 | +15.1 pp | [-17.2, 41.4] | 0.4908 |
| T0.3/p0.8/pp0 | low → xhigh | 11/14 | 9/13 | -9.3 pp | [-39.6, 22.5] | 0.6776 |
| T1/p0.95/pp0 | low → medium | 10/12 | 8/12 | -16.7 pp | [-46.8, 17.6] | 0.6404 |
| T1/p0.95/pp0 | medium → xhigh | 8/12 | 36/48 | +8.3 pp | [-15.6, 37.7] | 0.7163 |
| T1/p0.95/pp0 | low → xhigh | 10/12 | 36/48 | -8.3 pp | [-26.6, 21.6] | 0.7134 |
| ALL (pooled) | low → medium | 21/26 | 21/36 | -22.4 pp | [-41.8, 1.2] | 0.09799 |
| ALL (pooled) | medium → xhigh | 21/36 | 45/61 | +15.4 pp | [-3.5, 34.1] | 0.1229 |
| ALL (pooled) | low → xhigh | 21/26 | 45/61 | -7.0 pp | [-23.2, 13.9] | 0.5903 |

**Not one effort step is statistically distinguishable** (every Fisher p ≥ 0.098; every
Newcombe CI straddles zero). Cell counts per rung are 12–48, which cannot resolve the
7.0–24.4 pp differences observed. The apparent non-monotonicity — `medium` scoring lowest at
both samplers — is **not** supported as a real effect and should not be reported as one.

What the ladder *does* show cleanly is cost: median tokens rise roughly 1.8–2.7× from `low`
to `xhigh` (T0.3: 17,366 → 32,094; T1: 14,514 → 38,506), with no accompanying pass-rate gain.
On this corpus, raising 3.8's thinking effort buys tokens, not quality.

---

## 6. Q8_0 quantization control

Q8_0 arm at freeze #2 is 19 cells over all 12 families: 2 replicates on the 7 phase-1/phase-2 families, 1 on the 5 phase-3 families.

> **What changed at freeze #2.** At freeze #1 this arm was 11 cells with zero graded and
> carried no quality information at all. At freeze #2 it is 19 cells with 8 graded
> (5 PASS, 3 FAIL), so it now supports **provisional rates with wide intervals** —
> loop rate 6/19 31.6% [15.4, 54.0] and graded-only pass rate 5/8 62.5% [30.6, 86.3] (Wilson 95%).
> The loop interval excludes zero, so "the no-think loop occurs at Q8_0 at a real,
> non-negligible rate" is now a provisional *rate* claim rather than an existence-only
> observation. The quality numbers stay **descriptive only**: on n=8 graded cells no
> pass-rate comparison against a Q4 arm can separate quantization from noise, and none is
> asserted. 19 of the 19 cells ran to a terminal state and 13 produced full token accounting.

> **Unscored qualitative evidence, disclosed and excluded.** `p3_doc_qwen38q8-nothink-matched_v2`
> was quarantined in-flight at freeze #2 and is **not a row in the frozen CSV**: it was
> observed in a rewrite loop — 139 iterations rewriting brief.md, context grown to ~228k tokens when quarantined.
> This is a different failure shape from the identical-call loop that `looped_freq30` /
> `looped_run30` count, it is UNSCORED, and it is excluded from every rate and every
> denominator in this document. It is recorded because a second loop subclass at Q8_0 is
> qualitatively relevant to the quantization question even though it carries no
> statistical weight.

Per-cell detail for all 19 Q8_0 cells as of freeze #2:

| Family | Rep | Verdict | Graded | Terminal | Loop freq30 | Loop run30 | Tokens | Elapsed s |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `p1_bugfix` | 1 | *(none)* | 0 | 1 | 1 | 1 | n/a | n/a |
| `p1_bugfix` | 2 | *(none)* | 0 | 1 | 0 | 0 | n/a | n/a |
| `p1_refactor` | 1 | PASS | 1 | 1 | 0 | 0 | 11,435 | 259.2 |
| `p1_refactor` | 2 | *(none)* | 0 | 1 | 1 | 1 | n/a | n/a |
| `p1_testwrite` | 1 | *(none)* | 0 | 1 | 1 | 1 | n/a | n/a |
| `p1_testwrite` | 2 | *(none)* | 0 | 1 | 1 | 0 | 16,665 | 597.3 |
| `p2_ci` | 1 | PASS | 1 | 1 | 0 | 0 | 4,136 | 96.2 |
| `p2_ci` | 2 | *(none)* | 0 | 1 | 0 | 0 | 4,160 | 98.7 |
| `p2_extract` | 1 | PASS | 1 | 1 | 0 | 0 | 2,422 | 53.0 |
| `p2_extract` | 2 | *(none)* | 0 | 1 | 0 | 0 | 2,435 | 54.5 |
| `p2_hallucination` | 1 | PASS | 1 | 1 | 0 | 0 | 4,316 | 97.0 |
| `p2_hallucination` | 2 | *(none)* | 0 | 1 | 0 | 0 | 4,446 | 101.5 |
| `p2_triage` | 1 | PASS | 1 | 1 | 0 | 0 | 6,771 | 144.5 |
| `p2_triage` | 2 | *(none)* | 0 | 1 | 0 | 0 | 7,434 | 159.1 |
| `p3_business` | 1 | FAIL | 1 | 1 | 0 | 0 | 8,334 | 176.6 |
| `p3_doc` | 1 | FAIL | 1 | 1 | 0 | 0 | 15,304 | 326.8 |
| `p3_market` | 1 | *(none)* | 0 | 1 | 1 | 1 | n/a | n/a |
| `p3_pm` | 1 | FAIL | 1 | 1 | 0 | 0 | 2,935 | 65.2 |
| `p3_writing` | 1 | *(none)* | 0 | 1 | 1 | 1 | n/a | n/a |

Delivery and (provisionally) graded-only quality against Q4 arms restricted to the same
12 families:

**vs 3.8 Q4 (same sampler, same model — isolates quantization)**

| Metric | Q4 comparator | Q8_0 | Δ (Q8−Q4) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| Terminal | 93/95 97.9% | 19/19 100.0% | +2.1 pp | [-14.8, 7.4] | 1 |
| Loop (freq30) | 29/95 30.5% | 6/19 31.6% | +1.1 pp | [-17.9, 25.0] | 1 |
| Loop (run30) | 23/95 24.2% | 5/19 26.3% | +2.1 pp | [-15.2, 25.8] | 1 |
| Pass, graded only (PROVISIONAL) | 51/65 78.5% | 5/8 62.5% | -16.0 pp | [-48.9, 10.5] | 0.3782 |

Token cost, descriptive only (Q8_0 carries 1–2 replicates per family, so the
≥3-cells-per-side comparability rule of §4 is generally not satisfied and no summary
ratio is claimed): 9 families have data on both sides; median per-family token ratio Q8/Q4 = **×1.00** (range ×0.54–×2.15).

**vs 3.6 Q4 (same sampler, different model)**

| Metric | Q4 comparator | Q8_0 | Δ (Q8−Q4) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| Terminal | 118/121 97.5% | 19/19 100.0% | +2.5 pp | [-14.4, 7.0] | 1 |
| Loop (freq30) | 3/121 2.5% | 6/19 31.6% | +29.1 pp | [12.3, 51.6] | 0.00019 **\*** |
| Loop (run30) | 3/121 2.5% | 5/19 26.3% | +23.8 pp | [8.6, 46.4] | 0.00119 **\*** |

Token cost, descriptive only (Q8_0 carries 1–2 replicates per family, so the
≥3-cells-per-side comparability rule of §4 is generally not satisfied and no summary
ratio is claimed): 9 families have data on both sides; median per-family token ratio Q8/Q4 = **×0.88** (range ×0.45–×1.96).

> **Any loop difference in this table is a model effect, not a quantization
> effect.** This row compares 3.8-Q8_0 against 3.6-Q4 — the models differ as well as the
> quantization — so it simply reproduces the no-think looping gap already established in
> §1. Only the preceding table (3.8-Q8_0 vs 3.8-Q4, same model and sampler) isolates
> quantization.

With 19 cells and 1–2 replicates per family, **every interval here still spans tens of
percentage points**. What the arm now establishes: the identical-call loop occurs at Q8_0 at
a rate whose Wilson interval excludes zero, so the loop is not an artifact of the UD-Q4_K_XL
quantization. What it still cannot do: support any quality verdict, or attribute (or
exonerate) the delivery regression as a quantization effect — there is still no matched 3.6
Q8_0 arm, and the graded subset is n=8. The graded outcomes above are published as data
for the next freeze to build on, not as findings.

---

## 7. Sensitivity: does the 3.6-vs-3.8 delta survive rescoring?

Seven scorings per comparison. The first six are the requested set; `graded_only` is added
because it is the natural upper bound on charity toward a model whose failures are delivery
failures.

- **`loops_as_failure`** — All cells in the group; passed==1 is success. Loops and ungraded cells score 0. This is the headline scoring.
- **`loops_excluded`** — Cells with looped_freq30==1 dropped entirely, then pass rate over the remainder. Charitable to whichever model loops more. NOTE: cells that are ungraded WITHOUT having looped are retained here and score 0.
- **`loops_half_credit`** — Score 1.0 for pass, 0.5 for a non-passing looped cell, 0.0 otherwise; compare MEAN scores. Scores are not 0/1 so Wilson and Fisher do not apply; CI is a z-interval on the difference of means.
- **`graded_only`** — Only graded==1 cells. Removes every delivery failure (loops and ungraded alike) and measures output quality conditional on delivery. Maximally charitable to a model that fails by not delivering.
- **`best_of_n_per_family`** — One Bernoulli trial per SHARED family: 1 if any cell in that group/family passed. Measures 'can the model ever do this task', not reliability. n = number of families, so it is structurally low-powered.
- **`first_replicate_only`** — Only rows with replicate==1 (one run per family per arm). Removes any weighting from unequal repeat depth; retains one row per arm, so n is families x arms, not families.
- **`depth_matched`** — Per shared family, the first k=min(n_a,n_b) cells from each side ordered by (arm, replicate, cell). Both sides then have identical family x depth composition.

### P1 — 3.6 no-think T0.3/p0.8/pp0 vs 3.8 no-think T0.3/p0.8/pp0

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | 95% CI on Δ | Fisher p |
|---|---|---|---:|---|---:|
| `loops_as_failure` | 81/121 66.9% | 51/95 53.7% | -13.3 pp | [-25.9, -0.2] | 0.05052 |
| `loops_excluded` | 81/118 68.6% | 51/66 77.3% | +8.6 pp | [-5.1, 20.9] | 0.2358 |
| `loops_half_credit` | mean 0.682 (n=121) | mean 0.689 (n=95) | +0.8 pp | [-10.4, 11.9] | n/a |
| `graded_only` | 81/114 71.1% | 51/65 78.5% | +7.4 pp | [-6.3, 19.5] | 0.2959 |
| `best_of_n_per_family` | 11/12 91.7% | 8/12 66.7% | -25.0 pp | [-53.4, 8.4] | 0.3168 |
| `first_replicate_only` | 8/13 61.5% | 8/13 61.5% | +0.0 pp | [-33.3, 33.3] | 1 |
| `depth_matched` | 62/94 66.0% | 51/94 54.3% | -11.7 pp | [-25.0, 2.3] | 0.1361 |

Range of Δ across the seven scorings: **-25.0 pp to +8.6 pp**. Sign is **NOT consistent — it flips**. Significant in **0 of 6** scorings that admit a Fisher test.

### P2 — 3.6 no-think T1/p0.95/pp0 vs 3.8 no-think T0.7/p0.8/pp1.5

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | 95% CI on Δ | Fisher p |
|---|---|---|---:|---|---:|
| `loops_as_failure` | 95/120 79.2% | 48/96 50.0% | -29.2 pp | [-40.8, -16.4] | 1.1e-05 **\*** |
| `loops_excluded` | 95/120 79.2% | 46/68 67.6% | -11.5 pp | [-24.9, 1.3] | 0.114 |
| `loops_half_credit` | mean 0.792 (n=120) | mean 0.635 (n=96) | -15.6 pp | [-26.6, -4.7] | n/a |
| `graded_only` | 95/120 79.2% | 48/79 60.8% | -18.4 pp | [-31.1, -5.5] | 0.006102 **\*** |
| `best_of_n_per_family` | 11/12 91.7% | 9/12 75.0% | -16.7 pp | [-45.7, 14.8] | 0.5901 |
| `first_replicate_only` | 9/12 75.0% | 12/24 50.0% | -25.0 pp | [-49.6, 8.8] | 0.2821 |
| `depth_matched` | 77/96 80.2% | 48/96 50.0% | -30.2 pp | [-42.1, -16.9] | 1.8e-05 **\*** |

Range of Δ across the seven scorings: **-30.2 pp to -11.5 pp**. Sign is consistently negative (3.8 worse). Significant in **3 of 6** scorings that admit a Fisher test.

### P3 — 3.6 think T0.3/p0.8/pp0 vs 3.8 think T0.3/p0.8/pp0

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | 95% CI on Δ | Fisher p |
|---|---|---|---:|---|---:|
| `loops_as_failure` | 67/108 62.0% | 33/51 64.7% | +2.7 pp | [-13.5, 17.7] | 0.8607 |
| `loops_excluded` | 67/107 62.6% | 33/49 67.3% | +4.7 pp | [-11.7, 19.6] | 0.5949 |
| `loops_half_credit` | mean 0.625 (n=108) | mean 0.667 (n=51) | +4.2 pp | [-11.5, 19.9] | n/a |
| `graded_only` | 67/107 62.6% | 33/48 68.8% | +6.1 pp | [-10.4, 20.9] | 0.5863 |
| `best_of_n_per_family` | 9/12 75.0% | 12/12 100.0% | +25.0 pp | [-4.1, 53.2] | 0.2174 |
| `first_replicate_only` | 8/12 66.7% | 26/36 72.2% | +5.6 pp | [-19.8, 35.6] | 0.726 |
| `depth_matched` | 34/51 66.7% | 33/51 64.7% | -2.0 pp | [-19.8, 16.0] | 1 |

Range of Δ across the seven scorings: **-2.0 pp to +25.0 pp**. Sign is **NOT consistent — it flips**. Significant in **0 of 6** scorings that admit a Fisher test.

### P4 — 3.6 think T1/p0.95/pp0 vs 3.8 think T1/p0.95/pp0

| Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | 95% CI on Δ | Fisher p |
|---|---|---|---:|---|---:|
| `loops_as_failure` | 105/120 87.5% | 54/72 75.0% | -12.5 pp | [-24.6, -1.4] | 0.03081 **\*** |
| `loops_excluded` | 105/120 87.5% | 54/72 75.0% | -12.5 pp | [-24.6, -1.4] | 0.03081 **\*** |
| `loops_half_credit` | mean 0.875 (n=120) | mean 0.750 (n=72) | -12.5 pp | [-24.2, -0.8] | n/a |
| `graded_only` | 105/120 87.5% | 54/72 75.0% | -12.5 pp | [-24.6, -1.4] | 0.03081 **\*** |
| `best_of_n_per_family` | 12/12 100.0% | 10/12 83.3% | -16.7 pp | [-44.8, 10.4] | 0.4783 |
| `first_replicate_only` | 12/12 100.0% | 36/48 75.0% | -25.0 pp | [-38.8, 1.3] | 0.1006 |
| `depth_matched` | 63/72 87.5% | 54/72 75.0% | -12.5 pp | [-25.0, 0.3] | 0.08639 |

Range of Δ across the seven scorings: **-25.0 pp to -12.5 pp**. Sign is consistently negative (3.8 worse). Significant in **3 of 6** scorings that admit a Fisher test.

### What survives every scoring

Computed directly from the table above rather than asserted:

- **P1** (3.6 no-think T0.3/p0.8/pp0 vs 3.8 no-think T0.3/p0.8/pp0): **Not robust — the sign flips with the scoring rule.** No quality claim in either direction survives. Significant in 0 of 6.
- **P2** (3.6 no-think T1/p0.95/pp0 vs 3.8 no-think T0.7/p0.8/pp1.5): **Directionally robust, not uniformly significant.** 3.8 is worse under all seven scorings, significant in 3 of 6.
- **P3** (3.6 think T0.3/p0.8/pp0 vs 3.8 think T0.3/p0.8/pp0): **Not robust — the sign flips with the scoring rule.** No quality claim in either direction survives. Significant in 0 of 6.
- **P4** (3.6 think T1/p0.95/pp0 vs 3.8 think T1/p0.95/pp0): **Directionally robust, not uniformly significant.** 3.8 is worse under all seven scorings, significant in 3 of 6.

**A confound in P2, and why it cannot carry the effect.** P2's vendor-matched design ties
model identity to `presence_penalty`: the 3.8 vendor sampler carries pp=1.5 while 3.6's
carries pp=0, so any P2 delta could in principle be a presence-penalty artifact rather than
a model difference. That objection fails against the delivery finding: P1 holds pp=0 on
**both** sides and still shows the +28.0 pp loop delta (4.9e-09), so the looping regression
appears with the confound removed entirely. P2's *quality* deltas have no pp-free
replication at the same (no-think) mode — P1, the pp=0 no-think pair, flips sign across
scorings — so the confound caveat does apply to P2's pass rates. One more reason the loop
finding, not the pass-rate finding, is this document's headline.

Three statements survive **every scoring rule**, in every comparison where they can be
measured at all:

1. **3.8's no-think looping is real and large.** Loop rate (freq30) is +28.0 pp in P1 (4.9e-09) and +29.2 pp in
   P2 (1.1e-11), with CIs excluding zero. It is the single largest and most reliable effect in the
   corpus, and it is not sensitive to any scoring choice because it is measured upstream of grading.
2. **The looping is confined to no-think mode.** In thinking mode the loop rate collapses to
   2/51 and 0/72 for 3.8 (P3, P4) against 1/108 and 0/120 for 3.6 — no significant difference
   and, at T1/p0.95/pp0, zero loops on either side.
3. **3.8 costs more in thinking mode.** Median per-family token ratio is ×2.18 (P3) and ×2.97
   (P4), with wall-clock tracking it (×2.20, ×2.96), and no pass-rate gain to show for it.

The claim that does **not** survive is any clean statement that 3.8 produces worse *output*.
In P1 the sign flips: 3.8 is 13.3 pp worse end-to-end but 7.4 pp **better** among graded
cells. Both cannot be summarized as "3.8 is worse at the task" — the honest reading is
that 3.8 fails more often by not finishing, not by finishing badly.

---

## 8. Grader-defect exposure (why these tables are labelled *as-graded*)

Every pass rate in this document is **as-graded**: it uses the `passed` bit exactly as the
original graders produced it. Three grader defects are verified in this corpus. Per repo
convention they are corrected in a **separate non-destructive overlay**, never by editing
`grade.json` or the task briefs, so longitudinal comparability is preserved. The tables here
are the baseline that overlay will be applied to.

Diagnostics below are computed from raw `grade.json` files (the frozen CSV carries only the
final pass/fail bit, so diagnosing *why* a cell failed requires the grader's score fields).
Cell→model identity is joined from the frozen CSV by cell id, and cells that were ungraded
at the freeze are excluded even where a post-freeze `grade.json` now exists on disk (see the
drift note in §6). **No headline number above depends on this section.**

### Exposure: cells sitting in a defect-affected family

| Group | n | D1 length-gated (4 families) | D2 `p3_pm` | D3 `p2_triage` |
|---|---:|---|---|---|
| `A36` | 121 | n=36, graded=36, pass=18 | n=9, graded=9, pass=1 | n=9, graded=9, pass=0 |
| `A38` | 95 | n=28, graded=26, pass=20 | n=7, graded=7, pass=7 | n=7, graded=7, pass=7 |
| `V36` | 120 | n=40, graded=40, pass=21 | n=10, graded=10, pass=1 | n=10, graded=10, pass=7 |
| `V38` | 96 | n=32, graded=26, pass=11 | n=8, graded=8, pass=8 | n=8, graded=8, pass=5 |
| `B36` | 108 | n=36, graded=36, pass=10 | n=9, graded=9, pass=0 | n=9, graded=9, pass=0 |
| `B38` | 51 | n=16, graded=16, pass=5 | n=4, graded=4, pass=1 | n=4, graded=4, pass=4 |
| `C36` | 120 | n=40, graded=40, pass=29 | n=10, graded=10, pass=2 | n=10, graded=10, pass=10 |
| `C38` | 72 | n=24, graded=24, pass=6 | n=6, graded=6, pass=5 | n=6, graded=6, pass=6 |
| `Q8` | 19 | n=4, graded=3, pass=0 | n=1, graded=1, pass=0 | n=2, graded=1, pass=1 |

### D1 — word-gate tokenizer mismatch · correction favours **3.8**

| Family | 3.6 pass/n | 3.6 over word limit | 3.8 pass/n | 3.8 over word limit |
|---|---:|---:|---:|---:|
| `p3_business` | 35/38 | 3 | 4/23 | 18 |
| `p3_doc` | 28/38 | 10 | 9/25 | 16 |

In `p3_business` **every** FAIL on both sides is a word-limit FAIL (3.6: 3/3, 3.8: 18/18);
the substantive `stance_pushback` criterion was met by every graded cell of both models.

Overshoot sizes in `p3_doc` against its 700-word ceiling, i.e. how far over the grader's own
counter each failing deliverable landed:

| Model | Over-limit cells | Word counts | Overshoot range | Median overshoot |
|---|---:|---|---:|---:|
| 3.6 | 10 | 707, 707, 707, 707, 707, 707, 707, 707, 709, 713 | 7–13 words | 7.0 words |
| 3.8 | 16 | 701, 702, 708, 718, 719, 720, 722, 722, 722, 723, 725, 726, 727, 730, 733, 772 | 1–72 words | 22.0 words |

The bulk of these are single-digit to low-double-digit overruns on a 700-word budget — 3.6's
largest is 13 words over and its median is 7 — which is well inside the disagreement between
the two counters. That is the substance of D1: the graders count `\b\w+\b` while both models
budgeted with shell `wc -w`, and neither counter is ground truth. **The tail runs longer on
3.8's side** — its worst `p3_doc` overshoot is 72 words (772 against a 700 ceiling) versus
3.6's 13 — so the overlay must report per-cell outcomes rather than assume a blanket
reversal; correcting D1 should be expected to rescue most, though not necessarily all, of
3.8's length failures.

### D2 — `p3_pm` risk-keyword literalism · correction favours **3.6**

| Model | Pass/n | FAILs blocked by risk_recall < 3 | risk_recall distribution |
|---|---:|---:|---|
| 3.6 | 4/38 | 34 | 2 risks: 34 cells, 3 risks: 4 cells |
| 3.8 | 21/26 | 5 | 2 risks: 5 cells, 3 risks: 16 cells, 4 risks: 5 cells |

**34 of 38** 3.6 cells land on exactly `2/6` risks — one short of the `min_risks = 3`
threshold — and every one of the 34 3.6 FAILs is blocked by that rule alone. This is the
signature of a single unmatched keyword, consistent with the verified R3 literalism 
(3.6 writes "legal has not responded"; the rule requires a contracted form).

### D3 — `p2_triage` brief/ground-truth contradiction · correction favours **3.6**

| Quantity | Value |
|---|---:|
| Graded triage cells examined | 64 |
| Cells answering `n/a` on all three spam tickets (004, 009, 021) | **64/64** |
| FAIL cells | 24 |
| FAIL cells blocked by urgency accuracy *alone* | **24/24** |
| FAIL cells that flip to PASS once the spam penalty is removed | **24/24** |
| …of which 3.6 | 21 |
| …of which 3.8 | 3 |

> **Correction to the briefed characterization of D3.** The defect brief states that
> `p2_triage` "has zero discriminating power as graded". The frozen data does not support
> that as written: **as graded** the family splits 40 PASS / 24 FAIL and does discriminate
> (3.6 17/38 vs 3.8 23/26). The accurate statement is the reverse in time: all 64 cells take
> the identical 0.100 urgency penalty, and because the threshold is 0.700 that penalty decides
> the verdict purely by where each cell already sat — cells at 0.767–0.800 survive, cells at
> 0.633–0.667 do not. The observed split is threshold noise, not signal. It is **after** the
> correction that the family becomes uniformly passing and loses all discriminating power.

### Net direction of the pending overlay

The three defects **do not push the same way**: D1 materially helps 3.8, while D2 and D3 help
3.6. Anyone assuming the corrections will uniformly move the headline in one direction is
wrong. The as-graded numbers in this document should not be read as biased against either
model until the overlay is computed.

As one bound on how much of the quality signal is defect-contaminated, restricting to the
seven families with **no** verified grader defect (`p1_bugfix`, `p1_refactor`, `p1_testwrite`, `p2_ci`, `p2_extract`, `p2_hallucination`, `p3_market`):

| Comparison | 3.6 | 3.8 | Δ (3.8−3.6) | Newcombe 95% CI | Fisher p |
|---|---|---|---:|---|---:|
| P1 | 63/76 82.9% | 24/60 40.0% | -42.9 pp | [-56.2, -26.8] | 2.9e-07 **\*** |
| P2 | 67/70 95.7% | 32/56 57.1% | -38.6 pp | [-51.9, -24.3] | 1.2e-07 **\*** |
| P3 | 57/63 90.5% | 24/31 77.4% | -13.1 pp | [-31.0, 1.8] | 0.1133 |
| P4 | 66/70 94.3% | 42/42 100.0% | +5.7 pp | [-3.4, 13.8] | 0.295 |

This subset is **not** a substitute for the overlay: it changes the family mix (and in P1/P2 it
is heavily confounded by 3.8's looping, which is concentrated in `p1_bugfix` and `p1_testwrite`).
It is reported only to show that the defect families are load-bearing for the as-graded totals.

---

## 9. Comparisons too underpowered to report

Screening rule, applied uniformly: a comparison is flagged **UNDERPOWERED** if either arm has
n < 30, or the Newcombe 95% CI on the difference is wider than 30 pp — i.e. the interval
cannot separate a small effect from a large one in either direction.

This flag is about **precision, not significance**, and the two are independent. A result can
be flagged here and still be statistically significant. Read such rows as "the direction
is probably real, the magnitude
is not pinned down". Conversely, P3's non-significant rows are flagged because the data cannot
distinguish "no difference" from "a difference of 18 pp in either direction" — **P3 is not
evidence of equivalence.**

| Comparison | Metric | Δ | 95% CI | Width | Verdict |
|---|---|---:|---|---:|---|
| P1 | `best_of_n_per_family` | -25.0 pp | [-53.4, 8.4] | 61.8 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=12); Newcombe CI width 61.8 pp |
| P1 | `first_replicate_only` | +0.0 pp | [-33.3, 33.3] | 66.6 pp | UNDERPOWERED — n<30 in an arm (n_a=13, n_b=13); Newcombe CI width 66.6 pp |
| P2 | `best_of_n_per_family` | -16.7 pp | [-45.7, 14.8] | 60.5 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=12); Newcombe CI width 60.5 pp |
| P2 | `first_replicate_only` | -25.0 pp | [-49.6, 8.8] | 58.4 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=24); Newcombe CI width 58.4 pp |
| P3 | `pass_all` | +2.7 pp | [-13.5, 17.7] | 31.2 pp | UNDERPOWERED — Newcombe CI width 31.2 pp |
| P3 | `pass_graded` | +6.1 pp | [-10.4, 20.9] | 31.2 pp | UNDERPOWERED — Newcombe CI width 31.2 pp |
| P3 | `loops_as_failure` | +2.7 pp | [-13.5, 17.7] | 31.2 pp | UNDERPOWERED — Newcombe CI width 31.2 pp |
| P3 | `loops_excluded` | +4.7 pp | [-11.7, 19.6] | 31.2 pp | UNDERPOWERED — Newcombe CI width 31.2 pp |
| P3 | `graded_only` | +6.1 pp | [-10.4, 20.9] | 31.2 pp | UNDERPOWERED — Newcombe CI width 31.2 pp |
| P3 | `loops_half_credit` | +4.2 pp | [-11.5, 19.9] | 31.4 pp | UNDERPOWERED — Newcombe CI width 31.4 pp |
| P3 | `best_of_n_per_family` | +25.0 pp | [-4.1, 53.2] | 57.3 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=12); Newcombe CI width 57.3 pp |
| P3 | `first_replicate_only` | +5.6 pp | [-19.8, 35.6] | 55.4 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=36); Newcombe CI width 55.4 pp |
| P3 | `depth_matched` | -2.0 pp | [-19.8, 16.0] | 35.8 pp | UNDERPOWERED — Newcombe CI width 35.8 pp |
| P4 | `best_of_n_per_family` | -16.7 pp | [-44.8, 10.4] | 55.2 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=12); Newcombe CI width 55.2 pp |
| P4 | `first_replicate_only` | -25.0 pp | [-38.8, 1.3] | 40.0 pp | UNDERPOWERED — n<30 in an arm (n_a=12, n_b=48); Newcombe CI width 40.0 pp |

Explicitly **not** reportable:

- **The Q8_0 quantization arm for any quality *verdict*.** 8 of 19 cells graded at freeze #2;
  the graded-only rate 5/8 is published in §6 as provisional data with a Wilson interval
  spanning tens of points — direction-finding for the next freeze, not evidence.
- **Every `best_of_n_per_family` result.** n = 12 families per side by construction; CI widths
  are 55.2–61.8 pp. These rows are shown for completeness of the sensitivity grid, not as evidence.
- **Every `first_replicate_only` result** for the same reason (n = 12–48).
- **Every effort-ladder step.** All nine pairwise steps are non-significant with CI widths
  of 37.1–64.3 pp.
- **All per-family rows in §3** individually (n = 4–19 per side).
- **P4's quality delta** is borderline and, more importantly, structurally biased: the shared
  T1/p0.95/pp0 sampler is 3.6's vendor point and not 3.8's, so 3.8 runs off-spec by construction.

---

## 10. Method appendix

### Estimators (pure python, no scipy)

**Wilson score interval** for a proportion — inverts the score test rather than using the
Wald form, so it stays inside [0,1] and behaves at x = 0 and x = n (several arms here are 0/n):

```
center = (p + z^2/(2n)) / (1 + z^2/n)
half   = z * sqrt( p(1-p)/n + z^2/(4n^2) ) / (1 + z^2/n)
CI     = center -/+ half            z = 1.959963984540054
```

**Fisher exact test**, two-sided. Conditioning on both margins, the top-left cell follows the
hypergeometric law; the p-value is the Fisher/Irwin sum-of-small-probabilities form used by
R's `fisher.test`:

```
P(a) = C(r1,a) * C(r2,c1-a) / C(r1+r2,c1)
p    = sum of P(x) over all tables x with the same margins where P(x) <= P(observed)
```

Computed in exact rational arithmetic (`fractions.Fraction`), so no floating-point tie-breaking.

**Newcombe method 10** (hybrid score) CI for a difference of proportions — propagates the two
Wilson intervals instead of a pooled Wald SE, which is what keeps it sane at boundary counts:

```
lower = (p1-p2) - sqrt( (p1-l1)^2 + (u2-p2)^2 )
upper = (p1-p2) + sqrt( (u1-p1)^2 + (p2-l2)^2 )
```

**Half-credit scoring** produces per-cell scores in {0, 0.5, 1}, which are not Bernoulli.
Wilson/Newcombe/Fisher are therefore **not** applied to it; that row uses a z-interval on
the difference of means (`z_diff_mean` — a normal approximation with critical value z, not
a Welch-t interval) and is labelled as such.

### Validation

`test_stats.py` checks each estimator against its defining equation or an exact independent
enumeration rather than against remembered published values:

- Wilson limits are verified to be exact roots of the score equation (the score statistic
  evaluates to z at both limits to 1e-9), and to bracket p̂ for every (x, n) with n ≤ 199.
- The hypergeometric pmf is verified to sum to exactly 1 in rational arithmetic, and to match
  brute-force enumeration over all C(11,4) subsets.
- Fisher reproduces the tea-tasting table `[[3,1],[1,3]]` as exactly 17/35, is symmetric under
  row and column swaps, and agrees with the chi-square approximation at large n.
- Newcombe is verified against its construction, verified antisymmetric under group swap, and
  its zero-exclusion agrees with Fisher p < 0.05 on 98.2% of a 441-table grid.

One real defect was found and fixed by this suite: at x = 0 and x = n the Wilson closed form
missed the exact boundary by ~1e-16, leaving the interval not quite containing p̂. Those two
cases are now snapped to exactly 0 and 1.

### Known limitations of this dataset

1. **Single seed.** All 802 runs use seed 42; replicates are repeat runs, not independent
   seeds. Binomial CIs treat cells as independent draws, which is optimistic.
2. **Unequal and non-random depth.** Replicate counts vary by family and arm (1–19 per
   family-group). The `depth_matched` scoring exists to bound the effect of this.
3. **Non-random missing cost data.** 64 of 802 cells lack `completion_tokens`; all 64 are
   ungraded and most looped. Cost figures for affected arms are lower bounds.
4. **Pooled effort in 3.8 thinking.** Groups `B38` and `C38` each pool three effort levels;
   their aggregate pass rates are effort-mix-weighted, not single-configuration numbers.
5. **As-graded only.** Three verified grader defects remain uncorrected here by design.
6. **Arm pooling.** Several groups pool two or more arms that share model, quant, mode and
   sampler triple but were run as separate sweeps (listed in §0).

