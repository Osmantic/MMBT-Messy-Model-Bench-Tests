> [!IMPORTANT]
> **EXPLORATORY — notice added 2026-08-16 per the corrective protocol, section 9. No number
> below has been altered; this notice is prepended only.**
>
> 1. **Arm mislabel (V36 vendor no-think).** The arm labelled "3.6 vendor no-think" ran
>    Qwen3.6-27B at its **thinking** sampler (T1.0 / top_p 0.95 / presence_penalty 0) with
>    thinking disabled — off-spec per the pinned Qwen3.6-27B card (rev `6a9e13bd`, README
>    L637: official non-thinking is T0.7 / top_p 0.80 / top_k 20 / min_p 0 / pp 1.5 / rp 1,
>    identical to Qwen3.8-27B). The "vendor vs vendor" no-think contrast in this entry is
>    therefore mode/sampler-confounded, and this corpus contains **no cell of Qwen3.6
>    non-thinking at its official sampler**.
> 2. **Cell-level Fisher exact values in this entry are descriptive only.** They treat cells
>    as independent and are anti-conservative under family/seed clustering; they are not
>    confirmatory inference.
> 3. **This 802-cell freeze is exploratory evidence.** It feeds no confirmatory claim. The
>    confirmatory design, arms, fixed N, and analysis plan are preregistered at
>    [`../qwen36-vs-qwen38-corrective-2026-08/PREREGISTRATION.md`](../qwen36-vs-qwen38-corrective-2026-08/PREREGISTRATION.md);
>    the pinned-card sampler evidence is recorded at
>    [`../qwen36-vs-qwen38-corrective-2026-08/protocol/CARD-EVIDENCE.md`](../qwen36-vs-qwen38-corrective-2026-08/protocol/CARD-EVIDENCE.md).

# 2026-08 — Qwen3.6-27B vs Qwen3.8-27B (UD-Q4_K_XL) across 12 task families

> Head-to-head of Qwen3.6-27B and Qwen3.8-27B, both at Unsloth UD-Q4_K_XL, on the 12-family
> MMBT suite: 802 frozen cells over 9 sampler/mode arms, plus a 19-cell Q8_0 control.
> The campaign also audited MMBT's own graders and found three defects that materially
> distort the raw numbers; corrections ship as a non-destructive overlay, and five earlier
> conclusions from this investigation are formally retracted in [`claims.yaml`](../../claims.yaml).
>
> **Top-line:**
>
> 1. **The one large, unambiguous effect is a delivery regression in no-think mode, not a
>    capability regression.** 3.8's identical-call-loop rate is +28.0 pp over 3.6 at the
>    matched sampler (Fisher p = 4.9e-09) and +29.2 pp at each model's own vendor sampler
>    (p = 1.1e-11). This is measured upstream of grading — no scoring choice and none of the
>    three grader defects can touch it.
> 2. **The regression disappears in thinking mode.** 3.8's loop rate falls to 2/51 (T0.3)
>    and 0/72 (T1), neither distinguishable from 3.6.
> 3. **Conditional on delivering, and after the grader corrections, the models are within
>    noise of each other at the matched sampler** (86.0% vs 86.2% no-think; 92.5% vs 89.6%
>    think). "3.8 is worse at the task" is not a supportable summary of this corpus;
>    "3.8 fails more often by not finishing" is. The vendor-point conditional gap (~15 pp)
>    survives correction and is unresolved.
> 4. **Thinking costs 3.8 roughly 2.2–3.0× more tokens with no pass-rate gain**, and its
>    `reasoning_effort` ladder buys tokens rather than quality (no step is significant).
> 5. **Three grader defects are verified and corrected by overlay** — a word-count tokenizer
>    mismatch (62 counter-dependent verdicts), a `p3_pm` keyword literalism (36 verdict
>    flips), and a `p2_triage` brief/ground-truth contradiction (24 flips). Two of the three
>    corrected families saturate and stop discriminating. See [`grader-defects.md`](grader-defects.md).
> 6. **The identical-call loop reproduces at Q8_0** (6/19, Wilson 95% [15.4%, 54.0%],
>    excluding zero) — the no-think loop is not an artifact of the 4-bit quantization.

---

## Provenance

