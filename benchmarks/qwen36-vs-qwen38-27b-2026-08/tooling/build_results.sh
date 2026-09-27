#!/bin/sh
# Rebuild the MMBT 3.6-vs-3.8 results tables from the frozen dataset.
#
# Order matters: mmbt_results.py writes results.json, defect_diag.py APPENDS the
# defect_diagnostics block to it, and make_md.py renders both into markdown.
# Running them out of order (or running mmbt_results.py again afterwards) drops
# the diagnostics block.
#
# No third-party dependencies; python3 stdlib only.
set -e
cd "$(dirname "$0")"

echo "== validating estimators =="
python3 test_stats.py

echo "== computing tables from the frozen dataset =="
python3 mmbt_results.py

echo "== appending grader-defect diagnostics =="
python3 defect_diag.py > /dev/null

echo "== rendering markdown =="
python3 make_md.py

echo
echo "Outputs:"
ls -l /home/michael/pr-staging/results.json /home/michael/pr-staging/results-tables.md
