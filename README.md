# Python vs Go POS Backend Benchmark

![Python vs Go POS backend benchmark hero](assets/hero/benchmark-hero.svg)

A reproducible Python/FastAPI vs Go benchmark using **production-inspired POS backend workloads**.

> Same PostgreSQL. Same datasets. Same correctness constraints. Frozen Track A implementations.

This repository is an evidence-first benchmark package. It compares two application stacks under the same synthetic workload model, resource limits, database, transaction semantics, and correctness gates. It is not a benchmark of the theoretical limits of either language.

## TL;DR

Go was already the leading architectural candidate for the backend project that motivated this experiment. The useful question was not *“is Go faster?”* but *“how large is the practical gap, where does it appear, and what still remains an architecture problem?”*

The strongest Track A findings were:

| Scenario | Python | Go | What it means |
|---|---:|---:|---|
| D1 CARD @100 median p95 | 2.96 s | 156 ms | ~19x lower p95 latency for the Go stack in this workload |
| D2 CARD @500 median p95 | 15.66 s | 928 ms | The gap remains large as payment load increases |
| D3 Dashboard @100 median p95 | 2.46 s | 512 ms | ~4.8x lower p95 latency |
| D3 Dashboard @200 median p95 | 4.20 s | 899 ms | ~4.7x lower p95 latency |
| D3 Worker, 50,000 devices | 27.00 s | 10.15 s | Go is materially faster, but **both miss the <5 s target** |

The final Track A decision is:

**`EVALUATE_BROADER_GO_MIGRATION`**

That does **not** mean “rewrite everything immediately.” The D3 Worker result, query-count behavior, and extreme capacity failures show that runtime choice and architecture still need to be treated as separate engineering problems.

## Why I Built This

For an upcoming backend project, Go was already the leading architectural candidate. I did not want to justify that direction with a generic statement such as “Go is faster than Python.”

Instead, I built a controlled benchmark around **production-inspired POS backend workloads**: device heartbeat/configuration traffic, payment flows, contention cases, dashboards, command lifecycle processing, and a device-evaluation worker.

The goal was to quantify the size and shape of the difference while keeping the important semantics fixed.

This repository models production-inspired POS backend workloads. It does not reproduce or disclose a specific production system.

## What Is Being Compared

### Python stack

- Python 3.12
- FastAPI
- SQLAlchemy 2 async
- asyncpg
- Redis async client
- single-process Uvicorn
- default access logging enabled
- no uvloop

### Go stack

- Go
- `net/http`
- `pgx/v5`
- explicit SQL
- Redis client
- no equivalent per-request access log
- 5-second handler context timeout

### Shared benchmark boundary

Both stacks use the same:

- PostgreSQL instance and schema/indexes;
- Redis instance;
- synthetic dataset profiles;
- transaction and lock semantics;
- application DB pool ceiling;
- resource budgets;
- workload scripts and scenario definitions;
- correctness hard gates;
- warmup/measured matrix rules.

## Benchmark Architecture

![Benchmark architecture diagram](assets/diagrams/benchmark-architecture.svg)

The load generator or Worker drives one runtime at a time. Both runtimes interact with the same benchmark PostgreSQL/Redis services. Metrics, PostgreSQL snapshots, lock evidence, trial summaries, and invariant checks are retained as evidence.

See [docs/architecture.md](docs/architecture.md) for the runtime and measurement boundaries.

## Workloads and Dataset Scale

![D1 to D3 dataset scale](assets/diagrams/dataset-scale.svg)

The benchmark uses three deterministic synthetic profiles:

| Profile | Devices | D3 context |
|---|---:|---|
| D1 | 500 | Baseline acceptance scale |
| D2 | 5,000 | 10x device scale |
| D3 | 50,000 | 5,000 stations, 500 companies, ~1M payment rows |

The workload set covers:

- heartbeat;
- configuration retrieval;
- CARD payment;
- QR payment contention;
- RF payment contention;
- dashboard queries;
- command lifecycle;
- device-evaluation Worker.

## Key Results

### CARD payment p95

![CARD payment p95 latency chart](assets/charts/card-p95.svg)

At **D1 CARD @100**, median p95 dropped from **~2.96 s on the Python stack to ~156 ms on the Go stack — roughly a 19x latency difference** for this specific workload.

The difference remained large at D2:

| D2 CARD load | Python median p95 | Go median p95 |
|---:|---:|---:|
| 100 | 3.27 s | 189 ms |
| 250 | 7.91 s | 445 ms |
| 500 | 15.66 s | 928 ms |

These are workload-bound observations, not a claim that the Go language is universally “Nx faster” than Python.

### Dashboard scaling

![Dashboard p95 latency chart](assets/charts/dashboard-p95.svg)

At D3:

- Dashboard @100: **~2.46 s Python vs ~512 ms Go** median p95.
- Dashboard @200: **~4.20 s Python vs ~899 ms Go** median p95.

The Go stack retained a roughly 4–5x p95 advantage in these D3 dashboard scenarios.

### Worker

![Worker duration and throughput chart](assets/charts/worker.svg)

At D3, the Worker evaluates **50,000 devices**:

- Python median duration: **~27.00 s**;
- Go median duration: **~10.15 s**;
- Python median rate: **~1,852 devices/s**;
- Go median rate: **~4,947 devices/s**.

Both runtimes exceed the **<5 s** target. The Worker intentionally preserves per-device/query-count behavior in Track A, so this result points to future set-based/batching/N+1 work rather than a language-only fix.

## D3 Findings

![D3 canonical capacity evidence](assets/charts/d3-capacity.svg)

Two extreme D3 levels hit the canonical stop-escalation rule on the Python warmup:

- **Heartbeat @1667:** p95 ~36.42 s, achieved throughput ~112.6 req/s, HTTP error rate ~43.8%, 42,864 dropped iterations; correctness invariants still passed.
- **CARD @1000:** p95 ~38.08 s, achieved throughput ~31.3 req/s, HTTP error rate ~41.2%; correctness invariants still passed.

Because the canonical scenario stopped at those failure points, this public package does **not** present a paired Go number for those levels. Separate diagnostic work existed during the investigation, but no retained raw diagnostic artefact is included in the public evidence package, so diagnostic numeric claims are intentionally excluded.

The bottleneck evidence is more useful than the headline latency alone:

![Application vs PostgreSQL bottleneck diagram](assets/diagrams/bottleneck.svg)

At the key D3 failures, the evidence does not support global PostgreSQL lock contention as the primary explanation. Python application/request-path saturation and queueing are stronger candidates, while payment workloads also show connection pressure. The benchmark therefore does not reduce the result to “the database was slow.”

## Correctness

Performance was accepted only when correctness hard gates remained intact.

Accepted Track A trials did not observe invalidating failures for:

- duplicate payment;
- QR double redemption;
- RF double spend;
- negative wallet or duplicate debit;
- idempotency mismatch;
- illegal command transition;
- partial financial commit;
- Worker alarm correctness.

A faster result that violated those invariants would not count as a valid performance result.

## Reproduce It

### Requirements

- Docker with Docker Compose
- Git
- Python 3.12 for local validation scripts

The public repository is self-contained. It does **not** require the private source repository that was used to establish historical Track A provenance.

Validate the public boundary and workload contracts:

```bash
export ISOLATION_MODE=public
bash scripts/verify_isolation.sh
python3 scripts/validate_contracts.py
```

Run a small self-contained smoke trial for both runtimes:

```bash
export ISOLATION_MODE=public
export BENCH_DRY_RUN=1
export BENCH_OVERWRITE=1

bash scripts/run_scenario.sh python D1 smoke public-repro measured 1
bash scripts/run_scenario.sh go D1 smoke public-repro measured 1
bash scripts/stop_stack.sh all
```