| Item | Value |
| --- | --- |
| Frozen dataset | [`data/mmbt-frozen-dataset-v2.csv`](data/mmbt-frozen-dataset-v2.csv) — freeze #2, 802 cells (733 graded), frozen `2026-08-16T14:23:09Z` |
| Frozen dataset sha256 | `d2ed0beca5b68e9ca63788e452235f23a299af06639893f558bef19f784cf018` |
| Freeze stamp | [`data/FREEZE2_STAMP.txt`](data/FREEZE2_STAMP.txt) |
| Supersedes | freeze #1 (746 cells, `2026-08-16T11:49:14Z`), which was cut while campaign processes were still writing cells |
| Correction overlay | [`overlay/`](overlay/) — 165 per-cell records + manifest, digest `e332cd2c78ad94fe264aed7d31e6c64f5273cd9598f889dc1a8fac539e971351` |
| Full statistical tables | [`results-tables.md`](results-tables.md) (rendered from [`results.json`](results.json)) |
| Grader-defect report | [`grader-defects.md`](grader-defects.md) |
| Methodology audit (locked/varies, bias list B1-B11) | [`AUDIT.md`](AUDIT.md) |

Every number in this entry derives from the frozen CSV and the immutable run artifacts —
never from a live re-scan. Model, quantization and sampler identity come from each run's
`receipt.json`, never from directory names (one arm named `-offspec` was found actually
carrying the vendor-card sampler; filename inference is unsafe). The corpus is static:
every campaign process is stopped, in-flight cells are quarantined out of the extract, and
the overlay manifest's `post_freeze_divergence` ledger is empty — the on-disk verdict
agrees with the frozen verdict for all 733 graded rows. Raw per-run logs and workspaces
stay outside the repo per `REPO-SPACE.md` (the workspace tarballs alone are ~1.5 GB); the
frozen CSV, the overlay, and the generators in [`tooling/`](tooling/) are the publishable,
auditable derivation chain.

All 802 runs used seed 42. Replicates are repeat runs at a fixed seed, not a seed sweep —
see the seed-correlation caveat added to [`KNOWN-LIMITATIONS.md`](../../KNOWN-LIMITATIONS.md).

## What was tested

| Group | Definition | Cells | Graded | Notes |
|---|---|---:|---:|---|
| `A36` | 3.6 no-think T0.3/p0.8/pp0 | 121 | 114 | off-spec for 3.6; sampler-matched to A38 |
| `A38` | 3.8 no-think T0.3/p0.8/pp0 | 95 | 65 | off-spec for 3.8; sampler-matched to A36 |
| `V36` | 3.6 no-think T1/p0.95/pp0 | 120 | 120 | 3.6 vendor point |
| `V38` | 3.8 no-think T0.7/p0.8/pp1.5 | 96 | 79 | 3.8 vendor point |
| `B36` | 3.6 think T0.3/p0.8/pp0 | 108 | 107 | sampler-matched to B38 |
| `B38` | 3.8 think T0.3/p0.8/pp0 | 51 | 48 | mixed effort (14 low / 24 medium / 13 xhigh) |
| `C36` | 3.6 think T1/p0.95/pp0 | 120 | 120 | 3.6 vendor point |
| `C38` | 3.8 think T1/p0.95/pp0 | 72 | 72 | 3.6's vendor sampler, NOT 3.8's; mixed effort (12/12/48) |
| `Q8` | 3.8 **Q8_0** no-think T0.3/p0.8/pp0 | 19 | 8 | quantization control |

Four paired contrasts are reported throughout: **P1** (no-think, sampler-matched A36/A38),
**P2** (no-think, vendor-matched V36/V38), **P3** (think, sampler-matched B36/B38), and
**P4** (think at T1 — which is 3.6's vendor point and not 3.8's, so P4 is biased in 3.6's
favour by construction). Group composition, arm pooling, and the missing-data structure are
in [`results-tables.md`](results-tables.md) §0.

## Delivery reliability

Delivery means the run produced a gradeable artifact (`graded == 1` in the frozen CSV).
Loop detection uses two mechanical detectors recorded per cell: `looped_freq30` (≥30
occurrences of one digit-stripped tool template) and the stricter `looped_run30` (≥30
consecutive). The loop metric is upstream of every grader and every grader defect.

