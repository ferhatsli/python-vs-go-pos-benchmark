# Benchmark Architecture

## Purpose

The benchmark isolates application-stack differences while retaining a shared database, deterministic synthetic datasets, workload contracts, and correctness gates.

```text
                         k6 / worker runner
                                |
                   +------------+------------+
                   |                         |
          Python/FastAPI stack          Go stack
          Uvicorn + SQLAlchemy          net/http + pgx
                   |                         |
                   +------------+------------+
                                |
                         PostgreSQL 17
                                |
                            Redis 8

                   metrics + invariants + summaries
                                |
                    normalized Track A evidence
```

Only one application runtime is active during a measured trial.

## Workload families

Track A covers eight contract families across device, payment, operational, and worker paths:

- heartbeat;
- configuration;
- card payment;
- QR contention;
- RF contention;
- command lifecycle;
- dashboard;
- worker evaluation.

The load runner and worker path share the same deterministic dataset profile selected for each trial.

## Measurement surfaces

Each HTTP trial records, where available:

- latency distribution values retained by k6;
- achieved request/iteration rate;
- failures and dropped iterations;
- application CPU and memory samples;
- PostgreSQL CPU/memory and connection state;
- lock/wait/deadlock samples;
- `pg_stat_statements` deltas;
- WAL and database counter deltas;
- invariant output.

Worker trials additionally record:

- duration;
- devices evaluated;
- devices per second;
- `<5s` overrun status;
- database statement behavior;
- invariant output.

## Evidence flow

```text
raw trial artefacts
        |
        v
matrix summaries + final normalized summary
        |
        v
compact public evidence
        |
        v
publication CSV data
        |
        +--> GitHub charts
        +--> Medium figures
        +--> validated quantitative claims
```

This keeps charts and prose downstream from the same evidence base.

## Reproduction modes

The historical private source freeze and the public benchmark are intentionally separated.

- `strict`, `workload`, and `frozen` are historical/private-source validation modes and require an explicit `POS_ROOT`.
- `public` verifies the self-contained public repository plus `docs/source-freeze/public-provenance.json` and does not require the private source tree.

This prevents a public reproduction from claiming a source validation it cannot independently perform.
