# Referencing or adapting the controller

This is source for a measured four-card Linux installation, with deliberately explicit ownership and identity checks. It is not a generic installer for arbitrary GPUs. The achieved evidence belongs to the published bytes and Tower2 conditions; formal performance uncertainty and omitted tests remain explicit. Changes need their own evidence. You can reuse the control design without adopting the native model or its large checkpoint.

## Inspect before adapting

The useful entry points are [policy.py](controller/policy.py) for the curve and state transitions, [hardware.py](controller/hardware.py) for NVML reads and fan operations, [controller.py](controller/controller.py) for the primary loop, [observer.py](controller/observer.py) for independent supervision, [recovery.py](controller/recovery.py) for restoration, and [workload.py](controller/workload.py) for exact owned-container suspension. [common.py](controller/common.py) defines the fixed hardware and state contract. [CONTROL.md](CONTROL.md) explains their interaction without requiring a line-by-line source reading.

The tested driver was NVIDIA 595.58.03 on a system using systemd 255.4. The GPUs are RTX PRO 6000 Blackwell Workstation Edition, each exposing two controllable fans. A different model may not expose these fan APIs. Check exact identity, fan count, default-policy restoration, target readback and RPM support on the intended hardware. A device name or a successful `nvidia-smi` query alone does not prove manual fan support.

Record inventory using read-only commands such as:

```sh
nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,power.limit --format=csv
systemctl --version
```

GPU indices are convenient labels, not stable control identities. Keep a separate physical map if useful; fan demand should still use the hottest valid member of the intended GPU set. Do not transfer this study's unmeasured gap dimensions or fan percentage to another stack as a calibrated airflow quantity.

## Contracts that require review

| Contract | Where to review | Why copying it blindly fails |
|---|---|---|
| Exact GPU UUID set | `common.py`, `hardware.py`, `common.validate_sample` | The current implementation expects exactly four GPUs and two fans per card. Changing only UUIDs does not generalize cardinality or fan count. |
| Power budget | `hardware.py`, `common.py`, profile validator, cap service/guard and analyzers | The tested 275 W contract is enforced independently of a JSON curve. Merely editing `power_limit_w` does not establish a new supported budget. |
| Fan table and timing | Selected `gpu-profile.json`, `policy.py` | Curve knots, startup, active/idle floors, protection, filtering and rate limits jointly define behavior. A colder table is not automatically faster or quieter. |
| Filesystem and privilege boundary | `common.BASE`, state paths, `/opt/mmbt/gpu-control`, `/etc/mmbt`, services and installer | Root service code/configuration must not be writable by untrusted users. Preserve the permanent lease pathname and inode throughout operations. |
| Owned workload | `common.CONTAINER`, `workload.py`, model unit and private runtime receipt | Container ID, image, current boot, PID start time and exact cgroup are validated. Changing a display name cannot safely authorize freezing another workload. |
| Startup/resumption | `model-gate.py`, three service units and offline model wrapper | Unit ordering is supplemented by fresh hardware proofs. An unrelated application's restart behavior must be reviewed separately. |
| NVML dependency | Included `pynvml.py` and its retained BSD header | The pinned standalone binding still needs the installed NVIDIA driver library. Keep dependency provenance and requalify changed bindings or drivers. |
| Study harness paths | Constants in `harness/` and fixture/runtime receipts | Helpers target this study workspace and deployment; they are reproducibility/reference tools, not an automatic discovery mechanism. |

The update bridge `harness/install-control-v2.py` specifically updates an existing Tower2 installation. It requires the three owned units already to exist and be inactive/failed, and the resident owned model to be running but paused. It is intentionally not a fresh-host bootstrap. A fresh installation needs reviewed directory ownership, state provisioning, cap management, workload ownership and unit setup appropriate to that host.

## Keep decision tests separate from live hardware tests

The pure/controller contract cases can be inspected and run before live installation:

```sh
python3 -m unittest discover -s controller -p test_control.py -v
```

Those tests use injected observations/adapters. They cannot prove another GPU's manual fan API, a physical fan's behavior, systemd recovery, or cold boot. Linux is the operating target; passing some policy tests on another platform does not make the services portable there.

For an adaptation, first establish read-only sampling and verified restoration to automatic. Then qualify one writer and common readback while idle; actual STOP/KILL recovery; representative loaded thermal and decode measurements; hot faults; removal and rollback; and real reboot before relying on unattended persistence. Change one clearly recorded configuration at a time, keep failed traces, and preserve exact source/profile hashes. [REPRODUCE.md](REPRODUCE.md) states the original workload, comparison windows and statistical gates; [FAULT-EVIDENCE.md](FAULT-EVIDENCE.md) identifies the actual proof categories.

The temperature limits and response deadlines here are decisions for this owner and stack. Do not silently raise them to make an adaptation pass. If the hardware, model workload or acoustic preference differs, declare that difference and design its acceptance criteria prospectively.

## Reference the evidence accurately

Use the final source manifest and selected profile together with the compact analyses in Git. Verify the full-trace release asset's SHA256 and byte count before regenerating results. A telemetry mean without its window, a decode rate without simultaneous coverage, a CPU fault test without its injected condition, or a source hash without an actual installed proof can all misstate what was achieved.

This study uses fan percentage as a within-stack noise proxy and NVML as the source of operating observations. It does not measure dBA, absolute airflow, every Engram page's residency, the full configured context, or a universal optimum. Keep those boundaries when quoting the results or adapting the design.
