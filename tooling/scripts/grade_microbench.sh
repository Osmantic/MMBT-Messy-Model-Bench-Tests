#!/usr/bin/env bash
# Grade all microbench runs for a given model label.
#
# Usage: bash tooling/scripts/grade_microbench.sh <model-label>
#
# Iterates logs/p[1-3]_*_<model-label>_v*/, picks the right grader per task
# family, writes grade.json next to the run's other artifacts.
#
# Idempotent — skips runs that already have grade.json.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <model-label>"
  echo "Example: $0 llama3-70b"
  exit 1
fi

LABEL="$1"
TOOLING="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$TOOLING/.." && pwd)"
LOGS_DIR="${REPO_ROOT}/logs"
GT="${TOOLING}/graders/ground_truth"
GRADERS="${TOOLING}/graders"

if [ ! -d "$LOGS_DIR" ]; then
  echo "ERROR: $LOGS_DIR not found. Run run_microbench.sh first."
  exit 2
fi

# Map run prefix → (grader, ground_truth)
declare -A GRADER
declare -A GT_FILE
GRADER[p1_bugfix]="${GRADERS}/phase1_grade.py"
GRADER[p1_testwrite]="${GRADERS}/phase1_grade.py"
GRADER[p1_refactor]="${GRADERS}/phase1_grade.py"
GRADER[p2_extract]="${GRADERS}/phase2_extraction_grade.py"
GRADER[p2_ci]="${GRADERS}/phase2_ci_failure_grade.py"
GRADER[p2_hallucination]="${GRADERS}/phase2_hallucination_grade.py"
GRADER[p2_triage]="${GRADERS}/phase2_triage_grade.py"
GRADER[p3_doc]="${GRADERS}/phase3_doc_synthesis_grade.py"
GRADER[p3_business]="${GRADERS}/phase3_business_memo_grade.py"
GRADER[p3_market]="${GRADERS}/phase3_market_research_grade.py"
GRADER[p3_writing]="${GRADERS}/phase3_writing_editing_grade.py"
GRADER[p3_pm]="${GRADERS}/phase3_project_mgmt_grade.py"

GT_FILE[p1_bugfix]=""  # phase1 graders don't take a separate ground-truth file
GT_FILE[p1_testwrite]=""
GT_FILE[p1_refactor]=""
GT_FILE[p2_extract]="${GT}/phase2_extraction.json"
GT_FILE[p2_ci]=""  # ci_failure grader re-runs ruff+pytest, no separate GT
GT_FILE[p2_hallucination]="${GT}/phase2_hallucination.json"
GT_FILE[p2_triage]="${GT}/phase2_triage.json"
GT_FILE[p3_doc]="${GT}/phase3_doc_synthesis.json"
GT_FILE[p3_business]="${GT}/phase3_business_memo.json"
GT_FILE[p3_market]="${GT}/phase3_market_research_rubric.json"
GT_FILE[p3_writing]="${TOOLING}/inputs/phase3_writing_editing/audience_briefs.json"
GT_FILE[p3_pm]="${GT}/phase3_project_mgmt.json"

GRADED=0
SKIPPED=0
NOT_FOUND=0

