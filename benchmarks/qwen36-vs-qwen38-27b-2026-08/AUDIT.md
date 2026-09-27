> [!IMPORTANT]
> **EXPLORATORY — notice added 2026-08-16 per the corrective protocol, section 9. No number
> or audit statement below has been altered; this notice is prepended only.**
>
> 1. **Arm mislabel (V36 vendor no-think).** The arm this bundle labels "3.6 vendor
>    no-think" ran Qwen3.6-27B at its **thinking** sampler (T1.0 / top_p 0.95 /
>    presence_penalty 0) with thinking disabled — off-spec per the pinned Qwen3.6-27B card
>    (rev `6a9e13bd`, README L637: official non-thinking is T0.7 / top_p 0.80 / top_k 20 /
>    min_p 0 / pp 1.5 / rp 1, identical to Qwen3.8-27B). The "vendor vs vendor" no-think
>    contrast is mode/sampler-confounded, and the corpus contains **no cell of Qwen3.6
>    non-thinking at its official sampler**.
> 2. **Cell-level Fisher exact values in this bundle are descriptive only.** They treat
>    cells as independent and are anti-conservative under family/seed clustering.
> 3. **The 802-cell freeze audited here is exploratory evidence** and feeds no confirmatory
>    claim. The confirmatory design, arms, fixed N, and analysis plan are preregistered at
>    [`../qwen36-vs-qwen38-corrective-2026-08/PREREGISTRATION.md`](../qwen36-vs-qwen38-corrective-2026-08/PREREGISTRATION.md);
>    the pinned-card sampler evidence is recorded at
>    [`../qwen36-vs-qwen38-corrective-2026-08/protocol/CARD-EVIDENCE.md`](../qwen36-vs-qwen38-corrective-2026-08/protocol/CARD-EVIDENCE.md).

# AUDIT — Qwen3.6-27B vs Qwen3.8-27B agentic comparison (2026-08-16)

This bundle compares two model generations on the 12-family MMBT microbench. The headline is a
**delivery-reliability** finding, not a capability finding, and the distinction is load-bearing:
the two models are statistically indistinguishable on the work they deliver once three verified
grader defects are corrected. This document states exactly what is locked, what varies, what the
comparison can and cannot support, and every bias we know of — including the ones that cut
against our own headline.

