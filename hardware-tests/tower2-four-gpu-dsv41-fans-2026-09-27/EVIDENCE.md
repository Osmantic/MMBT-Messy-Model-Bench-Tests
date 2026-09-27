# Evidence, provenance and acceptance limits

The owner accepted the practical cooling/noise behavior and ended additional qualification on2026-09-27. The two-hour soak was explicitly waived. This package preserves measurements and original failures rather than claiming that omitted tests passed.

## Read the compact evidence

- [Selected profile and descriptive comparison](evidence/v2-selected-base80-review.json): all six actual source/profile snapshot bytes and analysis linkage were checked against the installed controller and frozen harness. Formal comparison status remains **not-qualified**. The descriptive end-to-end95% lower ratio0.968594 also misses the declared0.97 performance limit.
- [Owner-ended extra validation](evidence/v2-owner-ended-validation.json): the partial C1 phase is owner-interrupted, not a hardware failure. No further hot-fault/burst/65k/reboot/soak claim is made.
- [Final persistent installation](evidence/v2-final-persistent-install.json): same measured controller/profile bytes, same lease, all eight automatic policies and275W caps verified during installation; fresh custom readiness and boot enablement.
- [Cold native startup and actual routed inference](evidence/v2-final-runtime-routing.json): the bounded-log native replacement returned correct authenticated and routed arithmetic JSON, with `X-Dream-Fleet-Endpoint: tower2`. This is an owned-model cold restart, not a real host reboot.
- [Trusted Pixel routing and per-call accounting](evidence/v2-final-pixel-routing-accounting.json): the documentation-navigation turn used the native DSV backend; imports are idempotent. Private agent sessions are not exported. Two initial arithmetic calls lost their usage receipts because of a proof-harness schema error and are excluded from known accounting; two saved chat calls report unknown cache split.
- [Matched results table](figures/matched-descriptive-comparison.csv) and [figure](figures/matched-descriptive-comparison.png): actual six completed runs, with the ineligible thirdcandidate visibly marked. The failed parent thirdreference remains in the evidence too.
- [Checkpoint verification](evidence/v2-checkpoint-verification.json):88 files/510,313,345,146bytes verified against the pinned Hugging Face revision. Weights and API-key values are excluded.
- [Raw archive manifest](evidence/raw-archive-manifest.json):59 completed, failed or owner-interrupted phases;16,816 files with hashes, including the exact used nonce-bearing input corpora, raw sensor traces, retained incoherent reads, delivery traces, provider receipts and source snapshots.

The original formal comparer and gates remain intact. The separately named limited-selection helpers accept only the exact SHA256 of the unqualified-selection receipt, preserve all cap/identity/normal-temperature/recovery checks, and do not manufacture a qualified comparison. Current-source CPU and idle faults, older-source loaded faults, installation, cold native startup and actual OS-reboot proof are different evidence categories. See [FAULT-EVIDENCE.md](FAULT-EVIDENCE.md).

## Full raw release assets

Release: [Tower2 four-GPU DSV4.1 fan study](https://github.com/Osmantic/MMBT-Messy-Model-Bench-Tests/releases/tag/tower2-four-gpu-dsv41-fans-2026-09-27).

| Asset | Bytes | SHA256 |
|---|---:|---|
| [Controller study raw evidence](https://github.com/Osmantic/MMBT-Messy-Model-Bench-Tests/releases/download/tower2-four-gpu-dsv41-fans-2026-09-27/final-raw-evidence.tar.gz) |121680549|`f6b5e771fe8e73b78df5fc058f956c71cf756e525b73e5b3d3e8d1e8d09d4745`|
| [Earlier automatic baseline / native study evidence](https://github.com/Osmantic/MMBT-Messy-Model-Bench-Tests/releases/download/tower2-four-gpu-dsv41-fans-2026-09-27/automatic-baseline-evidence.tar.gz) |105689873|`cee1e3283ff8162297570affc56471740005982098f9dd0ded64d08c979a7b09`|

The full controller archive was created before the final Pixel accounting receipt completed; that later compact receipt is separately versioned in Git and is not claimed to be inside the earlier archive. The archive key scan found no native API-key value in selected plaintext. The export avoids checkpoint weights, private agent sessions, arbitrary host files and still-running phases. Verify these hashes before extraction. `source-manifest.json` separately pins the published package files; it is not a substitute for a live health check or hardware acceptance.

## Local execution accounting

Native benchmark generation supplied useful local hardware workload; Codex directly engineered and accepted the critical controller, as requested. The final navigation packet used native DSV through the trusted Pixel route. Fresh-token local share exceeded90%; gross share was about35%, because Codex's long supervisory context had extensive cached reads. The exact measured checkpoint is saved with the package. Neither ratio is an exact subscription-usage or dollar conversion, and these benchmark receipts do not imply that controller engineering was delegated.
