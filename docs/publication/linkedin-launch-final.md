Go was already the leading candidate for a backend project I’m working on.

But “Go is faster than Python” wasn’t a useful enough answer.

I wanted to know: **by how much, under workloads that actually resemble the system we’re building?**

So I built a reproducible benchmark around production-inspired POS backend workloads and compared a Python/FastAPI stack with a Go stack under the same PostgreSQL database, synthetic datasets, resource limits, transaction semantics, and correctness gates.

A few results stood out:

• At CARD @100, median p95 was ~2.96s on the Python stack vs ~156ms on the Go stack — roughly a 19x latency difference for that workload.

• At D3 Dashboard @100, median p95 was ~2.46s vs ~512ms.

• On the 50,000-device D3 Worker, Python completed in ~27.00s vs ~10.15s for Go.

The last result is also the important counterpoint: **both runtimes missed the Worker’s <5s target.**

That changed the conclusion from a simple “Go wins” benchmark into something more useful.

The evidence supports evaluating a broader Go migration, but it also shows where changing the runtime is not enough. Query count, batching, database round trips, and architecture still matter.

I also kept the benchmark’s limitations explicit: the Python side is single-process Uvicorn with default access logging and no uvloop, while the Go side uses net/http + pgx and has a 5-second handler timeout. Track A was intentionally frozen instead of tuning either side mid-matrix.

I wrote up the methodology, D1→D3 scaling behavior, bottleneck analysis, correctness gates, and what I would test next in a Track B.

Full engineering write-up:
https://medium.com/@ferhatsli/python-vs-go-pos-backend-benchmark-results-from-500-to-50-000-devices-c5ce0218d7dd

Reproducible benchmark + evidence:
https://github.com/ferhatsli/python-vs-go-pos-benchmark
