#!/usr/bin/env bash
# Run the full microbench (12 task families × N=3 = 36 runs) against one model.
#
# Usage: bash tooling/scripts/run_microbench.sh <served-model-name> <port> <model-label> [<n>] [<reasoning-effort>]
#
# Args:
#   served-model-name: must match what your vLLM endpoint exposes via /v1/models
#   port: vLLM endpoint port
#   model-label: short tag used in run names (e.g. "qwen2.5-72b" → run names like
#                p2_extract_qwen2.5-72b_v1). Avoid spaces and slashes.
#   n: number of runs per cell (default 3). 1 for quick sweep, 3 for canonical.
#   reasoning-effort: optional low|medium|high|xhigh for models with reasoning levels
#                (e.g. Step-3.7-Flash). IMPORTANT: run names are keyed by label
#                only, so to sweep multiple efforts for one model you MUST put the
#                effort in the label (e.g. step3p7-low / -medium / -high) or later
#                efforts are skipped as "already complete". The script enforces this.
#
# Wall: 3-7 hours for N=3 on Tower2-class hardware. Probably ~6-15 hours on
# slower setups. Plan to run overnight.
#
# Output: logs/p[1-3]_<task>_<model-label>_v[1-N]/  per task family per replicate.
# After completion, run grade_microbench.sh + summarize.sh.

set -euo pipefail

if [ $# -lt 3 ]; then
  cat <<EOF
Usage: $0 <served-model-name> <port> <model-label> [<n>] [<reasoning-effort>]

Runs 12 task families × N replicates against the model on the given vLLM endpoint.

Args:
  served-model-name  what vLLM advertises (e.g. qwen3-coder-next-awq, llama3.3-70b)
  port               vLLM endpoint port (e.g. 8001)
  model-label        short tag for run names (no spaces/slashes; e.g. coder, 27b, llama3-70b)
  n                  N per cell (default 3)
  reasoning-effort   optional low|medium|high|xhigh (reasoning models). Run names are keyed
                     by label, so the effort MUST be in the label when sweeping
                     efforts (e.g. step3p7-low) or later efforts get skipped.

Example:
  $0 my-llama3-70b 8001 llama3-70b 3
  $0 step3p7 8001 step3p7-high 1 high     # effort 'high' is in the label

Recommended workflow:
  1. bash tooling/scripts/smoke_test.sh <model> <port>     # 2-5 min
  2. bash tooling/scripts/run_microbench.sh ...            # 3-7 hours
  3. bash tooling/scripts/grade_microbench.sh <model-label>
  4. bash tooling/scripts/summarize.sh <model-label>
EOF
  exit 1
fi

MODEL="$1"
PORT="$2"
LABEL="$3"
N="${4:-3}"
REASONING_EFFORT="${5:-}"   # optional: low|medium|high|xhigh for models with reasoning levels
REASONING_FLAG=""
[ -n "$REASONING_EFFORT" ] && REASONING_FLAG="--reasoning-effort $REASONING_EFFORT"
REASONING_LOCATION_FLAG=()
if [ -n "$REASONING_EFFORT" ] && [ -n "${BENCH_REASONING_EFFORT_LOCATION:-}" ]; then
  REASONING_LOCATION_FLAG=(--reasoning-effort-location "$BENCH_REASONING_EFFORT_LOCATION")
fi
THINKING="${6:-}"           # optional: on|off for models with an enable_thinking template var (e.g. Qwen3.5-397B)
THINKING_FLAG=""
[ -n "$THINKING" ] && THINKING_FLAG="--thinking $THINKING"
PRESERVE_THINKING_FLAG=()
case "${BENCH_PRESERVE_THINKING:-}" in
  1|true|on) PRESERVE_THINKING_FLAG=(--preserve-thinking on) ;;
  0|false|off) PRESERVE_THINKING_FLAG=(--preserve-thinking off) ;;
  "") ;;
  *) echo "ERROR: invalid BENCH_PRESERVE_THINKING=$BENCH_PRESERVE_THINKING" >&2; exit 2 ;;
