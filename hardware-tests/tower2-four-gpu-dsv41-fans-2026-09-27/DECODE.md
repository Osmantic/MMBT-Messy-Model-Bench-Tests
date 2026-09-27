# Decode performance as an acceptance criterion

The selection objective is lower sustained uniform fan percentage while preserving useful native inference performance. A candidate cannot qualify on temperature and fan percentage alone. The matched comparison requires both warm simultaneous decode and whole-run end-to-end throughput to establish no more than3% loss against the fixed85% reference.

## What is measured

Each completed C8 request wave contains eight independently recorded streaming responses. The harness retains monotonic arrival times, cumulative output token counts, final output IDs and provider usage. The analyzer reconstructs and validates those streams before computing a rate. Its observable is delivered tokens per second at the client, not an internal kernel timing or an upstream benchmark number.

For each wave, the common decode interval starts at the latest first-token arrival among its eight requests and ends at the earliest last-token arrival. It is clipped to the final600 seconds of telemetry. The numerator is the sum of positive delivered-token increments whose timestamps fall after the clipped start and at or before the clipped end, across all eight streams. The denominator is the sum of those common intervals. Prefill, gaps between waves and drainage are excluded. Streaming can deliver several tokens together, so this remains a delivery-based rate.

The actual numerator, denominator and rate are published together. At least300 common decode seconds are required within the600-second window. In the prospective30-minute comparison that window follows at least twenty minutes of warmup. A short cold burst, the first wave or a full-run peak does not replace it.

Whole-run end-to-end throughput divides all completed output tokens by the recorded run elapsed time, including prefill and request drainage. This is a separate criterion because a decode-only improvement could still leave users waiting longer. TTFT and request latency median/p95 remain descriptive companions. The final180-second decode rate is retained as a secondary observation.

The two-hour rolling soak uses immediate stream replacement instead of synchronized waves. Its separate analyzer constructs simultaneous active-decoding intervals from individual delivery traces, retaining coverage and occupancy/refill evidence. Its rate must be labeled as rolling-load performance rather than substituted into the matched synchronized-wave interval.

## Comparative inference

The experimental unit is the matched pair. Three pairs use reference/candidate, candidate/reference, reference/candidate order with new fixtures, identical candidate bytes, identical executable source snapshots and the same native runtime and boot. Both requested and enforced GPU limits remain275 W on all four cards.

For each metric, calculate the three log candidate/reference rate ratios. Their mean and sample standard deviation produce a two-sided95% Student-t interval with two degrees of freedom, using t=4.302652729911275. Exponentiate its limits. Both decode and end-to-end lower bounds must be at least0.97. A favorable mean with an uncertain interval is not a pass; hundreds of requests do not create hundreds of independent fan-profile replications.

Three pairs cannot validate the assumed distribution of paired errors. Room inlet temperature was not instrumented, and counterbalancing cannot remove every host or environmental effect. The conclusion is limited to the tested curves and recorded conditions. Raw negative closing slopes, failed runs and procedural changes remain visible in the evidence rather than being silently omitted.

A completed pair below0.97 already rules out this specific three-pair acceptance gate. If the lowest log ratio is m and the mean is u, the sample standard deviation is at least sqrt(3)/2 times (u-m). Therefore the interval lower limit is at most u-(t/2)(u-m), which is no greater than m because t=4.30265 exceeds2. This supports stopping remaining runs of that candidate while preserving its measured pair and the stop receipt. It is not a one-pair population confidence interval or proof of thermal causality.

## Interpretation and future comparisons

Record clocks, thermal and power-limit event counters, reported power, global memory/swap traffic and model-process faults alongside each rate. A late slow wave or a change in clocks alone does not establish thermal throttling. Global paging alone does not establish model attribution. Requested/enforced275 W settings are distinct from short reported power readings above275 W.

Future fan, model, runtime or hardware changes should use the same delivery/coverage definitions, fresh matched runs and their actual source/configuration identities. Changing input length, output length, concurrency, warmup or workload scheduling needs a distinct label. Preserve decode and end-to-end comparisons together, rather than optimizing fan noise at an unmeasured performance cost.
