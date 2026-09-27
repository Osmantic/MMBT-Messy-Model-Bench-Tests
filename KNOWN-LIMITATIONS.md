# Known limitations

This is a working benchmark corpus, not a leaderboard. The data is real and the methodology is documented, but several caveats affect how strong any claim from this repository can be. They're spread across many entry READMEs and findings docs; this file consolidates them for a reader who wants to assess what the evidence here can and cannot support.

If you're considering quoting a number from this repo or building a deployment decision on it, **read this file first.**

## Reproducibility caveats

### Legacy receipts have `git_dirty: true`; the DeepSeek campaign does not

The heading in older revisions applied to the original entries. The DeepSeek
V4 Flash campaign implements the process fix: run identity is captured before
launch, incomplete attempts are isolated, and canonical and extended runs use
committed harness states. This improves the new entry's reproducibility but
does not remove the caveat from older receipts.

Every earlier `receipt.json` in this repo records `harness.git_dirty: true`, meaning the source bench repo had uncommitted changes when the run executed. The harness was being iterated on during the experiment (we made several substantive changes mid-batch — see `tooling/HARNESS-CHANGELOG.md`), and the runs that produced those entries happened against working trees, not clean tagged states. The harness git SHA in each legacy receipt is therefore a near-but-not-exact reference; replays from those SHAs may differ slightly from the published runs.

Future canonical runs intended for publication should be made from clean trees. The DeepSeek campaign implements that process fix; it does not retroactively change the legacy entries.

### Cherry-picked successful runs are published

The DeepSeek entry is deliberately different: all three canonical replicates
and all three valid 75-PR outcomes are included in its aggregates. Two earlier
75-PR attempts are preserved but excluded because they hit an artificial 180K
response ceiling while safe served context remained. The exclusion policy and
replacement manifest are published; the successful-looking run is not
cherry-picked.

The local-model entries that have a deliverable are the *single best of multiple attempts*. The Coder-Next single-PR audit, for example, is `n1_coder_v2` — the one of three runs that produced a correct verdict; the other two (`v1` and `v3`) gave wrong verdicts with fabricated supporting evidence. Each entry's README documents its variance honestly and quotes the per-run shipped-rate fraction. But: a reader comparing entries cell-by-cell sees the best of N, not the expected outcome.

For some entries (`benchmarks/dreamserver-75-pr-audit/Qwen3-Coder-Next-AWQ/`, `benchmarks/wallstreet-intern-test/Qwen3.6-35B-A3B-AWQ/`) we publish failure-mode-only entries with no deliverable. Those are honest about the lack of a single representative run. But for the entries with deliverables, **don't quote a verdict or recommendation as "what the model says" without first checking the entry's variance section**.

### Microbench-2026-04-28: only 3 of 12 task families are published as full entries

The microbench has 12 task families × 2 models × N=3 = ~80 runs. Publishing every run as a full per-model folder would create 60+ tiny entries. Three task families (`adversarial-hallucination/`, `market-research/`, `doc-synthesis/`) are published as full per-model entries because they carry the highest-signal results. The other nine (Phase 1 coding × 3, Phase 2 extraction/CI/triage, Phase 3 business-memo/writing/PM) are published as **lean entries** (per-model README + cost.json + grade.json + label.json + summary.json + receipt.json — no transcripts or deliverables to keep repo size manageable).

This means: for the 9 lean entries, you can read the per-model verdict, cost, and label, but you can't drill into the specific transcript or deliverable artifact from MMBT alone. **However, the task prompts, input starters, ground truth, and grader scripts for all 12 task families are now shipped in `tooling/`** — so a reader with the right hardware can rerun any of these task families and produce their own transcripts + deliverables. See `tooling/REPRODUCING.md` § "Reproducing the microbench".

### Microbench: two manually-advanced 27B runs in `doc-synthesis`