esac
MAXLEN="${7:-}"             # optional: served context window (e.g. 131072 for the 397B GGUF on llama.cpp)
MAXLEN_FLAG=""
[ -n "$MAXLEN" ] && MAXLEN_FLAG="--max-model-len $MAXLEN"
MAX_OUTPUT_TOKENS_CAP="${BENCH_MAX_OUTPUT_TOKENS_CAP:-180000}"
if ! [[ "$MAX_OUTPUT_TOKENS_CAP" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: invalid BENCH_MAX_OUTPUT_TOKENS_CAP=$MAX_OUTPUT_TOKENS_CAP" >&2
  exit 2
fi
MAX_OUTPUT_TOKENS_CAP_FLAG="--max-output-tokens-cap $MAX_OUTPUT_TOKENS_CAP"
SERVING_MANIFEST_FLAG=""
[ -n "${BENCH_SERVING_MANIFEST:-}" ] && SERVING_MANIFEST_FLAG="--serving-manifest $BENCH_SERVING_MANIFEST"

# Deterministic run sharding allows one supervisor to drive independent GPU
# replicas without duplicate claims. The default remains the historical single
# lane. A run's zero-based ordinal modulo BENCH_LANE_COUNT owns the run.
LANE_INDEX="${BENCH_LANE_INDEX:-0}"
LANE_COUNT="${BENCH_LANE_COUNT:-1}"
if ! [[ "$LANE_INDEX" =~ ^[0-9]+$ && "$LANE_COUNT" =~ ^[1-9][0-9]*$ ]] || \
   (( LANE_INDEX >= LANE_COUNT )); then
  echo "ERROR: invalid BENCH_LANE_INDEX=$LANE_INDEX BENCH_LANE_COUNT=$LANE_COUNT" >&2
  exit 2
fi

# Sampling overrides via env (default keeps the cross-model temp=0.3 protocol). Some models
# specify a required operating point and loop under low temp — e.g. MiniMax-M2 card mandates
# temperature=1.0, top_p=0.95, top_k=40. Set BENCH_TEMP / BENCH_TOP_P / BENCH_TOP_K to deviate;
# the deviation is recorded per-run in receipt.json (temperature) and must be footnoted in findings.
TEMP="${BENCH_TEMP:-0.3}"
TOPP_FLAG=(); [ -n "${BENCH_TOP_P:-}" ] && TOPP_FLAG=(--top-p "$BENCH_TOP_P")
TOPK_FLAG=(); [ -n "${BENCH_TOP_K:-}" ] && TOPK_FLAG=(--top-k "$BENCH_TOP_K")
MINP_FLAG=(); [ -n "${BENCH_MIN_P:-}" ] && MINP_FLAG=(--min-p "$BENCH_MIN_P")
PRESENCE_FLAG=(); [ -n "${BENCH_PRESENCE_PENALTY:-}" ] && PRESENCE_FLAG=(--presence-penalty "$BENCH_PRESENCE_PENALTY")
REPEAT_FLAG=(); [ -n "${BENCH_REPEAT_PENALTY:-}" ] && REPEAT_FLAG=(--repeat-penalty "$BENCH_REPEAT_PENALTY")
SEED_FLAG=(); [ -n "${BENCH_SEED:-}" ] && SEED_FLAG=(--seed "$BENCH_SEED")

# Historical campaigns exposed every host GPU to task sandboxes. Remote-inference
# campaigns can set BENCH_SANDBOX_GPUS=none so coordinator GPUs are not attached.
SANDBOX_GPU_FLAG=(--gpus all)
case "${BENCH_SANDBOX_GPUS:-all}" in
  none|off|disabled|"") SANDBOX_GPU_FLAG=() ;;
  all) ;;
  *) SANDBOX_GPU_FLAG=(--gpus "$BENCH_SANDBOX_GPUS") ;;
esac

