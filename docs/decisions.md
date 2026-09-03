# Benchmark Decision Ledger

## 2026-09-03 — Track A Python vs Go

**Decision: `EVALUATE_BROADER_GO_MIGRATION`**

Validated Track A evidence shows Go materially outperforming the frozen Python implementation across multiple device-facing, dashboard, and worker workloads while preserving tested correctness. The result exceeds the predefined serious-candidate thresholds in multiple scenarios, and D3 evidence identifies Python runtime/request-path saturation as a binding constraint before database-wide saturation is established.

This decision does **not** claim that Go alone solves every scaling target. D3 Worker @50000 exceeds the 5-second target in both runtimes, and extreme D3 heartbeat/CARD levels require architectural follow-up. Track A runtime asymmetries (Python Uvicorn/access logging/no uvloop vs Go `net/http`/no equivalent request log/5-second handler timeout) are recorded as confounders and were not tuned mid-matrix.

Historical source provenance records that the frozen-source gate passed 9/9 at the pinned commit. The self-contained public reproduction mode does not require or disclose the private source repository and does not claim to repeat that private-source validation.

Evidence: `results/track-a-20260831/report.md` and `results/track-a-20260831/summary.json`.
