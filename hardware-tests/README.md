# Hardware Tests

Start here if your question is about machines rather than model behavior. This
tree answers hardware questions: throughput, power, thermals, backend maturity,
and buyer-value ratios. It is separate from the agent-task benchmark tree.

## Coverage Matrix

The cross-platform fleet study is not just a 27B dense run. It covers both a
dense model and a MoE model across the fleet, with one explicit Blackwell
engine/quant exception for the MoE row.

| Host | Dense 27B Q8 | MoE 35B-A3B | Backend status | Use for |
|---|---|---|---|---|
| Blackwell 6000 Tower | llama.cpp CUDA, canonical | native llama.cpp Q8 retracted; vLLM FP8 defended row | CUDA Q8 MoE hits SOFT_MAX on sm_120; vLLM works | discrete-GPU speed, long-context engine sensitivity |
| M5 Max MacBook Pro | llama.cpp Metal, canonical | llama.cpp Metal, canonical | clean Metal path | unified-memory Mac appliance behavior |
| DGX Spark | llama.cpp CUDA aarch64, canonical | llama.cpp CUDA aarch64, canonical | clean CUDA aarch64 path | NVIDIA unified-memory desktop behavior |
| EVO X2 / Strix Halo | llama.cpp Vulkan, canonical partial | llama.cpp Vulkan, canonical partial | Vulkan works; ROCm retry still pending | AMD APU / small-chassis behavior |

Canonical rows live in
[`qwen3.6-q8-fleet-2026-05-17/aggregate/canonical-headline.csv`](qwen3.6-q8-fleet-2026-05-17/aggregate/canonical-headline.csv).
Appendix and engine-comparison rows live in
[`qwen3.6-q8-fleet-2026-05-17/aggregate/appendix-headline.csv`](qwen3.6-q8-fleet-2026-05-17/aggregate/appendix-headline.csv).
Do not mix those two tables in a cross-host ranking.

## What Each Bundle Answers

| Bundle | Primary question | Main caution |
|---|---|---|
| [`tower2-four-gpu-dsv41-fans-2026-09-27`](tower2-four-gpu-dsv41-fans-2026-09-27/) | How can four 275 W RTX PRO 6000 cards share one quiet fan curve while running native DSV4.1 with RAM offload? | Practical profile accepted and persistent installation verified; formal 3% performance noninferiority was not established, final hot/host-reboot proofs were omitted, and the owner waived the soak. |
| [`tower2-dual-qwen27-no-gap-2026-07-29`](tower2-dual-qwen27-no-gap-2026-07-29/) | Can adjacent RTX PRO 6000 Blackwell cards sustain dense dual-GPU inference with no open-slot gap, and how does the thermal cost divide between temperature and fan duty? | 600/400 W is stable; 500/500 W shows no meaningful throttling; 600/600 W reaches the 96°C cutoff and confirmed GPU1 thermal slowdown after ~5 minutes. |
| [`tower2-dual-qwen27-600w-2026-07-29`](tower2-dual-qwen27-600w-2026-07-29/) | Can both RTX PRO 6000 Blackwell GPUs sustain dense Qwen3.6-27B inference at 600 W each for 30 minutes, and where do temperatures, clocks, and fans settle? | One Tower2 run with independent AWQ-INT4 vLLM engines; host CPU/CCD temperatures, not GPU throttling, were the limiting thermal observation. |
| [`qwen3.6-q8-fleet-2026-05-17`](qwen3.6-q8-fleet-2026-05-17/) | How do four local-AI hardware classes handle the same dense and MoE Qwen3.6 workloads? | Multi-user serving is held; Tower2 MoE uses a defended vLLM FP8 exception because native llama.cpp Q8 crashes. |
| [`best-stack-followup-2026-05-17`](best-stack-followup-2026-05-17/) | What's the best serving stack per platform (MLX vs Metal on M5; ROCm 7 on Strix Halo)? | Platform-specific; MLX beats Metal on M5, ROCm 7 works on Strix, no prefill lift. |
| [`qwen3.5-397b-vs-step3.7-flash-2026-05-29`](qwen3.5-397b-vs-step3.7-flash-2026-05-29/) | **(Model-behavior microbench, filed here for the rig.)** Does thinking help; do results tie across scale; 397B / Step-3.7 / MiniMax / 27B-Q4 refs. | Thinking net-negative across ~15× scale; small-N misreads cells; MiniMax temp serving-trap. A 12-family agentic microbench — see [`../MICROBENCH-INDEX.md`](../MICROBENCH-INDEX.md). Secondary: dual-GPU power. |
| [`local-ai-hardware-valuation-2026-05-17`](local-ai-hardware-valuation-2026-05-17/) | What are buyers paying per usable memory GB, bandwidth, and measured 27B Q8 tok/s? | Prices and wall-power assumptions are time-bound inputs. |
| [`vllm-power-sweep-2026-04-29`](vllm-power-sweep-2026-04-29/) | Where is the RTX PRO 6000 Blackwell LLM-serving power-cap plateau? | Tower2-only, vLLM-only, AWQ-INT4 models. |
| [`ltx23-power-sweep-2026-05-05`](ltx23-power-sweep-2026-05-05/) | Does the same GPU power-cap curve apply to diffusion/video generation? | Workload-specific to the LTX-2.3 workflow tested. |
| [`cpu-fullpower-2026-05-05`](cpu-fullpower-2026-05-05/) | Can the Tower2 Threadripper PRO CPU sustain rated 350 W on its cooling stack? | One rig, one cooling design, CPU-side validation only. |
| [`step3.7-flash-nvfp4-dual-blackwell-2026-05-28`](step3.7-flash-nvfp4-dual-blackwell-2026-05-28/) | How do you serve Step-3.7-Flash NVFP4 with native FP4 on 2× RTX PRO 6000 Blackwell (no NVLink), and what tok/s does it give? | Single rig, vLLM dev image (not a tagged release), single run per throughput cell. |
| [`qwen3.6-27b-fp8-microbench-2026-05-31`](qwen3.6-27b-fp8-microbench-2026-05-31/) | Is FP8 a stable serving path for Qwen3.6-27B where Q8 failed, and does thinking help on the agentic microbench? | Single rig, vLLM FP8, N=5; thinking is net-negative (35/60 no-think vs 29/60 think); hand-grading dimensions not yet filled. |

## What The Cross-Platform Study Can Settle

- Single-user prefill, decode, and TTFT for the tested dense and MoE model
  rows.
- Backend maturity and failure modes under the tested source SHA.
- Chassis and thermal behavior under sustained local-inference operation.
- Narrow buyer-value statements tied to the measured rows and dated prices.

## What It Does Not Settle Yet

- Best hardware for every quantization, model size, or engine.
- Best multi-user serving hardware under proper batching engines.
- Task quality of Q8 outputs.
- Cross-day variance or unit-to-unit variance.
- Total cost of ownership without plug-metered wall power on every host.

For the active gap list, read [`../NOT-HERE-YET.md`](../NOT-HERE-YET.md).

## Storage Posture

The hardware-test tree is the current repo-size hotspot because it preserves
raw sampler CSVs, JSONL inference traces, and audit bundles. That is useful for
trust, but it should stay intentional. See [`../REPO-SPACE.md`](../REPO-SPACE.md)
for the measured size breakdown and the recommended path for compressing or
externalizing future raw artifacts.