| Contrast | Metric | 3.6 | 3.8 | Δ (3.8−3.6) | Fisher p |
|---|---|---|---|---:|---:|
| P1 matched no-think | Delivered | 114/121 94.2% | 65/95 68.4% | −25.8 pp | 8.2e-07 |
| P1 matched no-think | Loop (freq30) | 3/121 2.5% | 29/95 30.5% | **+28.0 pp** | **4.9e-09** |
| P2 vendor no-think | Delivered | 120/120 100% | 79/96 82.3% | −17.7 pp | 4.4e-07 |
| P2 vendor no-think | Loop (freq30) | 0/120 0.0% | 28/96 29.2% | **+29.2 pp** | **1.1e-11** |
| P3 matched think | Loop (freq30) | 1/108 0.9% | 2/51 3.9% | +3.0 pp | 0.2412 |
| P4 think at T1 | Loop (freq30) | 0/120 0.0% | 0/72 0.0% | +0.0 pp | 1 |

Structure of the regression:

- **It is concentrated, not uniform.** At the matched sampler 3.8 delivers 1/12 on
  `p1_bugfix` and 2/13 on `p1_testwrite`, while matching 3.6 at 100% delivery on all four
  phase-2 families (7/7 each). At the vendor points, 3.6's per-family delivery ≥ 3.8's in
  12 of 12 families (5 strict, 7 ties).
- **Thinking removes most of it.** 3.8 delivers 48/51 (94.1%) in think mode at the matched
  sampler against 65/95 (68.4%) no-think, and 72/72 at T1. 3.6 is at or near ceiling in
  think mode on both samplers (107/108, 120/120).
- **Terminal rate is not the story** — 97.5–100% everywhere. 3.8's non-deliveries are runs
  that looped until an operator or the harness gave up, not crashes.

There is deliberately **no "abort rate" in this entry**. The operator's
identical-call-loop label disagrees with the mechanical loop signal on 24 of 802 cells in
both directions, so a rate built on the label would measure operator intervention as much
as model behavior — see the retraction `bench.qwen38.nothink-abort-rate` in
[`claims.yaml`](../../claims.yaml).

## Quality, as graded

Two scorings per pair, because they answer different questions and their disagreement is
the finding. All-cells counts loops as failures (end-to-end); graded-only conditions on
delivery (maximally charitable to a model that fails by not finishing).

| Contrast | Scoring | 3.6 | 3.8 | Δ (3.8−3.6) | Fisher p |
|---|---|---|---|---:|---:|
| P1 matched no-think | All cells | 81/121 66.9% | 51/95 53.7% | −13.3 pp | 0.05052 |
| P1 matched no-think | Graded only | 81/114 71.1% | 51/65 78.5% | **+7.4 pp** | 0.2959 |
| P2 vendor no-think | All cells | 95/120 79.2% | 48/96 50.0% | −29.2 pp | 1.1e-05 |
| P2 vendor no-think | Graded only | 95/120 79.2% | 48/79 60.8% | −18.4 pp | 0.006102 |
| P3 matched think | All cells | 67/108 62.0% | 33/51 64.7% | +2.7 pp | 0.8607 |
| P3 matched think | Graded only | 67/107 62.6% | 33/48 68.8% | +6.1 pp | 0.5863 |
| P4 think at T1 | All cells | 105/120 87.5% | 54/72 75.0% | −12.5 pp | 0.03081 |

In P1 the sign flips between the two scorings: 3.8 is 13.3 pp worse end-to-end and 7.4 pp
*better* among graded cells. Across the full seven-scoring sensitivity grid
([`results-tables.md`](results-tables.md) §7), P1 and P3 flip sign with the scoring rule
(no quality claim in either direction survives), while P2 and P4 are directionally robust
but carry structural caveats — P2 ties model identity to presence_penalty, and P4 runs 3.8
off-spec at 3.6's vendor sampler. These are **as-graded** numbers containing the three
verified grader defects; per-family breakdowns with denominators are in
[`results-tables.md`](results-tables.md) §3, and no family row is individually conclusive
(n = 4–19 per side).

No family-paired win count is published. At the matched sampler the count is 4 (3.6) / 5
(3.8) / 3 tied on raw grades and 4 / 3 / 5 after correction — not stable, and two of the
twelve families were contributing wins on the strength of grader defects. See the
retraction `bench.family-paired.nine-three`.

## Quality conditional on delivery

After applying the correction overlay (D2 and D3 verdict corrections; D1 gate-invalidated
cells counted as non-failures — see [`grader-defects.md`](grader-defects.md) for why those
62 verdicts are counter-dependent rather than valid FAILs):

