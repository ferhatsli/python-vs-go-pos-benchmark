# Python vs Go Track A Benchmark Decision Report

Run ID: `track-a-20260831`

Frozen POS source: `271e4ee207aa56b4b9322376cd40fa76130ea6b7`

Frozen-source isolation: **PASS (9/9 frozen source hashes unchanged)**

## Decision

**`EVALUATE_BROADER_GO_MIGRATION`**

Track A provides broad, repeated evidence that the Go implementation materially outperforms the frozen Python implementation while preserving the tested correctness invariants. The strongest differences are well above the predefined 20% “small difference” band and, in multiple workloads, exceed the 2x serious-candidate threshold. D3 also shows that neither implementation is sufficient at every design target without architectural work: heartbeat @1667 and CARD @1000 hit canonical capacity failure, and Worker @50000 exceeds the 5s target in both runtimes. Therefore this is evidence to evaluate a broader Go migration, not evidence that a language rewrite alone removes all scaling bottlenecks.

## Method and evidence limits

- Same frozen workload source, PostgreSQL, datasets, SQL/transaction semantics, correctness expectations, resource limits, and app DB pool were retained under Track A.
- Measured trials used the canonical AB/BA matrix and unstable scenarios continued to 10 measured trials, then were marked `UNSTABLE`.
- Stored k6 summaries do **not** include p99. `summary.json` records p99 as `null`; no p99 value is inferred.
- Headline normalized values below are medians across measured trials. Every normalized record in `summary.json` includes its raw trial file paths.
- Python/Go runtime asymmetries are confounders: Python is single-process Uvicorn with default access logging and no uvloop; Go has no equivalent per-request access log and uses a 5s handler context timeout. These were intentionally not changed mid-matrix.
- The canonical `ISOLATION_MODE=frozen` gate passes. A separate strict working-tree equality check currently fails because the POS repository contains concurrent changes relative to the benchmark-start status baseline. Those changes were not reset or incorporated into Track A; therefore this report claims frozen-source reproducibility, not current POS working-tree equality.

## Workload-by-workload results