For canonical matrix structure without executing the load:

```bash
BENCH_PLAN_ONLY=1 bash scripts/run_matrix.sh payment-card D1 example-run 100
```

Historical provenance for the frozen benchmark source is recorded in [docs/source-freeze/public-provenance.json](docs/source-freeze/public-provenance.json). `ISOLATION_MODE=public` verifies the self-contained public reproduction boundary; it does not pretend to re-run the original private-source 9/9 hash gate.

## Methodology

Track A follows these rules:

- 2 warmups per runtime;
- alternating Python → Go / Go → Python measured blocks;
- at least 5 measured runs;
- continue up to 10 measured runs when p95 CV exceeds 10%;
- mark the matrix `UNSTABLE` when CV remains above 10% at the maximum;
- only one runtime active during a measured trial;
- correctness failure invalidates the performance result;
- stop escalation when a scenario reaches a canonical capacity/hard failure condition.

Stored k6 summaries do **not** include p99. No p99 value is inferred or published.

Full methodology: [docs/methodology.md](docs/methodology.md).

## Fairness and Limitations

**This benchmark compares these two frozen application stacks under these workloads. It does not measure the theoretical performance limit of either Python or Go.**

Important asymmetries were intentionally frozen instead of tuned mid-matrix:

- Python uses single-process Uvicorn;
- Python default access logging is enabled;
- Python does not use uvloop;
- Go has no equivalent per-request access log;
- Go handlers use a 5-second context timeout;
- Python uses SQLAlchemy async/asyncpg while Go uses explicit SQL/pgx.

This means the benchmark answers a concrete stack question, not an abstract language-limit question.

It also does not prove that a Go migration alone solves:

- Worker query-count/N+1 behavior;
- SQL architecture problems;
- database scaling problems;
- all extreme D3 capacity targets.

Track B is intentionally separate future work: runtime tuning, set-based Worker queries, batching, fewer DB round trips, and ingestion architecture changes must not be mixed into the Track A result.

Full limitations: [docs/limitations.md](docs/limitations.md).

## Full Report

![Final benchmark decision](assets/diagrams/final-decision.svg)

The complete normalized Track A decision report is available at:

- [results/track-a-20260831/report.md](results/track-a-20260831/report.md)
- [results/track-a-20260831/summary.json](results/track-a-20260831/summary.json)
- [compact public evidence](results/track-a-20260831/evidence/)
- [publication chart data](assets/data/)

Final decision: **`EVALUATE_BROADER_GO_MIGRATION`**.

The decision means the observed evidence is strong enough to evaluate a broader migration scope. It is **not** an automatic recommendation for a full rewrite without considering architecture, operational risk, delivery cost, and the workloads that remain bottlenecked elsewhere.

## Repository Structure

```text
.
├── python/                 # Python/FastAPI benchmark implementation
├── go/                     # Go benchmark implementation
├── contracts/              # workload behavior contracts
├── db/                     # benchmark PostgreSQL schema, indexes, seed/reset
├── load/                   # k6 workload scripts
├── scripts/                # orchestration and validation
│   └── publication/        # public audit/evidence/chart tooling
├── metrics/                # metrics and PostgreSQL evidence collection
├── assets/
│   ├── data/               # evidence-derived chart inputs
│   ├── charts/             # quantitative SVG figures
│   ├── diagrams/           # explanatory SVG figures
│   └── hero/               # publication/social assets
├── docs/                   # methodology, architecture, limitations, provenance
└── results/track-a-20260831/
    ├── summary.json
    ├── report.md
    └── evidence/           # compact public verification evidence
```

## Citation / License

This repository is released under the **MIT License**. See [LICENSE](LICENSE).

Citation metadata is available in [CITATION.cff](CITATION.cff).

If you reproduce or extend the benchmark, keep Track A results separate from optimized variants so readers can tell which changes came from runtime choice and which came from architecture/tuning.
