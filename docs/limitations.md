# Fairness, Limitations, and Confounders

This benchmark compares two **frozen application stacks under the same benchmark workloads**. It does not measure the theoretical performance limit of either Python or Go.

## Runtime asymmetries

### Python stack

- FastAPI
- SQLAlchemy async
- asyncpg
- single-process Uvicorn
- default access logging enabled
- no uvloop

### Go stack

- `net/http`
- `pgx/v5`
- explicit SQL
- no equivalent per-request access log
- 5-second handler context timeout

These differences are part of Track A. They were not changed mid-matrix because doing so would mix stack tuning with the frozen runtime comparison.

## What the results mean

The results support claims about these concrete stacks and workloads. They do **not** support blanket statements such as “Go is N times faster than Python.” Every public quantitative statement must identify the workload, load level where relevant, and metric.

A future Python configuration with multiple Uvicorn workers, uvloop, different logging, pool tuning, or query changes could produce different results. Those experiments belong to a separately labelled track.

## Database and architecture limits

Go materially extends capacity in several scenarios, but the benchmark also finds workloads where changing runtime alone is insufficient.

D3 Worker evaluates 50,000 devices and preserves the intentional per-device query behavior. Both runtimes miss the `<5s` target, so that result is evidence for query-count and architectural optimization work, not evidence that a language rewrite alone solves the worker path.

At extreme D3 heartbeat and payment levels, stop-escalation prevents pretending that a failed target is a valid stable matrix. Database CPU, connection pressure, lock samples, application CPU, achieved throughput, failure rate, and generator limits must be read together.

## p99

The retained k6 summaries did not capture p99. Public material must therefore show p99 as not captured rather than estimate or reconstruct it.

## Diagnostics

Task-level diagnostics may be useful for bottleneck analysis, but diagnostic numeric claims are publishable only when a retained raw artefact exists. Diagnostic evidence must never be presented as if it were a canonical paired matrix result.

## Cost claims

The Track A artefacts do not contain a monetary infrastructure price model. The publication may discuss resource efficiency such as throughput per CPU or memory where calculated, but it must not invent a dollar-cost or replica-cost percentage.

## Public provenance

The public repository contains historical provenance for the frozen Track A source boundary without disclosing the private source repository. `ISOLATION_MODE=public` verifies the public reproduction boundary only.
