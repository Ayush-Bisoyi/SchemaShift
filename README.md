# SchemaShift

SchemaShift is a deterministic-first hybrid developer tool for migrating a document-style NoSQL data source into a relational SQL database. It was built for the [SchemaShift recruitment challenge](https://github.com/WebClub-NITK/GDGxIris-Recruitments-2026/blob/main/Challenges/SchemaShift.md).

The sample is intentionally small but exercises the important cases: nested objects (`address`, `metadata`), primitive arrays (`tags`), arrays of objects (`orders.items`), primary keys, foreign keys, indexes, deterministic matching, generated SQL, rollback, ETL, ORM/data-access code, and verification.

## What is included

```text
sample/source/                 JSON document collections: users, products, orders
schemashift/                   Python implementation of every pipeline stage
artifacts/sample/              Reproducible reports and generated migration files
workflows/schemashift.n8n.json Importable n8n workflow export
workflows/schemashift_reverse.n8n.json Importable reverse n8n workflow
schemashift/langgraph_app.py     Real LangGraph graph with approval interrupt
schemashift/langgraph_reverse_app.py Real reverse LangGraph graph
tests/test_pipeline.py         End-to-end tests
DESIGN.md                      Dated decisions and rejected alternatives
BENCH.md                       Reproducible benchmark notes
docs/                          Zero-downtime design and failure log
```

## Hybrid rule and safety model

The core safety principle is: deterministic code owns truth and side effects; optional assistant code may suggest, rank, or explain but can never write production data.

| Layer | Deterministic part | Non-deterministic assist | Why / gate / match percentage |
|---|---|---|---|
| Inspect / infer | Structural sampling, type counts, naming rules, candidate schema | Optional OpenAI explanation of names, relations, and embed-vs-table choices | A candidate is saved as JSON and must be reviewed before freezing. |
| Similarity | Normalization, token overlap, `SequenceMatcher`, type compatibility, reproducible percentages | Optional explanation of ambiguous mappings | Low scores are listed in `needs_review`; the human gate blocks freeze unless `--approve` is supplied. |
| Script generation | DDL, indexes, ETL loader, rollback, Python repository, and Prisma schema from the frozen map | Comments and risk notes | Production scripts are generated from one immutable map, never from free-form LLM text. |
| Data migration | Typed transforms, FK order, transactions, retries can be added around the deterministic loader, verification | Optional diagnosis and explanation of a failed run | Failed writes roll back; the assistant cannot modify mappings automatically. |
| Verify / rollback | Counts, canonical checksums, spot checks, and rollback SQL | Human-readable drift summary | Pass/fail is calculated by code. A failed check is never hidden by an assistant. |
| ORM / application layer | Generated Python SQLite repository and `schema.prisma` | Suggested query idioms and manual-review notes | Generated code is reviewable and regenerated only after a new freeze. |
| Orchestration | Explicit graph nodes, artifact paths, gate, and failure propagation | Assist/explain nodes | `workflow_run.json` records every node as deterministic or assistive; n8n export is in `workflows/`. |

### Match percentage

The deterministic score is:

```text
55% normalized name similarity
+ 25% token overlap
+ 20% source/target type compatibility
```

The sample produces an overall match of `100.00%` because its frozen mapping is intentionally clear. Real data with ambiguous names will produce `guessed` and `needs_review` entries. The report contains an overall percentage, per-entity percentage, and per-field percentage.

## Quick start

You need Python 3.10 or newer. No database server is required for the local demonstration.

```bash
python3 --version
python3 -m unittest discover -s tests -v
python3 -m schemashift demo --approve
```

Expected summary:

```text
Migration complete: {'orders': 2, 'order_items': 3, 'products': 3, 'users': 3}
Verification passed: True
```

The generated files will be in `artifacts/sample/`:

```text
inspection.json                 source structure and type statistics
proposal.json                   candidate tables and columns plus assistant notes
similarity.json                 reproducible match percentages and review list
schema_map.json                 frozen map consumed by all downstream stages
generated/schema.sql            SQLite DDL and indexes
generated/rollback.sql          cleanup script in dependency-safe order
generated/load.py               generated ETL entry point
generated/generated_orm.py      generated Python data-access layer
generated/schema.prisma         optional Prisma-compatible model output
verification.json               counts, checksums, and spot checks
workflow_run.json               node-by-node execution record
```

## Run each stage manually

This is useful when explaining the project in an interview:

```bash
python3 -m schemashift inspect \
  --source sample/source --out artifacts/manual/inspection.json

python3 -m schemashift infer \
  --inspection artifacts/manual/inspection.json \
  --out artifacts/manual/proposal.json

python3 -m schemashift similarity \
  --inspection artifacts/manual/inspection.json \
  --proposal artifacts/manual/proposal.json \
  --out artifacts/manual/similarity.json

python3 -m schemashift freeze \
  --proposal artifacts/manual/proposal.json \
  --similarity artifacts/manual/similarity.json \
  --out artifacts/manual/schema_map.json --approve

python3 -m schemashift generate \
  --map artifacts/manual/schema_map.json \
  --out artifacts/manual/generated

python3 -m schemashift migrate \
  --source sample/source --map artifacts/manual/schema_map.json \
  --db artifacts/manual/demo.sqlite

python3 -m schemashift verify \
  --source sample/source --map artifacts/manual/schema_map.json \
  --db artifacts/manual/demo.sqlite
```

## How the mapping works

* Each JSON file is treated as one source collection.
* `_id` becomes the SQL `id` primary key.
* Nested objects are flattened one level: `address.city` becomes `address_city`.
* Arrays of primitive values stay as canonical JSON text: `tags` becomes a `TEXT` column.
* Arrays of objects become child tables: `orders.items` becomes `order_items`, with `order_id` as a foreign key.
* ID-like fields become foreign keys when a matching target table exists: `orders.user_id → users.id` and `order_items.product_id → products.id`.
* Foreign-key parents are loaded before child rows, all writes happen in one SQLite transaction, and any exception rolls the transaction back.
* Verification creates the same transformed rows in memory, sorts them canonically, hashes them with SHA-256, and compares the result with the target database.

## Optional LLM assistant

The project works offline with a safe heuristic explainer. To enable optional OpenAI explanations, install the optional dependency and set the environment variables below:

```bash
python3 -m pip install -r requirements-optional.txt
export OPENAI_API_KEY="your-key"
export SCHEMASHIFT_LLM=1
python3 -m schemashift demo --approve
```

The assistant receives reports and proposes explanations only. It cannot call the migration writer, change `schema_map.json`, execute SQL, or mark verification as passed. If the API fails, SchemaShift records the error and falls back to the offline explanation.

The sample settings are also recorded in [`config/sample.json`](config/sample.json), so source and target locations are easy to move out of the command line when adapting the project.

## LangGraph and n8n workflow paths

The project includes both requested orchestration technologies.

### LangGraph

Install and run the actual Python graph:

```bash
python3 -m pip install -r requirements-langgraph.txt
python3 -m schemashift.langgraph_app --approve
```

Without `--approve`, the graph pauses at a real LangGraph `interrupt()` and asks for human approval before any database side effect. It uses `InMemorySaver` checkpointing for the demo and connects: inspect → infer → similarity → approval → freeze → generate → migrate → verify.

### n8n

Import `workflows/schemashift.n8n.json` into self-hosted n8n. It uses built-in Execute Command, Wait, Code, If, and Stop and Error nodes. Set `SCHEMASHIFT_ROOT` to this repository’s absolute path before executing it. The Wait node provides the approval pause; rejected approval stops before migration. Execute Command is not available on n8n Cloud and is disabled by default in recent self-hosted n8n versions, so enable it only in a trusted local environment. The LangGraph path is the easiest local demonstration.

Detailed setup is in [`docs/frameworks.md`](docs/frameworks.md). Both frameworks call the same deterministic migration functions, keeping orchestration separate from production data side effects.

## Bonus: SQL → NoSQL bidirectional migration

The optional reverse direction is fully implemented in the separate reverse modules. It follows the same hybrid rule:

| Reverse layer | Deterministic ownership | Assistant ownership | Gate |
|---|---|---|---|
| Inspect / infer | Inspect SQLite tables, columns, foreign keys, indexes; infer root collections and embedded child arrays | Explain table-to-document choices | Review `reverse_model.json` |
| Similarity | Normalize field names and calculate reproducible percentages | Explain low-confidence mappings | Low scores go to `needs_review` |
| Generate | Generate document model, exporter, reverse ORM helper, and rollback instructions | Risk notes and narrative | Generate only from frozen reverse map |
| Export | Read SQL rows, decode JSON columns, nest child rows, write JSON collections | Diagnose failures | Human approval before export |
| Verify | Compare SQL row counts with exported documents and embedded child counts | Summarize drift | Pass/fail remains deterministic |
| Orchestration | LangGraph interrupt and n8n Wait/If gate | Optional assist node | Rejection stops before export |

Run the reverse path after the normal demo has created `artifacts/sample/demo.sqlite`:

```bash
python3 -m schemashift reverse-inspect \
  --db artifacts/sample/demo.sqlite \
  --out artifacts/sample/reverse_inspection.json

python3 -m schemashift reverse-infer \
  --inspection artifacts/sample/reverse_inspection.json \
  --forward-map artifacts/sample/schema_map.json \
  --out artifacts/sample/reverse_model.json

python3 -m schemashift reverse-similarity \
  --inspection artifacts/sample/reverse_inspection.json \
  --model artifacts/sample/reverse_model.json \
  --out artifacts/sample/reverse_similarity.json

python3 -m schemashift reverse-freeze \
  --model artifacts/sample/reverse_model.json \
  --similarity artifacts/sample/reverse_similarity.json \
  --out artifacts/sample/reverse_schema_map.json --approve

python3 -m schemashift reverse-generate \
  --map artifacts/sample/reverse_schema_map.json \
  --out artifacts/sample/reverse_generated

python3 -m schemashift reverse-export \
  --db artifacts/sample/demo.sqlite \
  --map artifacts/sample/reverse_schema_map.json \
  --out artifacts/sample/reverse_documents

python3 -m schemashift reverse-verify \
  --db artifacts/sample/demo.sqlite \
  --map artifacts/sample/reverse_schema_map.json \
  --out artifacts/sample/reverse_documents
```

The result reconstructs documents such as `orders.json`, including nested `items` arrays and the original source field names when the forward map is supplied. Reverse artifacts include `document_model.json`, `sql_to_nosql.py`, `reverse_orm.py`, and `rollback.md`.

Run the actual reverse LangGraph graph with:

```bash
python3 -m schemashift.langgraph_reverse_app --approve
```

The second n8n export, `workflows/schemashift_reverse.n8n.json`, runs the same reverse stages with an advisory assistant node and an approval Wait node.

## Failure handling

Two bugs found during implementation and their fixes are documented in [`docs/failure-log.md`](docs/failure-log.md). Keeping this record is important: migration tools must make failures visible rather than silently producing a partial database.

## Bonus design

The zero-downtime strategy, including expand/backfill/dual-write/verify/cutover/rollback phases, is documented in [`docs/zero-downtime.md`](docs/zero-downtime.md). The local sample intentionally does not pretend that a single-process demo is production zero-downtime.

## Submission checklist

1. Create a private GitHub repository.
2. Copy all files from this project into it.
3. Run the tests and demo; keep the generated JSON reports as evidence.
4. Read and understand `DESIGN.md`, `README.md`, and the generated SQL before the interview.
5. Commit incrementally with messages such as `add deterministic inspection`, `add migration verification`, and `document hybrid workflow`.
6. Add the recruitment mentors as collaborators and keep the repository private until instructed otherwise.

## References

* [SchemaShift challenge](https://github.com/WebClub-NITK/GDGxIris-Recruitments-2026/blob/main/Challenges/SchemaShift.md)
* [PostgreSQL data modeling documentation](https://www.postgresql.org/docs/current/ddl.html)
* [MongoDB data modeling patterns](https://www.mongodb.com/docs/manual/data-modeling/)
* [Prisma schema reference](https://www.prisma.io/docs/orm/prisma-schema)
* [n8n documentation](https://docs.n8n.io/)