| Contrast | 3.6 corrected | 3.8 corrected | Δ (3.8−3.6) |
|---|---|---|---:|
| P1 matched no-think | 98/114 86.0% | 56/65 86.2% | +0.2 pp |
| P1, excluding `p2_triage` | 89/105 84.8% | 49/58 84.5% | −0.3 pp |
| P3 matched think | 99/107 92.5% | 43/48 89.6% | −2.9 pp |
| P3, excluding `p2_triage` | 90/98 91.8% | 39/44 88.6% | −3.2 pp |
| P2 vendor no-think | 110/120 91.7% | 61/79 77.2% | **−14.5 pp** |
| P4 think at T1 | 116/120 96.7% | 72/72 100.0% | +3.3 pp |

At the matched sampler all four contrasts sit within about three percentage points — 3.6
nominally ahead in three, behind by 0.2 pp in one — and on 3.8-side denominators of 44–65
cells a one-to-two-cell swing reverses any of them. Excluding the D1 cells from the
denominators instead of counting them as non-failures moves nothing outside noise
(no-think 85.7% vs 85.0%; think 91.4% vs 87.8%), so the reading does not hinge on the D1
treatment.

Two warnings that travel with this table:

- **The conditioning is the whole problem.** Delivery is exactly where the models differ,
  so conditioning on delivery conditions on a non-random subset — 3.8's delivered cells
  are its surviving runs. This describes graded work, never expected outcome per attempt.
- **The vendor-point gap survives correction.** 91.7% vs 77.2% (excluding D1 cells:
  91.4% vs 73.9%) is not explained by any of the three defects and is unresolved. It is
  also confounded by construction: the vendor design ties model identity to
  presence_penalty (pp=1.5 on 3.8's card, pp=0 on 3.6's), and its no-quality-confound
  replication (P1, pp=0 both sides) flips sign across scorings.

## Cost

Family-matched medians only (families differ by >10× in cost, and `completion_tokens` is
missing exactly for the cells that looped — 64 of 802, all ungraded — so unmatched pooled
medians are meaningless; comparability rules in [`results-tables.md`](results-tables.md) §4):

- **No-think, matched (P1):** token ratio ×0.86 over the 9 comparable families — but the
  excluded families (`p1_bugfix`, `p1_testwrite`, `p3_market`) are the expensive ones
  (×5.7 the median cost of the retained ones) and are excluded *because* 3.8's looping
  destroyed its cost accounting there. **Not readable as "3.8 is cheaper."**
- **Think (P3/P4):** token ratio ×2.18 / ×2.97, wall-clock ×2.20 / ×2.96. 3.8 pays a
  large thinking tax relative to 3.6 with no accompanying pass-rate gain.
- **Effort ladder (within 3.8 think):** no pairwise effort step is statistically
  distinguishable; `low` → `xhigh` raises median tokens 1.8–2.7× with no pass-rate change.
  The apparent cost non-monotonicity (`low` costing more than `medium` at T0.3) traces to
  the chat template — `medium` is the un-instructed baseline; `low` injects a brevity
  instruction that does not buy brevity — but it does not reproduce at T1 and is claimed
  only at that strength (see `bench.qwen38.reasoning-effort-cost-ladder`).

## Q8_0 quantization control

19 cells (2 replicates on the 7 phase-1/2 families, 1 on the 5 phase-3 families), 3.8
Q8_0, no-think, matched sampler. At freeze #1 this arm had zero graded cells; freeze #2
admits 8 (5 PASS, 3 FAIL), which upgrades it from existence-only evidence to **provisional
rates with wide intervals**:

- **Loop rate 6/19 = 31.6%, Wilson 95% [15.4%, 54.0%] — the interval excludes zero.** The
  identical-call loop occurs at Q8_0 at a real, non-negligible rate; it is not an artifact
  of the UD-Q4_K_XL quantization. Maximum identical-call runs: 110, 109, 81, 80, 71.
- **Against 3.8-Q4 at the same sampler, the loop rate is statistically indistinguishable**
  (29/95 = 30.5% vs 6/19 = 31.6%, Fisher p = 1.0) — consistent with quantization playing
  no role in the loop, though the Q8_0 interval is wide.
- **Quality stays near-uninformative.** Graded-only 5/8 = 62.5% [30.6%, 86.3%]; the vs-Q4
  contrast (78.5% vs 62.5%, p = 0.38) fails this entry's own power screen and no quality
  verdict is drawn. Of the three FAILs, two are length overruns by *both* word counters
  (D1 does not rescue them) and one is the D2 literalism (corrected to PASS).