| Workload | Load | Python p95 | Go p95 | Python RPS | Go RPS | Python CPU | Go CPU | Python RAM | Go RAM | DB CPU Python | DB CPU Go | DB stmt/unit | Lock wait | WAL/unit | Correctness | Bottleneck | Winner | Decision relevance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| D1 command-lifecycle | None | 421.3 ms | 50.0 ms | 74.5 | 450.9 | 28.0% | 3.5% | 54.3 MiB | 3.5 MiB | 1.2% | 2.2% | 9.65 | 0 | 8 | PASS | NO_SATURATION | GO | Material; `results/track-a-20260831/D1/command-lifecycle/matrix-summary.json` |
| D1 configuration | None | 293.4 ms | 18.2 ms | 356.2 | 4975.0 | 114.9% | 198.2% | 62.1 MiB | 12.5 MiB | 29.0% | 341.5% | 6.99 | 0 | 0 | PASS | APP_CPU | GO | Material; `results/track-a-20260831/D1/configuration/matrix-summary.json` |
| D1 dashboard | 50 | 385.4 ms | 79.5 ms | 194.7 | 1322.0 | 108.4% | 76.2% | 60.9 MiB | 14.5 MiB | 54.5% | 404.0% | 10.98 | 0 | 0 | PASS | DB_CPU | GO | Material; `results/track-a-20260831/D1/dashboard-level-50/matrix-summary.json` |
| D1 heartbeat | 17 | 11.6 ms | 7.8 ms | 15.6 | 15.6 | 12.9% | 3.8% | 55.9 MiB | 10.2 MiB | 2.7% | 2.9% | 10.00 | 0 | 971 | PASS | NO_SATURATION | GO | Material; `results/track-a-20260831/D1/heartbeat-level-17/matrix-summary.json` |
| D1 payment-card | 100 | 2960.1 ms | 155.8 ms | 108.2 | 809.7 | 107.1% | 119.9% | 67.9 MiB | 13.8 MiB | 41.0% | 405.2% | 41.97 | 0 | 2474 | PASS | APP_CPU | GO | Material; `results/track-a-20260831/D1/payment-card-level-100/matrix-summary.json` |
| D1 payment-qr-contention | None | 2362.0 ms | 1004.7 ms | 41.6 | 93.8 | 55.8% | 23.9% | 63.4 MiB | 10.7 MiB | 10.7% | 4.0% | 36.33 | 0 | 1034 | PASS | NO_SATURATION | GO | Material; `results/track-a-20260831/D1/payment-qr-contention/matrix-summary.json` |
| D1 payment-rf-contention | None | 2274.5 ms | 838.6 ms | 43.0 | 111.6 | 55.0% | 23.1% | 62.9 MiB | 10.6 MiB | 9.0% | 3.3% | 36.36 | 0 | 1457 | PASS | NO_SATURATION | GO | Material; `results/track-a-20260831/D1/payment-rf-contention/matrix-summary.json` |
| D1 worker | 500 | 302.6 ms | 235.5 ms | 1653.0 | 2123.7 | N/A% | N/A% | N/A MiB | N/A MiB | 3.3% | 3.1% | 1.03 | 0 | 5 | PASS | QUERY_COUNT | GO | Material; `results/track-a-20260831/D1/worker-level-500/matrix-summary.json` |
| D2 configuration | None | 280.8 ms | 17.0 ms | 366.3 | 5022.6 | 108.4% | 198.1% | 61.6 MiB | 12.5 MiB | 27.9% | 349.0% | 6.99 | 0 | 112 | PASS | APP_CPU | GO | Material; `results/track-a-20260831/D2/configuration/matrix-summary.json` |
| D2 dashboard | 100 | 1282.0 ms | 179.5 ms | 192.8 | 825.5 | 108.5% | 56.2% | 64.7 MiB | 16.6 MiB | 76.8% | 398.0% | 10.98 | 0 | 0 | PASS | DB_CPU | GO | Material; `results/track-a-20260831/D2/dashboard-level-100/matrix-summary.json` |
| D2 dashboard | 50 | 318.9 ms | 92.8 ms | 228.2 | 893.8 | 110.0% | 53.4% | 61.0 MiB | 14.3 MiB | 77.0% | 404.1% | 10.98 | 0 | 0 | PASS | DB_CPU | GO | Material; `results/track-a-20260831/D2/dashboard-level-50/matrix-summary.json` |
| D2 heartbeat | 167 | 806.9 ms | 5.7 ms | 158.0 | 158.2 | 79.0% | 26.2% | 71.5 MiB | 20.6 MiB | 23.1% | 19.1% | 9.99 | 0 | 1050 | PASS | NO_SATURATION | GO | Material; `results/track-a-20260831/D2/heartbeat-level-167/matrix-summary.json` |
| D2 payment-card | 100 | 3269.7 ms | 189.1 ms | 86.8 | 695.9 | 108.6% | 89.3% | 66.2 MiB | 13.8 MiB | 42.8% | 405.4% | 41.96 | 0 | 2451 | PASS | APP_CPU | GO | Material; `results/track-a-20260831/D2/payment-card-level-100/matrix-summary.json` |
| D2 payment-card | 250 | 7909.5 ms | 444.7 ms | 99.2 | 739.9 | 111.1% | 109.5% | 75.2 MiB | 20.7 MiB | 40.8% | 406.2% | 41.97 | 0 | 3150 | PASS | APP_CPU | GO | Material; `results/track-a-20260831/D2/payment-card-level-250/matrix-summary.json` |
| D2 payment-card | 500 | 15659.3 ms | 927.5 ms | 94.3 | 683.3 | 112.5% | 108.8% | 87.5 MiB | 32.3 MiB | 43.6% | 406.0% | 41.97 | 0 | 2964 | PASS | APP_CPU | GO | Material; `results/track-a-20260831/D2/payment-card-level-500/matrix-summary.json` |
| D2 worker | dataset | 2148.8 ms | 1162.8 ms | 2327.1 | 4300.7 | N/A% | N/A% | N/A MiB | N/A MiB | 5.0% | 3.2% | 1.00 | 0 | 3 | PASS | QUERY_COUNT | GO | Material; `results/track-a-20260831/D2/worker/matrix-summary.json` |
| D3 dashboard | 100 | 2456.0 ms | 512.1 ms | 131.3 | 291.7 | 101.8% | 34.0% | 65.1 MiB | 15.7 MiB | 147.6% | 402.5% | 10.97 | 0 | 0 | PASS | DB_CPU | GO | Material; `results/track-a-20260831/D3/dashboard-level-100/matrix-summary.json` |
| D3 dashboard | 200 | 4197.3 ms | 899.5 ms | 179.3 | 334.1 | 100.8% | 30.9% | 69.2 MiB | 20.6 MiB | 145.1% | 399.2% | 10.98 | 0 | 209 | PASS | DB_CPU | GO | Material; `results/track-a-20260831/D3/dashboard-level-200/matrix-summary.json` |
| D3 worker | dataset | 27000.3 ms | 10149.2 ms | 1851.9 | 4946.7 | N/A% | N/A% | N/A MiB | N/A MiB | 20.9% | 28.7% | 1.00 | 0 | 27 | PASS | QUERY_COUNT | GO | Material; `results/track-a-20260831/D3/worker/matrix-summary.json` |

