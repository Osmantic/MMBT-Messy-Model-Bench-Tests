# Controller failure evidence

Status: practical installation accepted by the owner; extra qualification ended and the soak waived. This table distinguishes decision tests from actual host behavior. A prior loaded test is not automatically transferred to a repaired installation. Each proof retains its source hashes and boot identity.

| Path | Evidence already obtained | What it establishes |
|---|---|---|
| Policy inputs and transitions |46 CPU cases across policy, adapter, observer, recovery and ownership boundaries | Hottest-card selection, malformed/duplicate/stale data rejection, bounded settling, startup behavior and emergency decisions using injected observations |
| Fan adapter failures | CPU partial-write/default-policy/readback cases | All eight restoration attempts are made; incomplete restoration cannot report success; caps precede manual writes |
| Failed logging and blocked native calls | CPU cases and real subprocess timeout with a deliberately stalled CPU shim | Verified automatic restoration precedes the logging failure response; a blocked child is terminated rather than extending continuity indefinitely. No real driver hang was induced |
| Permanent writer lease | Actual kernel STOP/KILL lease proof and installed competing-writer attempt | A stopped holder retains exclusivity; killing it releases the same inode; a second writer is rejected before hardware access |
| Primary STOP at idle | Automatic handoff4.78s, custom ready14.87s | Actual systemd supervision and hardware recovery on the current installed source |
| Primary KILL at idle | Automatic handoff0.54s, custom ready10.67s | Actual restart after a killed writer |
| Observer STOP at idle | Automatic handoff5.82s, custom ready9.12s | Independent watchdog/cleanup response |
| Observer KILL at idle | Automatic handoff0.62s, custom ready3.52s | Actual recovery after a killed observer |
| Persistent invalid configuration | Automatic handoff0.48s; owned runtime suspension observed31.13s after the nonrenewable recovery epoch | Production recovery deadline survives repeated restart attempts.30s is the request threshold, not a claim that suspension was confirmed within exactly30s |
| Docker RPC unavailable | Actual root-owned, identity-validated cgroup freeze in0.030s; explicit fresh unfreeze | Kernel fallback controls only the exact owned workload when the Docker endpoint is deliberately absent. This is not an actual Docker daemon restart |
| Current hot primary/observer faults | Not run after the owner ended extra qualification | No current-source hot-load recovery claim. Earlier-source loaded receipts remain separate |
| Real reboot and boot gating | Boot units enabled; actual host reboot not performed in the final validation | Startup ordering is configured, not demonstrated by a new-boot receipt |
| Final continuous C8 soak | Explicitly waived by the owner | No two-hour-soak claim. Completed30-minute matched phases remain actual load evidence |
| Final byte-identical installation | Passed; all eight automatic policies verified during update,275W caps retained, same permanent lease and exact controller/profile hashes | Actual installed sources and fresh readiness, with boot enablement. Separate cold native startup verifies the bounded-log replacement |

The four current idle process proofs retained275W requested/enforced limits and preserved the paused resident model. Their hottest observed cores were48–53C; they do not prove hot-load behavior. Earlier loaded failures belonged to earlier installed source versions and remain archived separately.

The normal controller and observer do not use a model to choose fan speed. Recovery restores documented NVIDIA automatic policies before sacrificing model continuity when custom visibility is lost. Under the tested load, automatic cooling is a short bridge because the baseline reached90C in about four minutes. At a positively observed90C condition, the guards latch the event and suspend the owned runtime while retaining strong observable cooling. Persistent critical activity permits an exact owned-cgroup kill. A critical latch is not cleared automatically.

NVML percentage/RPM fields are driver-reported operating observations. These tests do not constitute an independent physical tachometer or demonstrate immunity to every fan, driver, kernel or power failure. The acceptance claim is limited to the actual injected software faults, installed versions and recorded hardware behavior.
