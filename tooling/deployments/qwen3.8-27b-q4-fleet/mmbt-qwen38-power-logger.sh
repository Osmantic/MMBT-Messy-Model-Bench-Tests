#!/usr/bin/env bash
set -euo pipefail

state_dir="$HOME/.local/state/dream-fleet/mmbt/qwen38-27b-q4-n20"
output="$state_dir/power.csv"
mkdir -p "$state_dir"
if [[ ! -s "$output" ]]; then
  echo 'timestamp_utc,host,gpu_uuid,power_draw_w,power_limit_w,temperature_c,memory_used_mib,memory_total_mib,utilization_gpu_pct,graphics_clock_mhz' > "$output"
fi

while true; do
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
  host="$(hostname)"
  nvidia-smi \
    --query-gpu=uuid,power.draw,power.limit,temperature.gpu,memory.used,memory.total,utilization.gpu,clocks.current.graphics \
    --format=csv,noheader,nounits |
    while IFS= read -r row; do
      printf '%s,%s,%s\n' "$timestamp" "$host" "$row"
    done >> "$output"
  sleep 5
done
