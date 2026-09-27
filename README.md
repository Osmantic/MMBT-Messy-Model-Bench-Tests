# MMBT - Messy Model Bench Tests

This repository stores messy, real-world benchmark outputs from different
hardware and LLM tests in my lab.  It's my messy research, and exists for my personal use
but I'm making it public so that other people can use it too.

## Five-minute answers

| If you want to know… | Read |
|---|---|
| **First-time reader: how to weigh anything in here** | [`HOW-TO-READ.md`](HOW-TO-READ.md) — repo layout, status vocabulary, reading order |
| Every claim in this repo with a status tag | [`claims.yaml`](claims.yaml) — strong / provisional / held / retracted matrix |
| What we **didn't** measure (and where PRs are welcome) | [`NOT-HERE-YET.md`](NOT-HERE-YET.md) |
| What this evidence can and can't support | [`KNOWN-LIMITATIONS.md`](KNOWN-LIMITATIONS.md) — caveats on what we did measure |
| Where the benchmark folders start | [`benchmarks/README.md`](benchmarks/README.md) — agent-task benchmark landing page |
| **"Coder-Next or 27B (or 27B-no-think) for my task?"** | [`COMPARISON.md`](COMPARISON.md) — head-to-head decision doc |
| The full single-table comparison across all entries | [`SCORECARD.md`](SCORECARD.md) |
| **Gemma 4 31B QAT Q4: complete verified campaign** | [`benchmarks/gemma4-31b-q4/`](benchmarks/gemma4-31b-q4/) — native-256K serving, canonical N=3/N=10, strict artifact audits, and Qwen3.6-27B comparison |
| **DeepSeek V4 Flash 0731: complete verified campaign** | [`benchmarks/deepseek-v4-flash-0731/`](benchmarks/deepseek-v4-flash-0731/) — deployment, canonical N=3, extended suites, strict artifact audits, and full-context 75-PR outcomes |
| **Four-card DSV4.1 cooling at 275 W per GPU** | [`hardware-tests/tower2-four-gpu-dsv41-fans-2026-09-27/`](hardware-tests/tower2-four-gpu-dsv41-fans-2026-09-27/) — uniform fan curve, native RAM offload, measured decode/noise tradeoff, persistent controller, raw evidence and explicit qualification limits |
| **All 12-family microbench results (across both trees) + the four "27B"s** | [`MICROBENCH-INDEX.md`](MICROBENCH-INDEX.md) — cross-tree microbench index + quant disambiguation |
| Cross-model **qualitative** spot-grades (provisional, not a ranking) | [`QUALITATIVE-SPOT-GRADES.md`](QUALITATIVE-SPOT-GRADES.md) + [`tooling/QUALITATIVE-GRADING-PROTOCOL.md`](tooling/QUALITATIVE-GRADING-PROTOCOL.md) — single-grader provisional scores + grader-independence rules |
| How repo size is managed | [`REPO-SPACE.md`](REPO-SPACE.md) — storage hotspots and artifact policy |
| How to benchmark a new local model | [`tooling/ADDING-A-MODEL.md`](tooling/ADDING-A-MODEL.md) |
| How to replay a specific past run | [`tooling/REPRODUCING.md`](tooling/REPRODUCING.md) |

## Operating point (read before quoting)

Most earlier agent-task benchmarks under [`benchmarks/`](benchmarks/) use **Cyankiwi 4-bit AWQ** quants on **2x RTX PRO 6000 Blackwell at 500 W cap**. DeepSeek V4 Flash 0731 and Gemma 4 31B are explicit exceptions: DeepSeek uses official FP4 weights, FP8 KV, and a validated 1,048,576-token context; Gemma uses Google's official QAT Q4_0 GGUF, Q8 KV, llama.cpp, and a validated native 262,144-token context per slot. Every entry README pins its own operating point. Other quants, VRAM tiers, hardware classes, and languages other than Python are **not characterized** unless an entry says otherwise. See [`COMPARISON.md` section "What this benchmark doesn't characterize"](COMPARISON.md#what-this-benchmark-doesnt-characterize) for the model-benchmark validity boundaries, and [`ROADMAP.md`](ROADMAP.md) for what's queued to fill those gaps.