- **There is no matched 3.6 Q8_0 arm**, so this is not a quant A/B: it can neither
  attribute the delivery regression to quantization nor exonerate it.

Per-cell detail is in [`results-tables.md`](results-tables.md) §6. One additional Q8_0
observation is unscored and excluded from every rate; it is reported in the next section.

## Qualitative exhibits

Three exhibits from the run evidence. These carry no statistical weight; they are here
because they show the *mechanisms* behind the numbers above.

### 1. The `copyfileobj` misdiagnosis spiral (`p1_bugfix`, 3.8 no-think)

`p1_bugfix_qwen38-nothink-offspec_v1` is one of the 10 loop-flagged 3.8 `p1_bugfix` cells
at the matched sampler. Its first nine iterations are exemplary: read the repo, run the
test suite, run the benchmark, reproduce the slowdown. At iteration 10 it decides to time
`load()` on a smaller slice of the 50 MB benchmark log, and builds the slice with:

```python
shutil.copyfileobj(open('benchmarks/bench_50mb.log','rb'),
                   open('/tmp/bench_5mb.log','wb'), 5*1024*1024)
```

The third argument of `copyfileobj` is the **copy buffer size, not a byte limit** — this
call copies the entire 50 MB file regardless. So the "5 MB slice" was 50 MB, `load()` on
it hit the 300 s bash timeout, and the probe returned nothing. The model's response to
the timeout was to shrink the slice: 1 MB (240 s timeout), 100 KB (120 s), 10 KB (60 s),
1 KB (30 s), 100 bytes (20 s) — and then, with an 8-second timeout, byte by byte: 35, 30,
25, 20, 15, 12, 11, 10, 9, 8, 7, and finally a **6-byte "slice"**, each probe still
silently copying all 50 MB and timing out identically. 41 probes over iterations 10–51,
every one the same template differing only in numerals, ~18 of the run's 30 wall minutes
spent inside them. At no point did the model question the slicing primitive; every timeout
was read as "the input is still too large." The operator SIGTERM'd it at iteration 52
under the ≥30-identical-digit-stripped-template rule.

This is what the +28 pp loop delta is made of: not gibberish, but a plausible debugging
strategy built on one wrong API assumption, iterated with perfect confidence and zero
self-correction. The transcript is preserved in the campaign archive
(`logs/` is not published in this repo; see Reproduction below).

### 2. The 90-day board signal (`p3_writing`): a real framing difference, and another keyword gate

The `p3_writing` CEO-brief spec requires "second-occurrence-in-90-days framing (board
signal)". The grader checks it with the keyword list
`["90 days", "90-day", "second time", "second 4"]`. On the 59 graded cells:

| Arm | Keyword hit |
|---|---|
| 3.8 (both modes, all samplers) | **21/21** |
| 3.6 think | 19/19 |
| 3.6 no-think | **8/19** (matched T0.3: 2/9; vendor T1: 6/10) |

3.8 preserves the source memo's own framing essentially verbatim, e.g.
(`p3_writing_qwen38-nothink-offspec_v1`):

> This is the second 4+ hour outage in 2026 (the first was the February database storage
> issue) — the second data point in 90 days.

But the 11 "missing" 3.6 no-think briefs are not missing the signal. Every one carries an
explicit board-signal line — e.g. (`p3_writing_qwen36-nothink-offspec_v1`):

> **Board Signal:** This is the second outage of 4+ hours in 2026. The first occurred in
> February. A third would compel a full reliability program review.

The honest reading is layered. There **is** a real, systematic difference: 3.8 (and 3.6
in think mode) reproduces the memo's sharp 90-day-window framing; 3.6 no-think reliably
paraphrases it into a calendar-year framing, dropping the 90-day window — the compression
that makes the signal urgent — and the paraphrase is near-identical across replicates
(fixed-seed replicate correlation; see KNOWN-LIMITATIONS). A CEO reading 3.6's version
gets a diluted signal. But the grader cannot see any of that: it can only see keywords, so
it scores "second outage of 4+ hours in 2026, first in February" — which contains the
second occurrence, the window's endpoints, and the escalation rule — identically to a
brief with no board signal at all. That is the same instrument shape as defect D2, in a
family this PR's overlay does **not** correct (only D1's length gate touches
`p3_writing`). The keyword rates above are reported as instrument readings, not as
"3.6 no-think misses the board signal."