## D3 capacity and stop-escalation evidence

- `results/track-a-20260831/D3/heartbeat-level-1667/python/warmup-1`: python canonical warmup failed at load `1667`; p95 36424.3 ms, throughput 112.6, error rate 43.8%, dropped 42864, invariants PASS. Per canonical stop-escalation, the next level was not run.
- `results/track-a-20260831/D3/payment-card-level-1000/python/warmup-1`: python canonical warmup failed at load `1000`; p95 38082.1 ms, throughput 31.3, error rate 41.2%, dropped 0, invariants PASS. Per canonical stop-escalation, the next level was not run.

Additional diagnostic evidence captured during Task 11 (outside the canonical paired matrix) showed Go could drive much higher throughput than Python at the D3 heartbeat and CARD failure points, but Go still did not fully sustain the target arrival rates. Those diagnostics are capacity evidence, not replacements for the frozen canonical result.

## Bottleneck classification

- **Python runtime / request path:** D3 heartbeat and CARD evidence shows severe application-side queueing while PostgreSQL CPU/lock evidence does not support DB lock saturation as the primary cause. `APP_CPU` is the primary classification for these capacity failures.
- **PostgreSQL:** connection pressure appears in payment runs, but deadlocks and lock wait samples do not support lock contention as the dominant global explanation.
- **Worker:** both runtimes preserve the intentional per-device query behavior. D3 Worker is classified `QUERY_COUNT`; both exceed 5s, while Go remains materially faster. Set-based/N+1 optimization belongs to Track B, not this Track A report.
- **Load generator:** the D3 heartbeat diagnostic reached the VU ceiling, so generator limits are a secondary confounder at the extreme point; the Go diagnostic nevertheless demonstrated generator capacity far above Python achieved throughput.

## Scaling conclusion

Across D1 → D2 → D3, Go retains a large latency advantage on device-facing and dashboard workloads. Python degradation becomes severe at high heartbeat/payment load before PostgreSQL evidence indicates a database-wide saturation condition. Go extends capacity materially but does not make D3 design targets universally safe: Worker remains over target and extreme heartbeat/payment levels need architectural work.

## Decision thresholds

- Differences under 20% are treated as small unless they resolve an SLO failure; the major observed Go advantages are substantially larger than this band.
- The serious-candidate criterion is met by evidence of >=2x effective capacity/latency advantage across multiple relevant workloads, together with Python runtime binding evidence at D3.
- A precise app-replica **cost** ratio cannot be claimed from these artefacts because no monetary infrastructure price model is recorded. Resource-efficiency metrics (RPS/core and RPS/GiB) are retained in `summary.json` inputs where calculable, but they are not converted into currency.
- PostgreSQL does not consistently saturate before Python. In the key D3 heartbeat evidence, app runtime/request-path saturation is the stronger explanation.

## Correctness

All completed canonical measured matrices retained invariant correctness. The hard-gate classes—duplicate payment, QR double redemption, RF double spend, negative wallet/duplicate debit, idempotency mismatch, illegal command transition, partial financial commit, and worker alarm correctness—were not observed as invalidating failures in the accepted Track A trials.

## Recommendation

Proceed with **`EVALUATE_BROADER_GO_MIGRATION`** as the Track A technology conclusion. Keep the scope evidence-driven: Go is justified as a serious broader migration candidate, but D3 results also require separate architecture/query optimization work. Do not present Go alone as solving Worker N+1/query-count behavior or extreme design-target capacity.

## Raw evidence

Normalized evidence and raw-file links are in [`summary.json`](./summary.json). Matrix summaries and individual trial artefacts remain under `results/track-a-20260831/D1`, `D2`, and `D3`.
