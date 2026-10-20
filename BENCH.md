# Benchmark notes

This is a small correctness-focused sample, not a performance claim for production-sized databases. The benchmark is included so a reviewer can reproduce the measurement.

## Artefact 1 — Environment

* Date: 2026-10-16
* Runtime: Python 3.10+
* Dependencies: Python standard library
* Target: SQLite file database
* Workload: 3 users, 3 products, 2 orders, 3 order items

## Artefact 2 — Workload command

```bash
time python3 -m schemashift demo --approve
```

## Artefact 3 — Correctness result

```text
Migration complete: {'orders': 2, 'order_items': 3, 'products': 3, 'users': 3}
Verification passed: True
```

The important benchmark invariant is that every table has matching counts and canonical checksums, not merely that the process exits successfully.

## Artefact 4 — Interpretation

The sample is too small for meaningful throughput conclusions. The deterministic pipeline is designed to scale by replacing the JSON reader and SQLite writer with streaming MongoDB/PostgreSQL adapters while preserving the frozen-map, batch, retry, and verification interfaces. A production benchmark should report rows/sec, batch size, peak memory, transaction duration, and failed-row rate on a representative dataset.
