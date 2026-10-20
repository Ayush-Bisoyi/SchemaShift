# Zero-downtime migration design

The included demo is an offline batch migration. A real application that must stay online should use expand/contract and dual writes:

1. **Expand:** create SQL tables and indexes without switching reads. Run deterministic schema verification.
2. **Backfill:** copy existing documents in stable primary-key batches. Record a checkpoint and retry failed rows.
3. **Dual write:** update the application so each new mutation is written to both stores. The deterministic adapter records an operation ID for idempotency.
4. **Shadow read:** compare a sample of NoSQL and SQL responses. The deterministic verifier decides whether values agree; an assistant may summarize drift.
5. **Cut over:** switch reads behind a feature flag. Keep the old source available for a defined rollback window.
6. **Rollback:** disable SQL reads, stop dual writes after draining in-flight operations, and use the frozen map plus operation log to diagnose divergence.
7. **Contract:** once verification and observation are complete, remove the old write path.

The cutover flag, batch checkpoints, idempotency keys, and verification result must remain deterministic. An agent may recommend whether the evidence looks safe, but it must not flip the cutover flag or delete the old database.
