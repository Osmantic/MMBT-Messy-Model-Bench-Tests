#!/usr/bin/env bash
set -euo pipefail

# Prepare or repair the two remote benchmark lanes without ever stopping the
# production ODS model or mutating Tower2's existing fleet tunnels. The
# operator must drain/stop ODS before invoking the mutating default mode.
# --check is strictly read-only and is safe before the maintenance window.

MODE=ensure
case "${1:-}" in
  "") ;;
  --check) MODE=check ;;
  -h|--help)
    echo "usage: $0 [--check]"
    echo "  --check  verify pinned prerequisites and existing tunnels without starting containers"
    exit 0
    ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

MODEL_ALIAS=Qwen3.6-27B-UD-Q4_K_XL
MODEL_REL=qwen3.6-27b-ud-q4-k-xl/Qwen3.6-27B-UD-Q4_K_XL.gguf
MODEL_SIZE=17612564704
MODEL_SHA256=ff6941ded525b34eb159496762c29dd0ec6e71dc31b74d57e75d871a03eec259
IMAGE_REF=dream-fleet/llama.cpp@sha256:0c8dc7c0954fe5e1d75118a4f880f17252f62d1d01e24716b172afe9fafd85a1
IMAGE_ID=sha256:0c8dc7c0954fe5e1d75118a4f880f17252f62d1d01e24716b172afe9fafd85a1
LLAMA_COMMIT=9d57ce456c94d241dde672b2db9cf18879766568
LLAMA_BINARY_SHA256=fc6a6a15230a2dd6c56aae913e6d0d1b4913015e0966d800c08da8dce57b376e
REMOTE_PORT=11434
CONTAINER=mmbt-qwen36-bench
SERVER_PROFILE=qwen36-27b-udq4xl-ctx262144-q8kv-np1-v1
EXPECTED_CTX=262144
EXPECTED_SLOTS=1

SSH_OPTS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
)

# lane|ssh alias|hostname|user|Tower2 port|GPU UUID|existing tunnel unit|unit SHA-256
LANES=(
  "1|tower3|tower3|tower3|18103|GPU-e0311306-9389-a863-fc29-dfed7d0e97c3|dream-fleet-tunnel-tower3.service|13796b4386dca90d2c1f2806e8ed0314321758ab8e891e41d4203450e5728a2f"
)

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

endpoint_matches() {
  local port=$1
  curl -fsS --max-time 5 "http://127.0.0.1:${port}/v1/models" 2>/dev/null |
    python3 -c 'import json,sys
expected,ctx=sys.argv[1],int(sys.argv[2])
payload=json.load(sys.stdin)
items=payload.get("data", []) + payload.get("models", [])
ids=[]
contexts=[]
for item in items:
    if not isinstance(item, dict):
        continue
    ids.extend(str(item.get(key, "")) for key in ("id", "name", "model"))
    meta=item.get("meta") or {}
    if meta.get("n_ctx") is not None:
        contexts.append(int(meta["n_ctx"]))
raise SystemExit(0 if expected in ids and ctx in contexts else 1)' \
      "$MODEL_ALIAS" "$EXPECTED_CTX"
}

verify_existing_tunnel() {
  local local_port=$1 unit=$2 expected_sha=$3
  systemctl --user is-active --quiet "$unit" || die "required existing tunnel is not active: $unit"
  local fragment actual_sha effective
  fragment=$(systemctl --user show "$unit" --property=FragmentPath --value)
  test -f "$fragment" || die "tunnel fragment is missing: $fragment"
  actual_sha=$(sha256sum "$fragment" | awk '{print $1}')
  test "$actual_sha" = "$expected_sha" || die "tunnel unit hash drifted: $unit"
  effective=$(systemctl --user show "$unit" --property=ExecStart --value)
  [[ "$effective" == *"127.0.0.1:${local_port}:127.0.0.1:${REMOTE_PORT}"* ]] ||
    die "tunnel forwarding drifted: $unit"
}

verify_remote_static() {
  local ssh_alias=$1 expected_host=$2 expected_user=$3 gpu_uuid=$4
  ssh "${SSH_OPTS[@]}" "$ssh_alias" bash -s -- \
    "$expected_host" "$expected_user" "$MODEL_REL" "$MODEL_SIZE" "$MODEL_SHA256" \
    "$IMAGE_REF" "$IMAGE_ID" "$LLAMA_COMMIT" "$LLAMA_BINARY_SHA256" "$gpu_uuid" <<'REMOTE'
set -euo pipefail
expected_host=$1
expected_user=$2
model_rel=$3
model_size=$4
model_sha=$5
image_ref=$6
image_id=$7
llama_commit=$8
llama_binary_sha=$9
gpu_uuid=${10}

test "$(hostname)" = "$expected_host"
test "$(id -un)" = "$expected_user"
model="/home/${expected_user}/ods/data/models/${model_rel}"
test -f "$model"
test "$(stat -c %s "$model")" = "$model_size"
test "$(sha256sum "$model" | awk '{print $1}')" = "$model_sha"

actual_image=$(docker image inspect "$image_ref" --format '{{.Id}}')
test "$actual_image" = "$image_id"
actual_revision=$(docker image inspect "$image_ref" \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')
test "$actual_revision" = "$llama_commit"

# If the identical image is already serving production, prove the exact binary
# hash without creating a throwaway container in read-only check mode.
if docker ps --format '{{.Names}}' | grep -Fxq ods-llama-server; then
  running_image=$(docker inspect ods-llama-server --format '{{.Image}}')
  test "$running_image" = "$image_id"
  actual_binary=$(docker exec ods-llama-server sha256sum /app/llama-server | awk '{print $1}')
  test "$actual_binary" = "$llama_binary_sha"
fi

actual_gpu=$(nvidia-smi --query-gpu=uuid --format=csv,noheader,nounits | head -1)
test "$actual_gpu" = "$gpu_uuid"
power_limit=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits | head -1)
awk -v value="$power_limit" 'BEGIN { exit !(value >= 499.5 && value <= 500.5) }'
REMOTE
}

