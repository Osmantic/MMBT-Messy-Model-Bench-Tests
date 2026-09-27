# Qwen3.8-27B Q4 MMBT remote lanes

This bundle prepares two exclusive benchmark replicas without exposing an
inference port to the LAN. It deliberately reuses the already-installed,
pinned Dream Fleet tunnels:

- Tower2 `127.0.0.1:18101` -> Tower1 `127.0.0.1:11434`
- Tower2 `127.0.0.1:18103` -> Tower3 `127.0.0.1:11434`

The production ODS server and the benchmark server are mutually exclusive on
each remote loopback port. No tunnel install, relink, restart, or replacement
is part of this launcher.

`ensure-qwen38-lanes.sh --check` is read-only. It verifies host/user identity,
model bytes, image identity, runtime revision, binary hash when the identical
production image is live, GPU UUID, the enforced 500 W limit, and the effective
unit/hash of each existing tunnel. A healthy production endpoint is reported
as not matching the benchmark profile because it uses a 131,072-token context.

The default launcher is intentionally fail-closed. Before it can start a
benchmark replica, the production `ods-llama-server` container must already be
drained and stopped and GPU memory use must be below 4096 MiB. The launcher
never stops or replaces production. A mismatched existing benchmark container
also causes a hard failure rather than automatic deletion.

Validate the committed bundle:

```bash
python3 tooling/deployments/qwen3.8-27b-q4-fleet/validate_campaign_deployment.py
bash tooling/deployments/qwen3.8-27b-q4-fleet/ensure-qwen38-lanes.sh --check
```

After the maintenance drain and all preregistration gates, the MMBT autopilot
invokes the launcher through `tooling/qwen3.8-27b-q4-t1-t3-mmbt.json`. Do not
invoke the mutating mode while production ODS inference is serving.

The planned benchmark runtime uses the exact pinned Q4 artifact and llama.cpp
image, one 262,144-token slot per 5090, Q8 K/V cache, full GPU offload, flash
attention, Jinja, in-band reasoning, and no context shift. MTP remains disabled
until separate quality-parity evidence justifies changing the manifest.