`p3_doc_27b_v2` and `p3_doc_27b_v3` were manually SIGTERM'd mid-run after entering identical-call-loops on `brief.md` (writing the same content for 50-130+ iters). The stuck-detector at `--stuck-threshold 500` would have eventually fired but several hours later. The runs' summary.json files explicitly mark `finish_reason: wall_killed_identical_call_loop`. The behavior is documented as a 27B failure shape on this task, not a transient bug. But: a strict reading might note that the 0/3 PASS rate on doc-synthesis includes 2 manually-advanced runs, not 3 stuck-detector-fired runs. The diagnostic interpretation (model can't trim to word limit) is supported by all 3 runs producing identical-content writes around the same word count (765/775/768).

### Failed-run artifacts not currently included for most entries

The DeepSeek publication keeps compact per-suite audits, run classifications,
hashes, and reproduction tooling in git. Its full workspace archives and long
transcripts remain external because the terminal-run archive alone is 137 MB.
This follows `REPO-SPACE.md`: conclusions are hash-auditable from the repository,
while byte-for-byte replay of every model turn requires the external archives.

Source bench repo has full receipts + transcripts + workspaces for every attempted run (success and failure). MMBT publishes receipts + transcripts only for the single representative run per entry. The 5 failed runs across the local models (`27b_invest_memo_v3`, `27b_invest_memo_v4`, `coder_invest_memo_v6`, `coder_invest_memo_v7`, `n1_coder_v1`, `n1_coder_v3`, all three 27B PR-audit canonicals' "secondary" runs, and the 35B-A3B failure runs) have receipts and transcripts in the private bench repo but not here. A more rigorous audit of variance would need those.

### The Qwen3.6-vs-3.8 numbers come from a frozen extract, not a live re-scan

Every headline figure in this entry is computed from a single frozen extract of the run corpus — `mmbt-frozen-dataset-v2.csv` (freeze #2), 802 cells, frozen `2026-08-16T14:23:09Z` — and **not** from a live re-scan of the five run checkouts. That is deliberate. The corpus was still accumulating cells while the freeze-1 analysis was underway, and live re-scans moved headline percentages by 4-9 points between passes purely because more cells had landed. Freeze #2 ends that: every campaign process is stopped, in-flight cells are quarantined out of the extract, and the on-disk verdict now agrees with the frozen verdict for all 733 graded rows (the overlay manifest's `post_freeze_divergence` ledger is empty).

Two consequences a replicator should plan for. First, the frozen extract is the citable object: model and sampler identity in it were read from each cell's `receipt.json`, never inferred from directory names, and re-deriving identity from names will not reproduce the arm assignments. Second, the freeze boundary still hides real objects: quarantined in-flight cells are not rows in the extract at all — the clearest instance is `p3_doc_qwen38q8-nothink-matched_v2`, a Q8_0 run quarantined mid-flight in a rewrite loop (139 iterations rewriting `brief.md`, context grown to ~228k tokens), which this entry cites only as unscored qualitative evidence and excludes from every rate. A reader who finds such directories on disk has found something real that the extract deliberately does not count. (The freeze-1 version of this entry disclosed 7 unreconciled Q8_0 grades; freeze #2 admits them — the Q8_0 arm now carries 8 graded cells — so that particular discrepancy no longer exists.)

### Replicate depth is unbalanced across the compared arms

The arms are not equal-sized, and the imbalance runs the same direction as the headline. Per family, Qwen3.6 no-think at `T0.3/p0.8/pp0` carries 9-19 replicates, Qwen3.8 at the same sampler 7-13; in think mode at that sampler Qwen3.6 carries 9 per family against Qwen3.8's 4-6. At the vendor points the gap is smaller but present (10 per family for 3.6, 8 for 3.8). Aggregate arm sizes are 121 vs 95 (no-think matched), 120 vs 96 (no-think vendor), 108 vs 51 and 120 vs 72 (think).

This means pooled percentages weight the two models' family mixes differently, and a family where one model happens to have twice the replicates pulls the pooled number toward that family's behavior. Per-family rates with their own denominators are printed in `benchmarks/qwen36-vs-qwen38-27b-2026-08/findings.md` for exactly this reason. **Do not compute a pooled model-level rate from this data without checking whether the family weighting is doing the work.** Confidence intervals are correspondingly wide: several per-family cells rest on 4-6 runs.

### Replicates share a seed and are not fully independent draws

Every one of the 802 cells ran at `seed=42`. Sampling temperature breaks strict determinism, so replicates do differ — of the duplicate-length sibling pairs we checked, **none** had byte-identical transcripts (8 of 8 sets checked, all distinct SHA-256). But the replicates are visibly correlated rather than independent. Within same-arm same-family replicate sets, the share of cells landing on an exactly identical total completion-token count as a sibling is 5.4% (17/316) at `T0.3/p0.8/pp0`, 3.6% (10/276) at `T1/p0.95/pp0`, and 0% (0/76) at `T0.7/p0.8/pp1.5`, the one sampler carrying a presence penalty. Concrete example: five `p2_extract` replicates in one Qwen3.6 arm all finished at exactly 1,515 completion tokens.

The honest reading is narrower than "the runs are near-deterministic": they are not, and the transcripts prove it. The reading that survives is that **effective n is somewhat below nominal n at the low-temperature samplers**, that the correlation is not uniform across samplers, and that this entry does not quantify how much statistical power is lost. Varying the seed across replicates is the obvious fix and was not done here.

## Methodology caveats

### No formal scoring rubric

Verdicts are graded right/wrong by hand against the actual diff and a known-correct reference review. This works at small N with a single PR; it does not scale. Any larger comparison should establish a per-claim rubric (verdict matches ground truth: y/n; line citations valid: y/n; fabricated evidence count) and apply it consistently. The forthcoming `SCORECARD.md` synthesizes existing evidence into a normalized table but uses hand-graded inputs, not a formal rubric.

### Microbench Phase 3 hand-grading is *claude-grading-claude*

The 30 hand-graded subjective dimensions on the microbench Phase 3 entries (prose quality, stance clarity, source skepticism, balanced tone, audience tone fit, faithfulness, fabrication count, citation validity) were graded by Claude Opus 4.7, not by the human maintainer. The grader is a different model from the grade-ees (Qwen3.6-27B-AWQ, Qwen3-Coder-Next-AWQ), and the grader's outputs went into `hand_rating_placeholders` with explicit `_GRADER_: claude-opus-4.7-1m-context` provenance fields — but the meta-issue stands: a model graded other models' outputs, and the grader's biases are not separately characterized. For research-grade claims about prose quality differences between models, a human grading pass would be needed.

The citation-validity sample on the 27B market-research entry (18 of 33 URLs, measured 75% valid) was done with WebFetch + content-comparison, which is a more grounded methodology than aesthetic judgment. The remaining hand-graded dimensions are prose-aesthetic and meta-issue-affected.

### Small N (typically N=3 per model × task)

DeepSeek's corrected 35/36 result is also N=3 per family. Qwen3.5-397B has N=10,
and its `p3_market` majority interpretation changed between N=3 and N=10. Treat
DeepSeek as the highest observed corrected local result, not a settled population
rate; an N=10 expansion is the direct follow-up.

3 runs per cell is enough to see that variance exists; not enough to bound it. Confidence intervals on a 1/3 success rate are wide ([1%, 71%] at 95%). Aggregate claims like "Coder-Next is wrong 67% of the time at N=1" are best read as "in the runs we ran, it was wrong 2/3 of the time." Generalization needs more data.

### Approximate determinism only

vLLM's bf16 paths aren't bitwise-deterministic, so `temperature=0.0 + seed=42` doesn't produce identical runs. Most runs in this repo use `temperature=0.3` deliberately, to break deterministic loop traps surfaced during the smokes. That makes per-run variance an inherent property of the data, not a bug — but it also means rerunning the same prompt with the same flags will produce a different output, and comparing single runs cell-by-cell is misleading.

### Live data drift

The DeepSeek 75-PR campaign discovered that the live backlog had grown to 272
PRs. Its scored replacements therefore use a frozen source-only fixture with
the same 75 PR numbers as the historical Qwen, GPT-5.5, and Opus artifacts,
pinned to baseline `d5154c3`. The first live-272 attempt is retained as
infrastructure-invalid. This restores set comparability, but comments and other
network-fetched context can still drift.

### DeepSeek V4 Flash 0731 is not a uniform leaderboard arm

DeepSeek runs at its published agentic sampling point (`temperature=1.0`,
`top_p=0.95`) with a 1,048,576-token served context. Earlier local arms commonly
used temperature 0.3 and 131K or 262K context. Its raw canonical score is 23/36;
the corrected score is 35/36 after reproducible cache-file false negatives,
host-runtime grader crashes, and contradictory writing rules were repaired
against unchanged archives. Original grades remain published.

The Qwen3.5-397B writing overlay applies equivalent non-destructive writing
corrections and moves no-think from 82/120 to 92/120, but Step, MiniMax, 27B,
and Coder-Next have not all been uniformly regraded with every new repair.
Therefore the corrected DeepSeek result is directional evidence of a strong
local lead, not a statistically or methodologically uniform global rank.

Artifact quality varies sharply by modality. DeepSeek completed all three
single-PR repositories, yet both audited investment workbooks contained zero
formulas and failed substantive finance review, and the valid board deck had
material visual defects. The full-context 75-PR result is 0/3 strict. Do not
generalize 35/36 bounded-task performance to finance, visual QA, or unattended
marathon reliability.

Tasks that reference real public state (DreamServer PRs, SEC filings, market prices) will see that state drift over time. The DreamServer PR audit task pins to a specific baseline commit (`d5154c37...`) but PR comments accumulate, contributors close PRs, the issue tracker moves. The wallstreet task has no such anchor — the company-pick is the agent's decision and the analyzed material may have been updated since extraction. Take time-of-run into account when comparing across replicates.

### No thinking-mode arm exists at Qwen3.8's own vendor sampler

This is the largest hole in the comparison and it cannot be patched by re-analysis. Qwen3.8's vendor sampling point is `T0.7/p0.8/pp1.5`; the corpus contains **zero** Qwen3.8 think cells there. Its think arms exist only at `T0.3/p0.8/pp0` (51 cells) and `T1/p0.95/pp0` (72 cells), and `T1/p0.95/pp0` is *Qwen3.6's* vendor point. So the only sampler at which both models have think cells is one model's home turf, and no run in this repository shows Qwen3.8 thinking at the settings its own model card recommends.

Any cross-model thinking comparison drawn from this entry is therefore both-models-at-3.6's-settings, and this repo declines to label it otherwise. The gap compounds with a second asymmetry: every Qwen3.8 think cell carries a `reasoning_effort` value, so those arms are mixtures of `low`/`medium`/`xhigh` (14/24/13 at the matched sampler, 12/12/48 at `T1`), while Qwen3.6's shipped chat template contains no `reasoning_effort` variable at all and its think arm is a single configuration. **A mixture compared against a point is not a like-for-like comparison**, whatever the sampler. Running Qwen3.8 think at `T0.7/p0.8/pp1.5` at a fixed effort level is the single highest-value follow-up to this entry.

### No phase-3 grader checks fabrication, factual accuracy, or quality — and the hand-rating slots are empty

Every phase-3 grader in `tooling/graders/` is a keyword-recall and word-count instrument. `phase3_project_mgmt_grade.py` asks whether literal strings appear; `phase3_doc_synthesis_grade.py` and `phase3_business_memo_grade.py` count matched fact keywords against a threshold and check a word ceiling; `phase3_writing_editing_grade.py` checks must-include and must-not-include strings plus a per-audience ceiling; `phase3_market_research_grade.py` emits `STRUCTURAL_PASS`/`STRUCTURAL_FAIL` on counts of products named and URLs cited. **None of them reads the deliverable for whether it is true.** A confidently fabricated status report that uses the right vocabulary and lands under 700 words passes every automated gate in this entry.

The graders were designed knowing this — they carry `hand_rating_placeholders` blocks for exactly the dimensions the automation cannot reach (fabrication count, faithfulness, citation validity, stance and structure quality). Those blocks are empty corpus-wide. Of the 733 `grade.json` files read (one per frozen graded cell), 441 have no placeholder block at all (the phase-1 and phase-2 graders), 292 carry one, and **every numeric or free-text rating field in all 292 is null**. The only non-null entries anywhere are 46 `p3_market` cells carrying a boilerplate `_HAND_VERIFICATION_REQUIRED_` note that says the structural pass is necessary but not sufficient — a marker that the work is outstanding, not a rating.

So: read every phase-3 result in this entry as *"produced an artifact with the expected shape and vocabulary."* It is not a quality score, and the corrected pass rates published here inherit that limit in full. The 39 `p3_market` `STRUCTURAL_PASS` verdicts in particular assert structure only and prove no citation.

### `p3_market` is a live-internet task and its results are not replayable

The `p3_market` family sends the agent to the live public web. Its inputs are whatever the internet returned at run time, so unlike the other eleven families it has no fixed fixture and no possibility of a byte-identical replay. Cells run on different days saw different pages; cells run against sources that have since changed cannot be re-graded against what the model actually read.

It is also the family most distorted by the run-length pathologies described in this entry — of its 64 cells, 18 are loop-labelled and only 46 are graded, the worst delivery of any family — which means its aggregate is computed on a smaller and differently-selected subset than its neighbors. Treat `p3_market` as a qualitative probe. **Do not include it in cross-model aggregates without saying so**, and do not read a difference in its pass counts as a difference in market-research ability.

## Hardware and platform caveats

### Single-workstation hardware specificity

All published runs were on a workstation with 2× RTX PRO 6000 Blackwell (96 GB each, 600 W each at full uncapped operation), TR PRO 7965WX, 252 GB RAM. Smaller GPUs work but the published flags assume this configuration. Specifically: `--max-model-len 262144` and `--gpu-memory-utilization 0.92` will OOM on consumer 24-48 GB GPUs. `tooling/REPRODUCING.md` notes this; the cost.json files do not normalize for it.

Cost numbers in `cost.json` are upper-bound estimates (assume the GPU drew at its `power.limit` for the entire wall — real draw is lower). On different hardware, the same workload would have different absolute cost numbers; comparing cost.json across hardware setups requires renormalization.

### Quantization specificity

The local-model entries used 4-bit AWQ quantizations from the cyankiwi HuggingFace organization. Different quants of the same base model (FP8, BF16, different AWQ tools) will behave differently. The entries pin specific HuggingFace model paths in `launch-commands.md`; respect those when comparing.

#### Cyankiwi 4-bit AWQ field reports

As of 2026-05, multiple practitioners (in independent forum / community discussions) have reported that the Cyankiwi 4-bit AWQ quants of Qwen3.6-27B and Qwen3-Coder-Next underperform the official Qwen FP8 quants and Unsloth UD4 GGUFs of the same base models in their workflows. The reports describe degraded output coherence and increased loop pathologies on certain task shapes.

This benchmark uses Cyankiwi 4-bit AWQ throughout for three reasons:
1. Reproducible community release with stable HuggingFace paths
2. Fits the available VRAM-throughput envelope on Tower2 with room for `--max-model-len 262144` and large concurrency batches in the hardware-tests sweep
3. Consistent across all three model arms (apples-to-apples within the quant)

What this means for the data here:
- **Within-quant comparisons (Coder-Next vs 27B at the same Cyankiwi 4-bit AWQ) remain informative.** Differential behaviors — Coder-Next's `p3_market` 0/10 collapse, 27B's word-trim loop, the `--no-think` ship-rate jump — are model-mechanism findings that are unlikely to disappear at higher precision.
- **Absolute model capability at higher precisions (FP8 / Unsloth UD4 / BF16) is not characterized.** Headline numbers like "27B-no-think 95.8% ship rate" are quant-specific.
- **The ranking of cells where models tie at this quant could shift at FP8.** The both-ship cells (p2_ci, p2_extract, p2_triage) are the most likely to be sensitive.

The FP8 re-run of the same 12-cell grid is the highest-priority follow-up — see [`ROADMAP.md`](ROADMAP.md). Contributors with FP8-capable hardware are welcome to PR results via the [`tooling/ADDING-A-MODEL.md`](tooling/ADDING-A-MODEL.md) flow (which now explicitly covers the "same model, different quant" contribution path).

### Quantization specificity — the Qwen3.6-vs-3.8 comparison does not settle the quant question

The head-to-head runs entirely on Unsloth UD-Q4_K_XL GGUFs for both models. The one quantization control in the corpus is a 19-cell Qwen3.8 Q8_0 arm at the matched sampler (2 replicates on the 7 phase-1/phase-2 families, 1 on the 5 phase-3 families), and at freeze #2 it establishes one thing at provisional-rate strength: the identical-call-loop failure shape occurs at Q8_0 at a real, non-negligible rate — 6 of 19 cells trip `looped_freq30` (31.6%, Wilson 95% CI [15.4%, 54.0%], excluding zero), with maximum identical-call runs of 110, 109, 81, 80 and 71. Against 3.8 at UD-Q4_K_XL, same sampler, same 12 families, the loop rate is statistically indistinguishable (29/95, 30.5%, vs 6/19; Fisher p = 1.0). **The loop is not an artifact of UD-Q4_K_XL alone.** A quarantined in-flight Q8_0 cell (`p3_doc_qwen38q8-nothink-matched_v2`, 139 iterations rewriting `brief.md`, ~228k context) additionally shows a rewrite-loop subclass at Q8_0 — unscored qualitative evidence only, excluded from every rate.

What the control cannot do is still more important than what it can. The graded subset is 8 of 19 cells (5 PASS, 3 FAIL; 62.5%, Wilson [30.6%, 86.3%]) — published as provisional data, and far too thin for any quality verdict: the vs-Q4 graded-only contrast (78.5% vs 62.5%, Fisher p = 0.38) fails this PR's own power screen. And there is **no matched Qwen3.6 Q8_0 arm at all**, so this is not a quant A/B: it can neither attribute the Qwen3.8 delivery regression to quantization nor rule quantization out. Whether Qwen3.8's no-think delivery gap narrows, holds, or disappears at Q8_0, FP8, or BF16 is open, and a Q8_0 arm at N>=5 per family for *both* models — graded — is the experiment that would close it.

### Cloud-LLM hardware is different

Cloud entries (`Opus-4.7/`, `GPT-5.5/`) ran on the providers' inference infrastructure, not Tower2. Cross-comparison should account for that — "the cloud LLM is better" partly reflects "different hardware + different quantization-strategy + different inference engine," not just model differences.

## Security caveats — for replicators only

The harness exposes flags that give the model-controlled sandbox elevated access to the host. This is documented in `tooling/HARNESS-CHANGELOG.md` and per-flag in `harness.py --help`, but worth restating prominently:

- **`--docker-socket`**: bind-mounts `/var/run/docker.sock`. The sandbox can spawn sibling containers, kill containers, pull images. **Effectively root-equivalent on the host docker daemon.** Used during the PR-audit experiments so the agent could run `docker run ubuntu:22.04` for installer testing. **Do not enable this on a host you don't fully control.**
- **`--gh-token`**: passes a GitHub PAT into the sandbox via env var. The model can use it. If the token has write scopes, the model can in principle push commits, comment on issues, close PRs. We mitigated by either passing a read-only token or no token at all (the DreamServer repo is public, so unauth `git fetch` works for the PR-audit task) — but if you replicate, **mint a fine-scoped read-only token, and treat any token you pass as compromised after the run.**
- **`--gpus all`**: the sandbox shares GPU access with the host. The agent can run CUDA workloads, fingerprint hardware, exfiltrate via timing, etc. Not a privilege escalation per se, but worth knowing.

These flags exist because the benchmark tasks needed them. They are not appropriate for adversarial-input evaluations or for any setup where the model is untrusted.

## Comparison-to-cloud caveats

The cloud entries in this repo were not graded with the same scoring methodology as the local entries, because the local entries' grading was hand-done against ground truth on PR #1057 and the cloud entries' verdicts on the same PR aren't graded at the per-claim level here (Opus-4.7's broader audit covers PR #1057 in passing; GPT-5.5's similarly). So while both classes are present in this repo, **a direct head-to-head with consistent grading isn't currently published.**

That's the gap a future `RUBRIC.md` + per-entry `grade.json` would close. As of this writing, the cloud-vs-local comparison should be read at the *categorical* level ("cloud entries shipped complete deliverables; most local entries shipped failure modes") not at the per-claim accuracy level.

### `microbench-2026-04-28` is local-models-only

The microbench has no cloud-LLM entries at all. The 12 task families were run only on Qwen3.6-27B-AWQ and Qwen3-Coder-Next-AWQ. Headline reads from the microbench (e.g. "27B drives internet-research workflows that Coder-Next doesn't") apply *between local models*, not vs cloud. Cloud LLMs would almost certainly do as well or better on these tasks; the gap-vs-cloud is undocumented.

A future microbench expansion that runs Opus-4.7 / GPT-5.5 on the same task starters (using the same harness via API instead of vLLM) would close this. Until then: the microbench tells you which *local* model to use, not whether a local model is the right fit at all.

## What this repo can and can't support

**Can support**:
- "Here's what agentic 30B-class quantized local-model failures look like in detail."
- "Here are receipts + transcripts + cost numbers for replicating a specific run."
- "Here's a documented vocabulary for agentic failure modes" (`tooling/FAILURE-TAXONOMY.md`).
- "Here's evidence that the same model can ship structurally complete output and confidently wrong content in the same task."
- "Here's the harness that produced these runs, with its iterative-fix history."

**Can't support yet** (until rubric + larger N + cloud-rubric pass land):
- "This model is reliably better than that one for everyday work."
- "This model has X% factual accuracy."
- "Cost of operation is exactly $Y per task at production scale."
- "Cloud is N× better than local on this benchmark."

When in doubt: cite the specific run name and its receipt, not the model name in general.