### 3. The Q8_0 rewrite loop (unscored)

`p3_doc_qwen38q8-nothink-matched_v2` was quarantined in-flight at freeze #2 and is **not a
row in the frozen CSV**: it was observed 139 iterations deep in a rewrite loop —
re-emitting `brief.md` over and over with its context grown to ~228k tokens when
quarantined. This is a different failure subclass from the identical-call loop the
detectors count (`rewrite-loop` in
[`tooling/FAILURE-TAXONOMY.md`](../../tooling/FAILURE-TAXONOMY.md), first documented on
27B in `microbench-phase-b-2026-05-02`), it is UNSCORED, and it is excluded from every
rate and denominator in this entry. It is disclosed because a *second* loop subclass at
Q8_0 is qualitatively relevant to the quantization question even though it carries no
statistical weight.

## Grader defects, in one screen

Full report with sources, natural experiments, and per-cell appendix:
[`grader-defects.md`](grader-defects.md). Corrections are a non-destructive overlay
([`overlay/`](overlay/)); no `grade.json`, brief, or ground-truth file was modified.

| | D1 word-gate tokenizer mismatch | D2 `p3_pm` keyword literalism | D3 `p2_triage` brief contradiction |
| --- | --- | --- | --- |
| Families | `p3_business`, `p3_doc`, `p3_writing` | `p3_pm` | `p2_triage` |
| Mechanism | grader counts `\b\w+\b`, models budget with `wc -w`; 62 of 71 length-only FAILs are under every ceiling by `wc -w` | grader requires "legal hasn't"; 3.6 writes "legal has not" | brief defines urgency `n/a` for spam; ground truth never uses it; all 64 cells penalized identically for complying |
| Verdict changes | 62 gate invalidations (23 of 3.6, 39 of 3.8) | 36 flips (31 / 5) | 24 flips (21 / 3) |
| Direction | favours 3.6 uncorrected | favours 3.8 uncorrected | favours 3.8 uncorrected |
| After correction | gate is not a valid discriminator | family saturates (61/64) | family saturates (64/64) |

The three defects do not push the same way, and in each case the correct conclusion is
"this gate does not measure what the benchmark claims", not "the other model actually
won". Under the shipped graders the three length-gated families read as a 34-point win
for 3.6 (64.9% vs 30.4%); with the other equally-defensible counter they read as a 2-point
win for 3.8 (85.1% vs 87.0%). The gate was deciding the headline.

D2 has a process finding worse than the grader bug: the repository already contained the
tested fix (`tooling/correct_gemma4_project_mgmt_grades.py`) — it never ran on these
campaigns because its cell enumeration was hardcoded to `p3_pm_gemma4-31b-q4_v{n}` names.
Prior-campaign exposure is measured in
[`grader-defects.md`](grader-defects.md) § What these defects mean for previously
published MMBT results: 2 of 10 Gemma4 `p2_triage` verdicts flip; every published
`p2_triage` urgency accuracy for every model is understated by 0.100; DeepSeek's verdicts
stand.

## Retractions

Five conclusions drawn earlier in this investigation are retracted in
[`claims.yaml`](../../claims.yaml) (entries persist there permanently; each carries its
full reason):

1. `bench.qwen38.nothink-abort-rate` — an operator-label-based "abort rate"; the label
   disagrees with the mechanical loop signal in both directions (24 of 802 cells).
2. `bench.p3_pm.qwen38-outscores-qwen36` — "3.8 wins p3_pm 17/21 vs 4/37"; the gap was
   lexical (D2). Corrected: 26/26 vs 35/38, near-saturation.
3. `bench.p2_triage.family-result` — "3.8 wins p2_triage 19/22 vs 16/37"; the split was a
   uniform 0.100 penalty interacting with a threshold (D3). Corrected: 64/64.
4. `bench.family-paired.nine-three` — a 9–3 family win split; not reproducible from the
   frozen data at any sampler, not stable under correction, and built on the two defect
   families above.
5. `bench.thinking.default-vs-default` — a thinking comparison described as
   "default vs default"; the only shared think sampler is 3.6's vendor point, and 3.8's
   think arms are effort mixtures. Nothing was ever run at 3.8's own vendor think point.

## What we did not run

