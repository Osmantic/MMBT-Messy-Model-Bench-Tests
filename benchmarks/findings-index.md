# Findings index

Cross-cutting analyses that synthesize across multiple model entries or benchmark runs. Listed newest-first.

| Doc | Date | One-line summary |
|---|---|---|
| [`qwen36-vs-qwen38-27b-2026-08/findings.md`](qwen36-vs-qwen38-27b-2026-08/findings.md) | 2026-08-16 | Qwen3.6-27B vs Qwen3.8-27B head-to-head at UD-Q4_K_XL (802 frozen cells + 19-cell Q8_0 control). The one large effect is a no-think delivery regression (+28-29 pp identical-call-loop rate, p <= 4.9e-09), not a capability gap - corrected pass-given-delivery is within noise at the matched sampler. Three MMBT grader defects found and corrected via non-destructive overlay; five earlier conclusions retracted in `claims.yaml`. |
| [`deepseek-v4-flash-0731/DEEPSEEK_V4_FLASH_0731_VERIFIED_RESULTS.md`](deepseek-v4-flash-0731/DEEPSEEK_V4_FLASH_0731_VERIFIED_RESULTS.md) | 2026-08-01 | Fully optimized DeepSeek V4 Flash campaign: canonical 35/36 corrected, complete N=3 single-PR runs, strict finance and deck audits, and 0/3 full-context frozen 75-PR outcomes including an 815,279-token terminal runaway. |
| [`microbench-phase-b-2026-05-02/findings.md`](microbench-phase-b-2026-05-02/findings.md) | 2026-05-02 | N=10 expansion + 27B-no-think third arm. Three identical-call-loop subclasses (`scroll-loop`, `word-trim-loop`, `rewrite-loop`). Per-cell ship rates with Wilson CIs, cost-per-shipped-run, "when to use which" updates. |
| [`microbench-phase-b-2026-05-02/findings-pairwise-quality-three-model.md`](microbench-phase-b-2026-05-02/findings-pairwise-quality-three-model.md) | 2026-05-03 | Hand-graded deliverable quality study on the both-ship cells (p2_ci, p2_extract, p2_triage). Headline: 27B-thinking and 27B-no-think substantively equivalent on output decisions; Coder-Next has a distinct reasoning style. **Includes a load-bearing correction to the 2026-04-28 study's `p2_ci` regression attribution.** |
| [`microbench-2026-04-28/findings.md`](microbench-2026-04-28/findings.md) | 2026-04-28 | Original 12-task-family × 2-model × N=3 microbench writeup. Daily-driver guide framework, 27B word-limit-trim failure mode, market-research inversion (27B drives internet research that Coder-Next doesn't). Still load-bearing for the 8 cells phase-b didn't expand. |
| [`dreamserver-75-pr-audit/findings-2026-04-27-local-models.md`](dreamserver-75-pr-audit/findings-2026-04-27-local-models.md) | 2026-04-27 | Cross-cutting comparison of the local-model entries against the cloud entries on the 75-PR audit. Documents the categorical cloud-vs-local gap and the per-local-model failure shapes. |
| [`dreamserver-1-pr-audit/findings-2026-04-27-strict-done-ablation.md`](dreamserver-1-pr-audit/findings-2026-04-27-strict-done-ablation.md) | 2026-04-27 | Ablation: does enforcing a strict `done()` requirement change the verdict-accuracy picture on the 1-PR audit? |

## Reading order recommendations

**For the 5-minute model-selection question**: Start with [`../COMPARISON.md`](../COMPARISON.md), not the findings docs. The findings docs are the evidence base; COMPARISON is the synthesis.

**For the newest high-capability local-model campaign**: `deepseek-v4-flash-0731/DEEPSEEK_V4_FLASH_0731_VERIFIED_RESULTS.md`.

**For the most current N=10 picture**: `microbench-phase-b-2026-05-02/findings.md`.

**For deliverable-quality differences when models all ship**: `findings-pairwise-quality-three-model.md`.

**For long-horizon agentic failure modes**: `dreamserver-75-pr-audit/findings-2026-04-27-local-models.md`.

**For the original 12-cell N=3 baseline (still current for the 8 non-Phase-B cells)**: `microbench-2026-04-28/findings.md`.