# Guard: run names + the idempotent skip check are keyed by LABEL only. If an
# effort is set but not encoded in the label, a later effort would reuse the same
# run names and be skipped as "already complete". Fail fast instead.
if [ -n "$REASONING_EFFORT" ] && [[ "$LABEL" != *"$REASONING_EFFORT"* ]]; then
  echo "ERROR: --reasoning-effort '$REASONING_EFFORT' is set but label '$LABEL' does not contain it." >&2
  echo "       Run names are keyed by label only, so multiple efforts under one label collide" >&2
  echo "       (later efforts skipped as already-complete). Put the effort in the label, e.g.:" >&2
  echo "         $0 $MODEL $PORT ${LABEL}-${REASONING_EFFORT} ${N} ${REASONING_EFFORT}" >&2
  exit 2
fi

# Same guard for --thinking: run names are keyed by LABEL only, so running
# --thinking off then on under ONE label silently skips the second arm as
# "already complete". Require the mode encoded in the label (nothink / think).
if [ -n "$THINKING" ]; then
  if [ "$THINKING" = "off" ]; then
    want="nothink"; [[ "$LABEL" == *nothink* ]] && ok=1 || ok=0
  else
    want="think"; [[ "$LABEL" == *think* && "$LABEL" != *nothink* ]] && ok=1 || ok=0
  fi
  if [ "$ok" != "1" ]; then
    echo "ERROR: --thinking '$THINKING' is set but label '$LABEL' does not encode it ('$want')." >&2
    echo "       Run names are keyed by label only, so --thinking off then on under one label collide" >&2
    echo "       (the second arm is skipped as already-complete). Put the mode in the label, e.g.:" >&2
    echo "         $0 $MODEL $PORT 397b-${want} ${N} \"\" ${THINKING} ${MAXLEN}" >&2
    exit 2
  fi
fi

TOOLING="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$TOOLING/.." && pwd)"
cd "$REPO_ROOT"

# Sanity: endpoint reachable
if ! curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null; then
  echo "ERROR: vLLM endpoint not reachable on port $PORT."
  exit 2
fi

# Task family → (task prompt file, input dir or "" for none)
# Format: "task_short_name|task_file|input_dir"
TASKS=(
  "p1_bugfix|task_code_adoption.md|tooling/inputs/code-task-starter"
  "p1_testwrite|task_test_writing.md|tooling/inputs/code-task-starter"
  "p1_refactor|task_refactoring.md|tooling/inputs/code-task-starter"
  "p2_extract|task_extraction.md|tooling/inputs/phase2_extraction"
  "p2_ci|task_ci_failure.md|tooling/inputs/phase2_ci_failure"
  "p2_hallucination|task_hallucination.md|tooling/inputs/phase2_hallucination"
  "p2_triage|task_triage.md|tooling/inputs/phase2_triage"
  "p3_doc|task_doc_synthesis.md|tooling/inputs/phase3_doc_synthesis"
  "p3_business|task_business_memo.md|tooling/inputs/phase3_business_memo"
  "p3_market|task_market_research.md|"
  "p3_writing|task_writing_editing.md|tooling/inputs/phase3_writing_editing"
  "p3_pm|task_project_mgmt.md|tooling/inputs/phase3_project_mgmt"
)