- **No 3.8 think arm at 3.8's own vendor sampler (T0.7/p0.8/pp1.5).** This is the largest
  hole in the comparison and cannot be patched by re-analysis; the cross-model thinking
  question is formally held (`bench.qwen38-vs-qwen36.thinking-quality-head-to-head.held`).
  Running it at a fixed effort level is the single highest-value follow-up.
- **No matched 3.6 Q8_0 arm**, so the quant question stays open (a Q8_0 arm at N≥5 per
  family for both models, graded, would close it).
- **No hand-graded quality pass.** Every phase-3 grader is a keyword/word-count
  instrument, and every hand-rating slot in all 292 phase-3 `grade.json` files is null.
  Corrected pass rates inherit that limit in full.
- **No seed sweep** — 802 cells, one seed.

## Reproduction

Everything derives from [`data/mmbt-frozen-dataset-v2.csv`](data/mmbt-frozen-dataset-v2.csv)
(sha256 `d2ed0bec…`, stamp `2026-08-16T14:23:09Z`) plus immutable run artifacts.

- **Tables:** [`tooling/build_results.sh`](tooling/build_results.sh) runs
  `test_stats.py` (estimator self-validation against defining equations),
  `mmbt_results.py` (writes `results.json`), `defect_diag.py` (appends grader-defect
  diagnostics), `make_md.py` (renders `results-tables.md`). Pure python3 stdlib. The
  rebuild is deterministic — two runs produce byte-identical output.
- **Overlay:** [`tooling/apply_grade_corrections.py`](tooling/apply_grade_corrections.py)
  `--dataset <csv>` regenerates [`overlay/`](overlay/);
  [`tooling/verify_overlay.py`](tooling/verify_overlay.py) checks idempotence (byte-identical
  re-run, stable digest), the leniency invariant (corrections only ever flip FAIL→PASS;
  686 cells checked, 0 violations), the write guard (`grade.json` / `receipt.json` /
  tasks / ground_truth refuse writes; 853 protected files hash-verified unmutated), and
  the empty `post_freeze_divergence` ledger.
- **Cross-file consistency:** [`tooling/validate_fixes.py`](tooling/validate_fixes.py)
  recomputes every corrected rate, defect count, win count, and Q8_0 figure from the
  frozen CSV plus overlay and checks them against this entry's documents — 174 checks.
- **Freeze:** [`tooling/freeze_dataset.py`](tooling/freeze_dataset.py) is the script that
  produced the CSV from the run checkouts (identity from `receipt.json`, never from
  directory names).
- **Fastest single check** (D2's natural experiment, three commands, no scripts):
  [`grader-defects.md`](grader-defects.md) Appendix B. Expect `card_v2`/`card_v8`
  ("Legal has not responded") to FAIL at `risk_recall 2/6` and `card_v4`
  ("Legal hasn't responded") to PASS at `3/6` with every other score identical.

Two practical notes. The scripts' default dataset paths point at the freeze location on
the bench host (`/home/michael/mmbt-frozen-dataset-v2.csv`); the identical CSV ships in
this entry's `data/`. Raw `logs/` (transcripts, workspaces, `grade.json`) are not in this
repository per `REPO-SPACE.md` — the overlay records carry the sha256 of every raw file
they touched, so any single correction is checkable in isolation against the archive.

## Relation to prior MMBT entries

- The loop subclasses seen here are the ones first catalogued in
  [`microbench-phase-b-2026-05-02/findings.md`](../microbench-phase-b-2026-05-02/findings.md)
  (`scroll-loop`, `word-trim-loop`, `rewrite-loop`); the copyfileobj spiral is a
  scroll-loop-shaped probe loop, and the Q8_0 quarantined cell is a rewrite-loop. The
  ≥30-identical-digit-stripped-template SIGTERM rule from that entry was the operator
  policy for this campaign.
- The grader-defect findings retroactively affect prior campaigns that used the
  byte-identical graders (Gemma4, DeepSeek V4 Flash) — quantified in
  [`grader-defects.md`](grader-defects.md). The `p2_triage` understatement applies to
  every campaign ever published from these graders.
- This is the first MMBT entry built from a frozen dataset with a stamped freeze,
  non-destructive correction overlay, and machine-checked document consistency
  (`validate_fixes.py`). The freeze discipline exists because live re-scans during this
  investigation moved headline percentages by 4–9 points between passes.