Rig-characterisation studies under [`hardware-tests/`](hardware-tests/) have their own operating-point scope. Start with [`hardware-tests/README.md`](hardware-tests/README.md) before quoting hardware claims. In particular, [`hardware-tests/qwen3.6-q8-fleet-2026-05-17/`](hardware-tests/qwen3.6-q8-fleet-2026-05-17/) ranks four hardware classes on **Q8_0 GGUF** dense and MoE workloads under llama.cpp, with a Tower2 vLLM-FP8 appendix row for the MoE model the llama.cpp/CUDA path crashes on.

## Layout

```text
benchmarks/
  README.md                    agent-task benchmark landing page and navigation map
  gemma4-31b-q4/               complete Gemma campaign, N=3/N=10, strict audits, comparisons
  deepseek-v4-flash-0731/      cross-suite DeepSeek campaign, strict audits, and deployment evidence
  dreamserver-75-pr-audit/
    GPT-5.5/                   cloud, full audit
    Opus-4.7/                  cloud, full audit
    Qwen3.6-27B-AWQ/           local 30B-class, structurally complete + substantively partial
    Qwen3-Coder-Next-AWQ/      local MoE 80B/3B, no deliverable (failure-mode entry)
    findings-2026-04-27-local-models.md   cross-cutting writeup
  dreamserver-1-pr-audit/
    Qwen3-Coder-Next-AWQ/      local, single-PR deliverable (correct verdict, but variance-dominated — see entry README)
    Qwen3.6-27B-AWQ/           local, partial deliverable (excellent analysis, no verdict.md shipped)
    Qwen3.6-35B-A3B-AWQ/       local, floor failure (no artifacts produced)
  wallstreet-intern-test/
    GPT-5.5/                   cloud, full memo repo + board-of-advisors deck
    Opus-4.7/                  cloud, full memo repo
    Qwen3.6-27B-AWQ/           local, full memo repo (GTLB BUY, 1 of 3 runs shipped)
    Qwen3-Coder-Next-AWQ/      local, full memo repo (DOCU BUY, 1 of 3 runs shipped — verdict reliability caveat in README)
    Qwen3.6-35B-A3B-AWQ/       local, no usable deliverable (0 of 3 runs shipped, kept as failure-mode entry)
hardware-tests/
  README.md                       hardware-test landing page: coverage matrix, settled vs held questions
  vllm-power-sweep-2026-04-29/ rig characterisation: vLLM throughput vs GPU power cap, 28-cell sweep with raw CSVs + audit notes
  tower2-dual-qwen27-600w-2026-07-29/ 30 min dual-GPU 600 W thermal saturation run
  tower2-dual-qwen27-no-gap-2026-07-29/ adjacent-card 600/400 W transient and steady-state thermal runs
  qwen3.6-q8-fleet-2026-05-17/ cross-platform dense + MoE Q8 hardware comparison
  local-ai-hardware-valuation-2026-05-17/ recomputable buyer valuation worksheet
```

## Benchmarks