shopt -s nullglob
for run_dir in "${LOGS_DIR}"/p[1-3]_*_${LABEL}_v*/; do
  run=$(basename "$run_dir")
  tarball="${run_dir}/workspace_final.tar.gz"

  if [ ! -f "$tarball" ]; then
    echo "SKIP $run (no workspace_final.tar.gz — run may have been killed mid-run)"
    NOT_FOUND=$((NOT_FOUND + 1))
    continue
  fi
  if [ -f "${run_dir}/grade.json" ]; then
    echo "SKIP $run (already graded)"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Identify task prefix (e.g. p2_extract from p2_extract_llama3-70b_v1)
  prefix=$(echo "$run" | sed -E "s/_${LABEL}_v[0-9]+\$//")
  grader="${GRADER[$prefix]:-}"
  gt="${GT_FILE[$prefix]:-}"

  if [ -z "$grader" ]; then
    echo "SKIP $run (unknown task prefix: $prefix)"
    NOT_FOUND=$((NOT_FOUND + 1))
    continue
  fi

  # Extract workspace. Phase-1 grading runs pytest/ruff in a root sandbox, which
  # leaves root-owned .ruff_cache/.pytest_cache here; a plain rm then fails with
  # "Permission denied" and (under set -e) aborts the whole grade pass. Fall back
  # to sudo so re-grades are clean.
  workspace="/tmp/grade_${run}"
  if ! rm -rf "$workspace" 2>/dev/null; then
    workspace_parent=$(dirname "$workspace")
    workspace_name=$(basename "$workspace")
    case "$workspace_name" in
      grade_[A-Za-z0-9._-]*) ;;
      *) echo "unsafe grade workspace name: $workspace_name" >&2; exit 2 ;;
    esac
    docker run --rm --network none --read-only \
      -e "CLEANUP_NAME=$workspace_name" \
      -v "$workspace_parent:/cleanup:rw" \
      sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 \
      sh -c 'rm -rf -- "/cleanup/$CLEANUP_NAME"'
  fi
  mkdir -p "$workspace"
  tar -xzf "$tarball" -C "$workspace"

  echo "GRADE $run  (task=$prefix)"
  case "$prefix" in
    p1_bugfix|p1_testwrite|p1_refactor)
      # Phase-1 codebase tasks: phase1_grade.py wraps code_task_grader.py, which
      # runs pytest/ruff/cov/bench on workspace vs the logalyzer starter baseline.
      # Must run INSIDE the sandbox (needs pytest/ruff/bench deps) and needs the
      # baseline starter. Signature: phase1_grade.py <task> <workspace> <baseline>.
      task1="${prefix#p1_}"
      baseline_src="${REPO_ROOT}/tooling/inputs/code-task-starter"
      if [ ! -d "$baseline_src" ]; then
        echo "  (phase1 baseline missing: $baseline_src — cannot grade)"; GRADED=$((GRADED+1)); continue
      fi
      docker run --rm \
        -v "${workspace}":/ws \
        -v "${baseline_src}":/base:ro \
        -v "${TOOLING}/graders":/g:ro \
        -v "${run_dir}":/out \
        --entrypoint python3 bench-sandbox:latest \
        /g/phase1_grade.py "$task1" /ws /base --out /out/grade.json 2>&1 | tail -1 || \
        echo "  (phase1 grader failed — see ${run_dir}/grade.json or stderr)"
      ;;
    p2_ci)
      # This grader executes the delivered project and requires its pinned
      # pytest/ruff toolchain. Run it in the same reproducible sandbox used for
      # Phase 1 instead of depending on executables installed on the host.
      docker run --rm \
        -v "${workspace}":/ws \
        -v "${TOOLING}/graders":/g:ro \
        -v "${run_dir}":/out \
        --entrypoint python3 bench-sandbox:latest \
        /g/phase2_ci_failure_grade.py /ws --out /out/grade.json 2>&1 | tail -1 || \
        echo "  (CI grader failed — see ${run_dir}/grade.json or stderr)"
      ;;
    *)
      if [ -n "$gt" ]; then
        python3 "$grader" "$workspace" "$gt" --out "${run_dir}/grade.json" 2>&1 | tail -1 || \
          echo "  (grader failed — see ${run_dir}/grade.json or stderr)"
      else
        python3 "$grader" "$workspace" --out "${run_dir}/grade.json" 2>&1 | tail -1 || \
          echo "  (grader failed — see ${run_dir}/grade.json or stderr)"
      fi
      ;;
  esac
  GRADED=$((GRADED + 1))
done

echo ""
echo "==> Grading complete"
echo "    graded:    $GRADED"
echo "    skipped:   $SKIPPED (already had grade.json)"
echo "    not found: $NOT_FOUND (no workspace tarball, or unknown task prefix)"
echo ""
echo "Next: bash $TOOLING/scripts/summarize.sh $LABEL"
