#!/bin/sh
set -eu
echo "Starting four-card 275 W cap guard; previous higher limits will not be restored."
while :; do
  limits=$(nvidia-smi --query-gpu=power.limit,enforced.power.limit --format=csv,noheader,nounits) || exit 1
  count=$(printf '%s\n' "$limits" | wc -l)
  [ "$count" -eq 4 ] || { nvidia-smi -pl 275; echo "Unexpected GPU count: $count" >&2; exit 1; }
  if printf '%s\n' "$limits" | awk -F, '{ if ($1+0 != 275 || $2+0 != 275) bad=1 } END { exit bad ? 0 : 1 }'; then
    nvidia-smi -pl 275
  fi
  sleep 2
done