TOTAL_RUNS=$(( ${#TASKS[@]} * N ))
if (( LANE_INDEX < TOTAL_RUNS )); then
  ASSIGNED_RUNS=$(( (TOTAL_RUNS - 1 - LANE_INDEX) / LANE_COUNT + 1 ))
else
  ASSIGNED_RUNS=0
fi
START_T=$(date +%s)

echo "==> Microbench chain: $TOTAL_RUNS runs (${#TASKS[@]} task families × N=$N)"
echo "    lane:     $LANE_INDEX/$LANE_COUNT ($ASSIGNED_RUNS assigned runs)"
echo "    model:    $MODEL  (label: $LABEL)"
echo "    port:     $PORT"
echo "    started:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

DONE=0
SKIPPED=0
FAILED=0
RUN_ORDINAL=0

for entry in "${TASKS[@]}"; do
  IFS='|' read -r task_short task_file input_dir <<< "$entry"
  for v in $(seq 1 "$N"); do
    ordinal="$RUN_ORDINAL"
    RUN_ORDINAL=$((RUN_ORDINAL + 1))
    if (( ordinal % LANE_COUNT != LANE_INDEX )); then
      continue
    fi
    run_name="${task_short}_${LABEL}_v${v}"
    DONE=$((DONE + 1))

    # Skip clean completions and explicitly operator-labeled terminal
    # pathologies.  The latter intentionally lack a workspace tarball because
    # the published substance-monitoring protocol SIGTERMs the harness.
    if [ -f "logs/${run_name}/summary.json" ] && [ -f "logs/${run_name}/workspace_final.tar.gz" ]; then
      echo "[$DONE/$TOTAL_RUNS] SKIP $run_name (already complete)"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    if [ -f "logs/${run_name}/receipt.json" ] && \
       [ -f "logs/${run_name}/transcript.jsonl" ] && \
       [ -f "logs/${run_name}/label.json" ] && \
       python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("primary") == "identical-call-loop" else 1)' \
         "logs/${run_name}/label.json"
    then
      echo "[$DONE/$TOTAL_RUNS] SKIP $run_name (operator-labeled terminal pathology)"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi

  # Build flag set
  INPUT_FLAG=""
  [ -n "$input_dir" ] && INPUT_FLAG="--input-mount $input_dir"

  # p1_testwrite requires stricter instructions to force real workspace edits.
  SYSTEM_FLAG=()
  STUCK_THRESHOLD=500
  case "$task_short" in
    p1_testwrite)
      SYSTEM_FLAG=(--system "$TOOLING/prompts/p1_testwrite_system.md")
      REQUIRE_FILES=(--require-files "CHANGELOG.md,decisions.md,research.md")
      STUCK_THRESHOLD=250
      # p1_testwrite gets a strict schema to avoid discovery-only loops.
      ;;
    *)
      REQUIRE_FILES=()
      ;;
  esac

  echo "[$DONE/$TOTAL_RUNS] $run_name  (started $(date +%H:%M:%S))"
  if python3 "$TOOLING/harness.py" \
    "$run_name" \
    "$TOOLING/tasks/$task_file" \
      --model "$MODEL" \
      --port "$PORT" \
      --temperature "$TEMP" \
      "${TOPP_FLAG[@]}" \
      "${TOPK_FLAG[@]}" \
    "${MINP_FLAG[@]}" \
    "${PRESENCE_FLAG[@]}" \
    "${REPEAT_FLAG[@]}" \
    "${SEED_FLAG[@]}" \
    --stuck-threshold "$STUCK_THRESHOLD" \
    $REASONING_FLAG \
    "${REASONING_LOCATION_FLAG[@]}" \
    $THINKING_FLAG \
    "${PRESERVE_THINKING_FLAG[@]}" \
    $MAXLEN_FLAG \
    $MAX_OUTPUT_TOKENS_CAP_FLAG \
    $SERVING_MANIFEST_FLAG \
    "${SYSTEM_FLAG[@]}" \
    "${REQUIRE_FILES[@]}" \
    $INPUT_FLAG \
    --docker-socket \
    "${SANDBOX_GPU_FLAG[@]}" 2>&1 | tail -3
    then
      :
    else
      echo "  WARN: harness exited non-zero for $run_name (check logs/${run_name}/)"
      FAILED=$((FAILED + 1))
    fi
  done
done

ELAPSED=$(( $(date +%s) - START_T ))
H=$(( ELAPSED / 3600 ))
M=$(( (ELAPSED % 3600) / 60 ))

echo ""
echo "==> Microbench chain complete"
echo "    total:    $ASSIGNED_RUNS assigned runs (of $TOTAL_RUNS campaign runs)"
echo "    skipped:  $SKIPPED (already complete from prior invocations)"
echo "    failed:   $FAILED (see logs/<run_name>/transcript.jsonl)"
echo "    elapsed:  ${H}h${M}m"
echo ""
echo "Next:"
echo "    bash $TOOLING/scripts/grade_microbench.sh $LABEL"
echo "    bash $TOOLING/scripts/summarize.sh $LABEL"