ensure_remote_server() {
  local ssh_alias=$1 expected_user=$2
  ssh "${SSH_OPTS[@]}" "$ssh_alias" bash -s -- \
    "$expected_user" "$MODEL_REL" "$MODEL_SHA256" "$IMAGE_REF" "$IMAGE_ID" \
    "$MODEL_ALIAS" "$REMOTE_PORT" "$CONTAINER" "$SERVER_PROFILE" \
    "$EXPECTED_CTX" "$EXPECTED_SLOTS" <<'REMOTE'
set -euo pipefail
expected_user=$1
model_rel=$2
model_sha=$3
image_ref=$4
image_id=$5
model_alias=$6
remote_port=$7
container=$8
server_profile=$9
expected_ctx=${10}
expected_slots=${11}

require_drained_gpu() {
  local used_mib
  used_mib=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  awk -v value="$used_mib" 'BEGIN { exit !(value < 4096) }' || {
    echo "GPU is not drained (${used_mib} MiB used); refusing benchmark server start" >&2
    exit 24
  }
}

if docker ps --format '{{.Names}}' | grep -Fxq ods-llama-server; then
  echo "production container ods-llama-server is still running; drain/stop it before benchmark mode" >&2
  exit 20
fi

if docker container inspect "$container" >/dev/null 2>&1; then
  test "$(docker inspect "$container" --format '{{.Image}}')" = "$image_id" || {
    echo "existing $container uses an unexpected image; refusing replacement" >&2
    exit 21
  }
  test "$(docker inspect "$container" --format '{{ index .Config.Labels "mmbt.model-sha256" }}')" = "$model_sha" || {
    echo "existing $container has an unexpected model receipt; refusing replacement" >&2
    exit 22
  }
  test "$(docker inspect "$container" --format '{{ index .Config.Labels "mmbt.server-profile" }}')" = "$server_profile" || {
    echo "existing $container has an unexpected serving profile; refusing replacement" >&2
    exit 23
  }
  if ! docker inspect "$container" --format '{{.State.Running}}' | grep -Fxq true; then
    require_drained_gpu
    docker start "$container" >/dev/null
  fi
else
  require_drained_gpu
  docker run -d --name "$container" --restart=no --gpus all --shm-size 8g \
    --label mmbt.campaign=qwen38-27b-q4-t1-t3 \
    --label "mmbt.model-sha256=$model_sha" \
    --label "mmbt.server-profile=$server_profile" \
    --read-only --tmpfs /tmp:rw,nosuid,size=1g --tmpfs /root/.nv:rw,nosuid,size=2g \
    -v "/home/${expected_user}/ods/data/models:/models:ro" \
    -p "127.0.0.1:${remote_port}:8080" \
    "$image_ref" \
    --model "/models/${model_rel}" \
    --alias "$model_alias" \
    --host 0.0.0.0 --port 8080 \
    --n-gpu-layers 999 \
    --ctx-size "$expected_ctx" \
    --batch-size 2048 --threads 4 --parallel "$expected_slots" \
    --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 \
    --jinja --reasoning-format none --no-context-shift --metrics >/dev/null
fi

for _ in $(seq 1 120); do
  if curl -fsS --max-time 5 "http://127.0.0.1:${remote_port}/v1/models" 2>/dev/null |
      python3 -c 'import json,sys
expected,ctx=sys.argv[1],int(sys.argv[2])
p=json.load(sys.stdin)
items=p.get("data", []) + p.get("models", [])
ids=[]
contexts=[]
for item in items:
    if not isinstance(item, dict):
        continue
    ids.extend(str(item.get(k, "")) for k in ("id", "name", "model"))
    meta=item.get("meta") or {}
    if meta.get("n_ctx") is not None:
        contexts.append(int(meta["n_ctx"]))
raise SystemExit(0 if expected in ids and ctx in contexts else 1)' \
        "$model_alias" "$expected_ctx"
  then
    exit 0
  fi
  if ! docker inspect "$container" --format '{{.State.Running}}' 2>/dev/null | grep -Fxq true; then
    docker logs --tail 80 "$container" >&2 || true
    exit 25
  fi
  sleep 5
done
docker logs --tail 80 "$container" >&2 || true
echo "benchmark server failed readiness deadline" >&2
exit 26
REMOTE
}

for lane_spec in "${LANES[@]}"; do
  IFS='|' read -r lane ssh_alias expected_host expected_user local_port gpu_uuid unit unit_sha <<<"$lane_spec"
  log "lane $lane static verification: $expected_host via $ssh_alias"
  verify_remote_static "$ssh_alias" "$expected_host" "$expected_user" "$gpu_uuid"
  verify_existing_tunnel "$local_port" "$unit" "$unit_sha"
  if [ "$MODE" = check ]; then
    if endpoint_matches "$local_port"; then
      log "lane $lane benchmark profile is currently reachable on 127.0.0.1:$local_port"
    else
      log "lane $lane prerequisites and existing tunnel verified; current endpoint is not the benchmark profile"
    fi
    continue
  fi
  log "lane $lane ensuring dedicated benchmark server behind the existing tunnel"
  ensure_remote_server "$ssh_alias" "$expected_user"
  endpoint_matches "$local_port" || die "lane $lane failed final model/context identity check"
done

log "qwen3.8 lane ${MODE} complete"