**Frozen snapshot: `2026-08-16T14:23:09Z` (freeze #2).** Every number in this bundle derives
from `data/mmbt-frozen-dataset-v2.csv` (802 cells) and nothing else. All campaign processes were
stopped and in-flight cells quarantined *before* this freeze was taken, so the corpus is static.
An earlier freeze (746 cells, 11:49:14Z) is superseded; during the live-corpus phase of the
investigation, figures drifted 4–9 pp between recomputations — that is why the freeze discipline
exists, and readers should treat any number without this stamp as stale.

---

## What is locked across both models

- **Task definitions.** Exactly one task sha256 per family across all five checkouts, 12/12
  families. Neither model saw a different brief.
- **Harness.** `harness.py` file_sha256 `b6656a23737ef89e…` on 800 of 813 receipts corpus-wide;
  the 13 non-canonical receipts are early bring-up and excluded-arm cells (2 on the previously
  disclosed `fdbc1584074f36d9…`, 11 across five minor variants). Same agent loop, same tool
  surface, same stuck detector across every headline comparison.
- **Graders.** All 11 grader `.py` files byte-identical across all five checkouts
  (e.g. `phase3_business_memo_grade.py` md5 `9b94cfcd09aa7bbed0e03a6e5cc600a3`). All 7
  `ground_truth/*.json` byte-identical. Zero model-conditional or arm-conditional logic, verified
  by three independent scans with a positive control proving the files were actually read.
  Graders are stdlib-only with hardcoded thresholds and open fixed relative filenames, so they
  cannot branch on arm implicitly.
- **Grader provenance at run time.** All post-fix `receipt.json` files record a single
  `grade_microbench_sha256` across both models.
- **Engine.** Same llama.cpp container image digest `sha256:0c8dc7c0954f…`, same
  `/app/llama-server` entrypoint, same flags (`--n-gpu-layers 999 --ctx-size 262144
  --batch-size 2048 --threads 4 --parallel 1 --flash-attn on --cache-type-k q8_0
  --cache-type-v q8_0 --jinja --reasoning-format none --no-context-shift --metrics`). Only
  `--model` and `--alias` differ between lanes.
- **Generation caps.** `max_iters = 10000` and `max_completion_total_default = 1e12` for every
  cell of both models. The longest observed cell is 565 tool calls. **Nothing was truncated by a
  cap**, so no result here is an artifact of an artificial ceiling.
- **Seed.** `seed = 42` on every cell.
- **Model attribution.** Taken per cell from the live endpoint capture in `receipt.json`, never
  from directory names. Zero mismatches against arm label across all in-scope cells. This matters
  because one arm named `…-offspec` was found to actually carry the vendor-card sampler.

---

## What varies

| axis | Qwen3.6 | Qwen3.8 | why / status |
|---|---|---|---|
| **Weights** | `Qwen3.6-27B-UD-Q4_K_XL` | `Qwen3.8-27B-UD-Q4_K_XL` | the intended variable |
| **Quantization grade** | ftype `Q4_K - Medium` | ftype **`Q4_K - Small`** | **NOT MATCHED — see B2** |
| **Vendor sampler** | T1.0 / top_p 0.95 / pp 0.0 | T0.7 / top_p 0.8 / **pp 1.5** | each model's own published point |
| **Matched sampler** | T0.3 / top_p 0.8 / pp 0.0 | identical | one distinct config block across all cells in this regime |
| **Thinking control** | binary `enable_thinking` | `reasoning_effort` ∈ {xhigh (default), medium, low} | genuinely new in 3.8; `high` is an alias for `xhigh` (verified byte-identical at seed 42) |
| **Replicate depth** | 9–19 per family per regime | 7–13 (matched) / 8 (vendor) | **NOT MATCHED — see B4** |
| **Host** | tower3 / tower2-gpu1 | tower1 / tower2-gpu0 | **confounded in the card regime — see B3** |

---

## What this bundle CAN support

- **A non-thinking-mode delivery-reliability regression in Qwen3.8 relative to Qwen3.6**, at both
  each model's own vendor sampler and at a byte-identical matched sampler, driven by
  byte-identical tool-call repetition loops concentrated in long-horizon coding families.
- **That the loop is not an artifact of the harness.** The container-death signature
  (`wall_s ≤ 0.05 ∧ 130 ≤ result_len ≤ 200`) returns **0 hits** across all flagged cells while
  firing 45–502× per cell on a 20-cell positive control of known container deaths. An independent
  channel using neither timing nor size agrees: the known-artifact cells repeat trivial probes
  (`echo hi`, `sleep 3600` returning 148 bytes in 0.01 s) while flagged cells repeat substantive
  work at 0.06–8.63 s.
- **That the loop is not an artifact of quantization — as a provisional rate.** At Q8_0
  (near-lossless) the loop rate is 6/19 = 31.6% (Wilson [15.4, 54.0], excluding zero) against
  the Q4 build's 29/95 = 30.5% — Fisher exact p = 1.0, the two builds indistinguishable — with
  the loops landing in the same families. See B2 for the residual limits.
- **That, conditional on delivering, the two models are indistinguishable** once D1–D3 are
  corrected.
- **A cost ordering within Qwen3.8's reasoning-effort ladder**, including its non-monotonicity.

## What this bundle CANNOT support

- **Any model-family generality.** One quant per model, no crossover build, no perplexity/KL
  fidelity check. Claims are about **these specific GGUF builds**.
- **Any causal account of the loop.** Tool result **bodies are never stored** — only
  `result_len`. Nothing here can establish whether the repeated command was erroring, returning
  empty, or succeeding. Any transcript grep for error text is a **null test** that returns
  nothing regardless of truth; it fires on 1 of 20 known container deaths.
- **Anything about Qwen3.8 thinking at Qwen3.8's own vendor sampler.** Every 3.8 thinking arm in
  this corpus ran at T1.0/0.95/pp0.0 — **Qwen3.6's** vendor point. No such run exists. Any
  "vendor default thinking" comparison is unsupported.
- **Output quality in any deep sense.** No phase-3 grader contains a fabrication, correctness or
  quality check; `hand_rating_placeholders` is `null` corpus-wide.
- **Generality to other quants, serving stacks, harnesses, or task sets.**
- **Multi-user serving.** Every lane ran `--parallel 1`.

---

## Bias list

### B1. The operator abort label is not a consistent rule — and we stopped using it
An earlier version of this finding was built on `label.json`, the operator-terminated pathology
marker. It is not consistently applied in either direction: one cell repeated a command **250
times** and was graded **PASS**, never aborted; another was aborted at a maximum repeat frequency
of **1**. Whether a run lands in the abort bucket partly measures operator attention.
**Mitigation:** the published metric is derived from `transcript.jsonl` alone and never reads
`label.json`. The abort-rate framing is formally retracted in `claims.yaml`.

### B2. Quantization is not matched between the models — but the Q8_0 control closes the main question
3.8 is `Q4_K - Small`; 3.6 is `Q4_K - Medium`, so quant damage could not be separated from model
behaviour by the Q4 arms alone. The Q8_0 control was run for exactly this reason and, at
freeze #2, it carries **19 cells across 12 families (8 graded: 5 PASS / 3 FAIL)** with a loop
rate of **6/19 = 31.6%** — statistically indistinguishable from the Q4 build (29/95 = 30.5%,
Fisher p = 1.0) and landing in the same families. Near-lossless quantization does not remove the
regression: **it is the model, not the build.** Residual limits, disclosed rather than waved
away: the arm is thin (per-family n ≈ 1–2), its graded-quality comparison is underpowered
(5/8 vs Q4, Fisher p = 0.38), no perplexity/KL fidelity check was run on either build, and both
GGUFs come from a single quantizer (unsloth). One additional Q8_0 cell — a 139-iteration
rewrite-loop that grew its context to ~228k — was quarantined in-flight and is reported as
**unscored** qualitative evidence only.

### B3. Host is confounded with model in the card regime
All `qwen38-nothink-card` cells ran on tower1; all `qwen36-nothink-card` and `qwen36-think-card`
cells on tower3. Zero crossover inside the scored arms. **Partially broken by out-of-scope
evidence:** an excluded arm at the same sampler ran cells on *both* hosts and flagged on both,
including on the identical GPU UUID that served every 3.6 card cell at zero flags. The effect
follows the weights across machines. The matched-sampler regime is not host-confounded in the
same way.

### B4. Replicate depth is unbalanced by design
3.6 reached 9–19 replicates per family per regime; 3.8 is at 7–13 (matched) / 8 (vendor), and
the thinking arms are thinner and effort-mixed (see the group inventory). Extra 3.6 replicates
can only tighten 3.6's interval — they cannot manufacture the gap — but every headline is
additionally reported **depth-matched** so a reader does not have to take that on faith.

### B5. The matched-sampler regime is not symmetric in what it costs each model
Running both models at pp 0.0 strips Qwen3.8 of the `presence_penalty 1.5` its model card
specifies (an anti-repetition measure) while costing Qwen3.6 nothing, since its vendor pp is
already 0.0. This regime is **not neutral**. It does not rescue 3.8 — the regression is present
at 3.8's own vendor sampler with pp 1.5 applied, and the matched pair (pp 0 on both sides)
still shows a ~+28 pp loop delta — but the asymmetry must be disclosed, and the missing 2×2
cell (3.6 at pp 1.5) has not been run.

### B6. seed=42 induces replicate correlation — not determinism — and the power loss is unquantified
No two same-arm same-family replicates are byte-identical (checked by SHA-256 on transcripts;
llama.cpp continuous batching breaks determinism), and verdicts flip within replicate groups.
What does hold is correlation: 5.4% of replicated cells at T0.3 (17/316) share an exact
completion-token count with a sibling, 3.6% at T1 (10/276), 0/76 at the 3.8 vendor point.
Effective n is therefore somewhat below nominal n, by an amount this bundle does not quantify;
per-family fractions in the matched regime should be read as texture, not rates.

### B7. Three grader defects, all corrected non-destructively, all in 3.8's favour when corrected
See `grader-defects.md`. Summary: a word-count gate whose tokenizer disagrees with the counter
both models demonstrably budget against (the correction *invalidates the gate* — recorded as
`gate_invalidated`, not as a verified PASS); a `p3_pm` risk-recall gate whose applied fix is the
repo's own R3 adjacency rule, with the contraction pair as the decisive natural experiment; and
a `p2_triage` ground truth that contradicts its own brief and penalised **64/64 graded cells of
both models**. All corrections are strictly leniency — no cell flips from PASS to FAIL under any
of them. **Disclosure:** the repo already contained an unapplied fix for the second
(`tooling/correct_gemma4_project_mgmt_grades.py`, unit-tested, hardcoded to a different model's
cell names). A reviewer will find it, so we say it here. Post-correction, `p2_triage` (64/64)
and `p3_pm` (61/64) saturate and carry **no discriminating weight** in any headline.

### B8. An interim arm whitelist dropped cells anti-conservatively — resolved by inclusion
Interim analyses during the investigation hardcoded a set of arm labels and skipped 95
non-quarantined cells; the exclusion worked *against* the eventual headline (the skipped clean
cells add flagged 3.8 cells and zero flagged 3.6 cells). The published pipeline resolves this:
the group inventory in `results-tables.md` **pools every arm at its receipt-derived sampler
point**, including the formerly skipped ones, and lists the pooled arm labels per group so the
numbers are reproducible from the stated composition. The interim exclusion is disclosed here
because earlier circulated figures were computed under it.

### B9. `p3_market` is a live-internet task
Arms ran on different days against changing external endpoints. Any `p3_market` result carries an
uncontrolled network confound. One of Qwen3.6's three no-think loops is a `curl` retry loop
against an external pricing endpoint — a network-retry loop, not a reasoning loop.

### B10. The container-artifact era, and why the time gate was retired
A harness bug removed sandbox containers mid-run and was misread for hours as model behaviour;
it is fixed (cleanup scoped by campaign label). Analysis was initially gated to transcripts newer
than the fix. That gate was **retired** after a retrospective scan applied the real signature to
all 159 surviving pre-fix cells and found **zero** contaminated — the damaged cells had already
been quarantined. Two container deaths were later found to have occurred *after* the fix and were
caught by operator quarantine, so **"post-fix therefore clean" is false as a rule**: cells are
clean because they were tested, not because of their timestamp.

### B11. Fifteen loop-killed cells left recoverable workspaces — unresolved
SIGTERM skips the final `tar czf` but leaves the host workspace; at freeze #2, 15 of the 64
operator-labelled cells have one. A probe graded a subset and reported four PASSes, three of
them 3.8 cells currently counted as all-cells failures; recovering them would move 3.8's matched
all-cells rate by several pp. This did **not** survive verification as stated and is **open**.
It is the live objection that attacks the strongest surviving finding most directly, and it is
listed as future work rather than quietly resolved in our favour.

---

## Reproducing

From this entry directory (`benchmarks/qwen36-vs-qwen38-27b-2026-08/`):

```bash
python3 tooling/test_stats.py                    # validate the estimator implementations
python3 tooling/mmbt_results.py                  # regenerate results.json from data/mmbt-frozen-dataset-v2.csv
python3 tooling/make_md.py                       # render results-tables.md (byte-identical rebuild)
python3 tooling/apply_grade_corrections.py --dry-run   # D1-D3 overlay summary, writes nothing
```

Regeneration is deterministic: the committed `results.json` and `results-tables.md` rebuild
byte-identically from the committed CSV + overlay (modulo three absolute-path provenance
strings; see the PR notes). `tooling/freeze_dataset.py` documents how the CSV was derived from
the raw corpus. Raw per-run logs and agent workspaces are **not published** (`/logs/` is
gitignored; the workspace tarballs alone are ~1.5 GB). The frozen dataset carries one row per
cell with the outcome, sampler, repetition metrics and token counts needed to re-derive every
published number. Anyone wanting the raw corpus should open an issue.