| Benchmark | Prompt Shape | Model Entries |
|---|---|---|
| [`gemma4-31b-q4`](benchmarks/gemma4-31b-q4/) | Cross-suite publication: full 12-family N=3 and N=10, single-PR N=3, investment research, board presentation, and frozen 75-PR N=3. | `Gemma-4-31B-it-QAT-Q4_0`; includes immutable raw grades, a narrow corrected overlay, strict substantive audit, and Qwen3.6-27B comparison. |
| [`deepseek-v4-flash-0731`](benchmarks/deepseek-v4-flash-0731/) | Cross-suite publication: full 12-family N=3, single-PR N=3, investment research, board presentation, and three valid full-context frozen 75-PR outcomes. | `DeepSeek-V4-Flash-0731`; includes corrected grader overlay and compact audit evidence. |
| [`dreamserver-75-pr-audit`](benchmarks/dreamserver-75-pr-audit/) | Audit 75 open PRs in a live repository and produce a traceable maintainer triage repo. | `GPT-5.5`, `Opus-4.7`, `Qwen3.6-27B-AWQ`, `Qwen3-Coder-Next-AWQ` (failure-mode entry) |
| [`dreamserver-1-pr-audit`](benchmarks/dreamserver-1-pr-audit/) | Same task spec, scaled to a single PR. Built as the floor of an escalation ladder (1 → 2 → 4 → 8 → 16 → 32) to find each model's complexity ceiling. | `Qwen3-Coder-Next-AWQ`, `Qwen3.6-27B-AWQ`, `Qwen3.6-35B-A3B-AWQ` (floor failure) |
| [`wallstreet-intern-test`](benchmarks/wallstreet-intern-test/) | Build a traceable investment memo repo with raw sources, extracted data, a three-statement model, valuation, and recommendation. | `GPT-5.5`, `Opus-4.7`, `Qwen3.6-27B-AWQ`, `Qwen3-Coder-Next-AWQ`, `Qwen3.6-35B-A3B-AWQ` (failure-mode entry) |
| [`microbench-2026-04-28`](benchmarks/microbench-2026-04-28/) | 12 smaller-scope task families (5-30 min deliverables) split across 3 phases — coding (Phase 1), structured business tasks (Phase 2), unbounded business/writing (Phase 3). Designed to surface task-class-specific differences between local 30B-class quantizations. N=3 per cell. Three highest-signal task families published as full per-model entries: adversarial-hallucination, market-research, doc-synthesis. | `Qwen3.6-27B-AWQ`, `Qwen3-Coder-Next-AWQ` |
| [`microbench-phase-b-2026-05-02`](benchmarks/microbench-phase-b-2026-05-02/) | Bumps the four highest-signal cells of `microbench-2026-04-28` from N=3 → N=10 to bound the headline failure rates with proper Wilson CIs, and adds **27B-no-think** as a third arm across the **full 12-family grid** (~240 runs total). Settles the `p3_doc` 27B word-trim loop as a stable ~40% failure shape, and bounds Coder-Next's `p3_market` 0/3 STRUCTURAL_FAIL as 0/10 at N=10 (Wilson 95% [0%, 27.8%]). | `Qwen3.6-27B-AWQ` (thinking), `Qwen3.6-27B-AWQ` (no-think), `Qwen3-Coder-Next-AWQ` |

For the benchmark landing page and per-folder navigation map, start with
[`benchmarks/README.md`](benchmarks/README.md).

## Hardware tests

`hardware-tests/` holds rig characterisation runs — power, throughput, and thermal sweeps on the lab hardware itself, separate from agent-task benchmarks. Start with [`hardware-tests/README.md`](hardware-tests/README.md): it makes the dense-vs-MoE coverage, backend exceptions, and "settled vs held" boundaries explicit.

| Test | Shape | What it measures |
|---|---|---|
| [`tower2-four-gpu-dsv41-fans-2026-09-27`](hardware-tests/tower2-four-gpu-dsv41-fans-2026-09-27/) | Four RTX PRO 6000 Blackwell Workstation GPUs at 275 W each; native DSV4.1 Flash with Engram RAM offload on 256 GB DDR5. | Owner-accepted uniform curve used roughly 79–81% sustained fans and peaked at 80–81°C in matched candidate runs. Includes decode/end-to-end evidence, retained failed comparisons, current-source idle recovery and persistent installation. Formal 3% noninferiority was not established; the soak was waived. |
| [`tower2-dual-qwen27-no-gap-2026-07-29`](hardware-tests/tower2-dual-qwen27-no-gap-2026-07-29/) | Adjacent RTX PRO 6000 Blackwell cards with no open-slot gap; dense Qwen3.6-27B AWQ-INT4 on each GPU; 600/400 W, equal 500/500 W, and attempted equal 600/600 W cells. | 500/500 W held 100% utilization with no meaningful throttling. The 600/600 W cell hit the 96°C cutoff after ~5 minutes: GPU1 averaged 589.7 W at 99.4% fan and recorded software plus hardware thermal slowdown. |
| [`tower2-dual-qwen27-600w-2026-07-29`](hardware-tests/tower2-dual-qwen27-600w-2026-07-29/) | Two independent Qwen3.6-27B AWQ-INT4 vLLM engines, one per RTX PRO 6000 Blackwell, held at 600 W and 100% utilization for 30 measured minutes after a 2-minute warmup. | Dual-card worst-case thermal envelope: 599.99 W mean per GPU, 85.1°C/89.0°C mean and 89°C/92°C max, with no thermal slowdown. Also records the host-side limit: CPU Tctl/CCD peaked at 95.6°C/96.6°C. |
| [`vllm-power-sweep-2026-04-29`](hardware-tests/vllm-power-sweep-2026-04-29/) | 7 GPU power caps × 5 min sustained vLLM load × 2 concurrencies (N=1, N=32) × 2 AWQ-INT4 models (Dense Qwen3.6-27B, MoE Coder-Next), 28 cells total, on RTX PRO 6000 Blackwell. | Throughput-vs-power-cap curve, native draw at unbounded cap, and per-cap thermal envelope. Validates the 500 W production cap (within 3.3 % of optimal in every scenario), and shows Coder-Next ≈ 1.8× faster batched / 2.3× faster single-stream than dense 27 B at every cap. The findings doc carries an "Audit notes" section flagging two per-cap "winner" markers that don't survive a re-read of the raw CSVs (a vLLM container warmup transient and a single-window thermal clock dip distort the per-cap winners without changing the plateau-shape headline). |
| [`qwen3.6-q8-fleet-2026-05-17`](hardware-tests/qwen3.6-q8-fleet-2026-05-17/) | Same Qwen3.6 Q8 GGUF model bytes across Blackwell 6000 Tower, DGX Spark, EVO X2 / Strix Halo, and M5 Max MacBook Pro under a pinned llama.cpp SHA, with vLLM appendix rows on Tower2. | Cross-platform single-user prefill/decode/TTFT, backend failure modes, thermal field notes, and cost-throughput caveats for local AI hardware debates. Multi-user serving conclusions are explicitly held. |
| [`best-stack-followup-2026-05-17`](hardware-tests/best-stack-followup-2026-05-17/) | Follow-up bundle: MLX on the M5 Max, and Dream-Server on ROCm 7 on the Strix Halo. | Best-serving-stack notes per platform (MLX beats Metal on M5; ROCm 7 works on Strix; no prefill lift). |
| [`qwen3.5-397b-vs-step3.7-flash-2026-05-29`](hardware-tests/qwen3.5-397b-vs-step3.7-flash-2026-05-29/) | **A 12-family agentic microbench (model behavior), filed here because it needed the dual-Blackwell rig.** 397B-A17B (Q3 GGUF) no-think/think N=10, + Step-3.7-Flash, MiniMax-M2.7, and 27B/Coder-Q4 refs. | Thinking is net-negative (397B 82→72); small-N misreads cells; aggregate ties ~7–8/12 across ~15× scale; MiniMax temp serving-trap. Secondary: dual-GPU power telemetry. See [`MICROBENCH-INDEX.md`](MICROBENCH-INDEX.md). |
| [`local-ai-hardware-valuation-2026-05-17`](hardware-tests/local-ai-hardware-valuation-2026-05-17/) | Derived valuation worksheet built from editable price/spec inputs plus the Qwen3.6 27B Q8 hardware measurements. | Recomputable buyer metrics: `$/usable AI GB`, `$/GB/s`, `$/measured decode tok/s`, `$/measured prefill tok/s`, capacity-bandwidth score, and rough 5-year energy/TCO lines. Use this when market prices change and you want the same mental model to survive the refresh. |
| [`step3.7-flash-nvfp4-dual-blackwell-2026-05-28`](hardware-tests/step3.7-flash-nvfp4-dual-blackwell-2026-05-28/) | Setup/config note: serving `stepfun-ai/Step-3.7-Flash-NVFP4` (201B MoE VLM, day-one) under vLLM on 2× RTX PRO 6000 Blackwell (sm_120, no NVLink), TP=2, native NVFP4 + FP8 KV. | The working launch command and the four non-obvious flags it took to get there, with full diagnostic trail: `--disable-custom-all-reduce` (custom all-reduce deadlocks without P2P/NVLink), `--moe-backend cutlass` (only native-FP4 MoE kernel that supports the model's SWIGLUSTEP activation), no expert-parallel, native max-model-len. No official 2×6000 recipe exists upstream. Companion to the Step-3.7 microbench entry. |
| [`qwen3.6-27b-fp8-microbench-2026-05-31`](hardware-tests/qwen3.6-27b-fp8-microbench-2026-05-31/) | Qwen3.6-27B dense served as FP8 on vLLM (one engine per GPU) on 2× RTX PRO 6000 Blackwell, run through the full MMBT 12-family agentic microbench at N=5 in both `--thinking on` and `--thinking off`. The clean FP8 redo of the 27B run the 397B entry had to exclude as a Q8/FP8 serving failure. | FP8 serving is stable (113/119 cells clean `done_signal`; the 6 errors are model loop-into-context-overflow, not quant instability). **Thinking is net-negative** for 27B here: 35/60 no-think vs 29/60 think — it breaks closed-vocab `p2_triage` (0/5 vs 5/5) and `p3_writing` (1/5 vs 5/5), winning only `p3_business` on length discipline. Hand-grading dimensions not yet filled. |

## At a glance

Two synthesis docs sit between this README and the per-entry detail:

- [`benchmarks/gemma4-31b-q4/GEMMA4_31B_Q4_VERIFIED_RESULTS.md`](benchmarks/gemma4-31b-q4/GEMMA4_31B_Q4_VERIFIED_RESULTS.md) — full Gemma result, native-256K deployment, N=3/N=10 quality, strict artifact audit, and direct Qwen3.6-27B comparison.
- [`benchmarks/deepseek-v4-flash-0731/DEEPSEEK_V4_FLASH_0731_VERIFIED_RESULTS.md`](benchmarks/deepseek-v4-flash-0731/DEEPSEEK_V4_FLASH_0731_VERIFIED_RESULTS.md) — full verified DeepSeek result, including corrected-vs-raw grading, strict artifact audits, production validation, and caveats.
- [`COMPARISON.md`](COMPARISON.md) — **head-to-head decision doc** for the three local model arms (Coder-Next vs 27B-thinking vs 27B-no-think). Organized by task class with cell-level evidence. Read this if your question is "which one should I use?"
- [`SCORECARD.md`](SCORECARD.md) — single-table summary across all entries (spec compliance, factual accuracy, fabricated-claim count, tests run, wall, cost upper bound, failure mode, "when to use which" guide). Read this if your question is "what's the full picture?"

Both link back to the per-entry artifacts they cite.

## Reproducing the runs

The [`tooling/`](tooling/) folder is the reproduction pack — agent harness, sandbox Dockerfile, vLLM launch commands, all 12 microbench task prompts, input starters, ground truth, grader scripts, and batch-runner scripts. With everything there plus a CUDA-capable Linux box and a HuggingFace model, an external reader can rerun any of the local-model entries here.

- **Replaying a published run**: see [`tooling/REPRODUCING.md`](tooling/REPRODUCING.md) — receipt-driven walkthrough.
- **Benchmarking a new local model**: see [`tooling/ADDING-A-MODEL.md`](tooling/ADDING-A-MODEL.md) — end-to-end guide with a four-command friendly path (`smoke_test.sh` → `run_microbench.sh` → `grade_microbench.sh` → `summarize.sh`). Half-day to one-day operator time per new model.

## How To Read A Model Entry

Start with the benchmark folder README, then open the model folder:

1. `benchmarks/<benchmark>/README.md`
2. `benchmarks/<benchmark>/<model>/README.md`
3. The model entry's README for its artifact-specific read order, then the main deliverables such as `report/` / `prs/` or `memo/` / `model/`.

For comparing multiple model entries within a benchmark, look for cross-cutting `findings-*.md` docs at the benchmark folder root (e.g. [`benchmarks/dreamserver-75-pr-audit/findings-2026-04-27-local-models.md`](benchmarks/dreamserver-75-pr-audit/findings-2026-04-27-local-models.md)).

## A note on "Messy"

The "Messy" framing is intentional. Some model entries are clean audits with traceable line-by-line reasoning (`Opus-4.7/` on the 75-PR task). Others are structurally-complete-but-substantively-partial scaffolds with a few hand-written reviews and 70+ template stubs (`Qwen3.6-27B-AWQ/` on the same task). Others are deliberate failure-mode entries with no audit artifacts at all but with documented failure trajectories ([`Qwen3-Coder-Next-AWQ/` on the 75-PR task](benchmarks/dreamserver-75-pr-audit/Qwen3-Coder-Next-AWQ/), [`Qwen3.6-35B-A3B-AWQ/` at N=1](benchmarks/dreamserver-1-pr-audit/Qwen3.6-35B-A3B-AWQ/)).

**Before quoting any number from this repo, read [`KNOWN-LIMITATIONS.md`](KNOWN-LIMITATIONS.md).** It consolidates the caveats that affect what claims this evidence can support — small N, cherry-picked successes, dirty harness git SHAs, hand-graded inputs without a formal rubric, hardware specificity, the gap in cloud-vs-local apples-to-apples grading. Useful evidence; not yet a leaderboard.

This repository is licensed under [MIT](LICENSE). Third-party content (DreamServer code excerpts, SEC filings, cloud-LLM and local-model outputs, Cyankiwi quantizations) retains its original licensing — see [`NOTICE`](NOTICE).

The repo keeps the failures because the *kinds* of failure are themselves the comparison data. A reader picking a model for their own work needs to know that "this model can't complete this task" or "this model produces output shape without substance" — those are real properties of the model, not noise to filter out.

## Current Entries

**gemma4-31b-q4:**
- [Verified campaign entry](benchmarks/gemma4-31b-q4/) — Gemma 4 31B QAT Q4_0 on two independent 500 W RTX PRO 6000 replicas, with native 262,144-token context per slot. Canonical N=10 is 89/120 raw and 99/120 corrected; extended strict result is 0/12. It beats Qwen3.6-27B on directly comparable bounded quality but not on batched serving.
- [Completion audit](benchmarks/gemma4-31b-q4/GEMMA4_31B_Q4_COMPLETION_AUDIT.md) — requirement-to-evidence handoff, including the pending production restore gate.

**deepseek-v4-flash-0731:**
- [Verified campaign entry](benchmarks/deepseek-v4-flash-0731/) — DeepSeek V4 Flash 0731 on 2x RTX PRO 6000 at 500 W/GPU and 1,048,576 context. Canonical corrected result 35/36 (N=3); single-PR 2/3 expected verdicts with all three complete; investment workbooks 0/2 substantively valid; board deck shipped with material visual defects; frozen 75-PR strict result 0/3 (two scaffold-and-stop, one 815,279-token runaway-generation terminal failure).
- [Completion audit](benchmarks/deepseek-v4-flash-0731/DEEPSEEK_V4_FLASH_0731_COMPLETION_AUDIT.md) — requirement-to-evidence handoff and artifact inventory.

**dreamserver-75-pr-audit:**
- [GPT-5.5](benchmarks/dreamserver-75-pr-audit/GPT-5.5/) — cloud, full audit (75 PRs, 34 merge / 40 revise / 1 reject)
- [Claude Opus 4.7 (1M context)](benchmarks/dreamserver-75-pr-audit/Opus-4.7/) — cloud, full audit (51 clean MERGE / 14 categorized HOLDs)
- [Qwen3.6-27B-AWQ](benchmarks/dreamserver-75-pr-audit/Qwen3.6-27B-AWQ/) — local, structurally complete (75/75 verdict files) but only 3 are real reviews; 72 are template stubs. Zero tests run.
- [Qwen3-Coder-Next-AWQ](benchmarks/dreamserver-75-pr-audit/Qwen3-Coder-Next-AWQ/) — local, **no audit deliverable** across 5 attempts. Three distinct degenerate failure modes (loops, cyclic-name slop, stuck-in-research). Folder kept as failure-mode evidence.
- [Cross-cutting findings doc](benchmarks/dreamserver-75-pr-audit/findings-2026-04-27-local-models.md) — comparison writeup of the local-model entries against the cloud entries

**dreamserver-1-pr-audit:**
- [Qwen3-Coder-Next-AWQ](benchmarks/dreamserver-1-pr-audit/Qwen3-Coder-Next-AWQ/) — local, single-PR deliverable, MERGE verdict (correct). **Caveat in README**: this is the cherry-picked correct run of three; other two gave REJECT (wrong, with fabricated technical issues).
- [Qwen3.6-27B-AWQ](benchmarks/dreamserver-1-pr-audit/Qwen3.6-27B-AWQ/) — local, partial deliverable. Best analytical content of any local-model run on this PR. No verdict.md shipped (failure to follow spec); implicit MERGE in `review.md`.
- [Qwen3.6-35B-A3B-AWQ](benchmarks/dreamserver-1-pr-audit/Qwen3.6-35B-A3B-AWQ/) — local, **floor failure**. Zero artifacts produced; model investigated for 28 iters then stopped without writing.

**wallstreet-intern-test:**
- [GPT-5.5](benchmarks/wallstreet-intern-test/GPT-5.5/) — cloud, full memo repo + the follow-on board-of-advisors presentation in `board-of-advisors-presentation/`
- [Claude Opus 4.7 (1M context)](benchmarks/wallstreet-intern-test/Opus-4.7/) — cloud, full memo repo
- [Qwen3.6-27B-AWQ](benchmarks/wallstreet-intern-test/Qwen3.6-27B-AWQ/) — local, GitLab Inc. (`GTLB`) BUY recommendation. 1 of 3 attempts shipped (other 2: parser fault, 1-hour single-call timeout). 17 KB three-statement model, full audit trail.
- [Qwen3-Coder-Next-AWQ](benchmarks/wallstreet-intern-test/Qwen3-Coder-Next-AWQ/) — local, DocuSign (`DOCU`) BUY recommendation. 1 of 3 attempts shipped (other 2: scaffold-and-stop). 10.6 KB three-statement model. **Verdict-reliability caveat in entry README** — single-shot Coder-Next output can be confidently wrong with fabricated evidence (see PR-audit benchmark for documented examples).
- [Qwen3.6-35B-A3B-AWQ](benchmarks/wallstreet-intern-test/Qwen3.6-35B-A3B-AWQ/) — local, **no usable deliverable**. 0 of 3 attempts shipped. Folder kept as failure-mode evidence consistent with the model's PR-audit floor failure.

**microbench-2026-04-28:**
- [`adversarial-hallucination/`](benchmarks/microbench-2026-04-28/adversarial-hallucination/) — agent must distinguish 6 real bugs from 9 confident-but-wrong fabrications. Sharpest local-model superiority signal in the entire repo: 27B 3/3 PASS, Coder-Next 1/3 PASS with 2 confirmed-fabrications-as-real on the shipping run.
- [`market-research/`](benchmarks/microbench-2026-04-28/market-research/) — 5-product enterprise password manager comparison + pricing math + cited sources. Inversion of the prior "both fail at internet research" expectation: 27B 3/3 STRUCTURAL_PASS (12-18 cites to 29-33 distinct URLs), Coder-Next 0/3 STRUCTURAL_FAIL.
- [`doc-synthesis/`](benchmarks/microbench-2026-04-28/doc-synthesis/) — 1-page executive brief from 5 source documents, 700-word limit. Documents a 27B failure mode: 8/8 facts captured every run, but model can't trim to length (765-775 words across N=3, two runs entered identical-call-loops on `brief.md`).
- [`findings.md`](benchmarks/microbench-2026-04-28/findings.md) — cross-cutting writeup spanning all 12 task families (3 published full + 9 summarized).

**microbench-phase-b-2026-05-02:**
- [Qwen3-Coder-Next-AWQ](benchmarks/microbench-phase-b-2026-05-02/) — N=10 expansion across 4 differential cells. Headline: 0/10 STRUCTURAL_FAIL on `p3_market` (Wilson 95% [0%, 27.8%]) confirmed reproducible.
- [Qwen3.6-27B-AWQ (thinking)](benchmarks/microbench-phase-b-2026-05-02/) — N=10 expansion. Word-trim loop on `p3_doc` bounded as a stable ~40% failure shape (4/10 wall_killed).
- **[Qwen3.6-27B-AWQ (no-think)](benchmarks/microbench-phase-b-2026-05-02/) — new third arm**, full 12-family grid × N=10. 95.8% ship rate (Wilson 95% [90.5%, 98.2%]) — most reliable shipper of the three. Halves the `p3_doc` word-trim loop rate (4/10 → 2/10).
- [`findings.md`](benchmarks/microbench-phase-b-2026-05-02/findings.md) — full per-cell breakdown with Wilson CIs, three identical-call-loop subclasses, cost-per-shipped-run analysis, "when to use which" updates.
- [`findings-pairwise-quality-three-model.md`](benchmarks/microbench-phase-b-2026-05-02/findings-pairwise-quality-three-model.md) — hand-graded deliverable quality study; 27B-thinking and 27B-no-think substantively equivalent on shipped output.
