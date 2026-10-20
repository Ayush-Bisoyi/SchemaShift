# SchemaShift

## Submission overview

SchemaShift is a deterministic-first hybrid migration tool for converting document-style NoSQL data into a relational SQL database.

This submission includes:

- NoSQL/document-style JSON to SQL migration
- SQL to NoSQL reconstruction as the bidirectional bonus
- deterministic schema inspection and inference
- reproducible source-to-target similarity scoring
- human approval before data-changing operations
- frozen schema maps
- generated DDL, ETL, rollback, ORM, and Prisma artifacts
- foreign-key-aware migration ordering
- deterministic verification using counts, checksums, and spot checks
- real LangGraph orchestration with checkpointing and approval interrupts
- importable n8n workflows
- automated tests and reproducible sample artifacts

The demonstration uses JSON collections as the document source and SQLite as the relational target. This keeps the project self-contained and runnable without a database server while preserving the same design principles required for MongoDB-to-PostgreSQL migration.

Challenge reference: [SchemaShift recruitment challenge](https://github.com/WebClub-NITK/GDGxIris-Recruitments-2026/blob/main/Challenges/SchemaShift.md)

---

## Core design principle

The implementation follows the required hybrid rule:

> Deterministic code owns schema decisions that affect data, generated scripts, database writes, and verification. The optional assistant may suggest, rank, or explain, but it never performs database side effects or decides whether verification passed.

This prevents an unpredictable model response from silently changing a migration.

| Pipeline layer | Deterministic implementation | Assistant role | Safety boundary |
|---|---|---|---|
| Inspect and infer | Structural traversal, type counts, naming rules, and candidate schema generation | Explain naming and embed-versus-table choices | Proposal is saved and reviewed before freezing |
| Similarity | Normalization, token overlap, SequenceMatcher, type compatibility, and percentages | Explain ambiguous mappings | Low-confidence mappings enter needs_review |
| Approval | Frozen-map creation and SHA-256 identity | Summarize risks | Migration cannot proceed without approval |
| Script generation | DDL, indexes, ETL loader, rollback, ORM, and Prisma output | Add comments and risk notes | Artifacts come only from the frozen map |
| Migration | Type conversion, parent-before-child loading, parameterized SQL, and transactions | Diagnose failures | Assistant cannot modify mappings or rows |
| Verification | Counts, canonical checksums, and spot checks | Explain drift | Pass/fail is calculated by Python |
| Orchestration | Explicit graph nodes, artifact paths, gates, and failure propagation | Optional explanation nodes | LangGraph and n8n call the same deterministic core |

---

## Architecture

Forward migration:

~~~text
Document collections
        |
        v
Inspect source
        |
        v
Infer candidate relational schema
        |
        v
Calculate deterministic similarity scores
        |
        v
Human approval gate
        |
        v
Freeze schema map
        |
        +--> Generate DDL, ETL, rollback, ORM, and Prisma artifacts
        |
        +--> Migrate data into SQL
        |
        v
Verify counts, checksums, and spot checks
~~~

Reverse bonus:

~~~text
SQL database
        |
        v
Inspect tables, columns, foreign keys, and indexes
        |
        v
Infer document collections and nested arrays
        |
        v
Calculate reverse similarity scores
        |
        v
Human approval gate
        |
        v
Freeze reverse schema map
        |
        +--> Generate reverse exporter and ORM artifacts
        |
        +--> Export nested JSON documents
        |
        v
Verify root documents and embedded child counts
~~~

The plain Python workflow, LangGraph workflow, and n8n workflow all reuse the same deterministic migration functions.

---

## Repository structure

~~~text
sample/source/                 Sample users, products, and orders collections
schemashift/                   Python implementation of every pipeline stage
artifacts/sample/              Reports, generated scripts, database, and evidence
workflows/                     Forward and reverse n8n workflow exports
tests/                         Forward, reverse, and optional LangGraph tests
docs/                          Framework, failure, and zero-downtime documentation
README.md                      Submission overview and reproducibility guide
CODE_WALKTHROUGH.md            Beginner-friendly file-by-file explanation
DESIGN.md                      Architectural decisions and alternatives
LEARNING_GUIDE.md              Concepts and learning notes
BENCH.md                       Reproducible benchmark notes
~~~

Important implementation modules include:

- inspect.py for source traversal and type statistics
- infer.py for relational schema inference
- similarity.py for deterministic mapping percentages
- freeze.py for approval and schema-map freezing
- generate.py for DDL, ETL, rollback, ORM, and Prisma generation
- migrate.py for transactional SQL loading
- verify.py for deterministic verification
- reverse.py for SQL-to-NoSQL reconstruction
- langgraph_app.py for forward LangGraph orchestration
- langgraph_reverse_app.py for reverse LangGraph orchestration

---

## Forward migration: NoSQL to SQL

The sample contains users, products, and orders. It demonstrates:

- nested objects such as address
- primitive arrays such as tags
- arrays of objects such as orders.items
- primary keys and foreign keys
- nullable fields and indexes
- deterministic field matching

The inference rules are:

- _id becomes the SQL id primary key.
- Simple nested objects are flattened one level, such as address.city to address_city.
- Primitive arrays remain canonical JSON text in a TEXT column.
- Arrays of objects become child tables.
- orders.items becomes order_items.
- Child rows receive a parent foreign key such as order_id.
- ID-like fields are linked to matching tables when possible.
- Parent tables are loaded before child tables.

The migration uses parameterized SQLite statements, enables foreign keys, and performs writes inside a transaction. If an exception occurs, the transaction is rolled back.

---

## Deterministic similarity scoring

The source-to-target match percentage is calculated entirely by Python:

~~~text
55% normalized name similarity
+ 25% token overlap
+ 20% source/target type compatibility
~~~

The report contains field-level, entity-level, and overall percentages, along with matched, guessed, and needs_review classifications.

The sample mapping produces an overall score of 100.00% because the sample schema is intentionally clear. The score is reproducible for the same inspection and proposal. The assistant can explain a low-confidence mapping, but it cannot change the score.

---

## Human approval and frozen schema maps

The approval gate is implemented in freeze.py.

If low-confidence mappings exist and approval has not been provided, freezing fails. Once approved, the system stores:

- the approved schema
- the similarity report
- the approval decision
- the freeze timestamp
- a SHA-256 hash of the proposal

All downstream stages consume this frozen map. They do not silently re-infer the schema. This makes generated scripts and migration results auditable and reproducible.

---

## Generated artifacts

The forward generator produces:

~~~text
schema.sql                  SQLite DDL, keys, foreign keys, and indexes
rollback.sql                Dependency-safe cleanup script
load.py                     Generated ETL entry point
generated_orm.py            Generated Python data-access layer
schema.prisma               Prisma-style relational model
schema_map.json             Frozen mapping used to generate the artifacts
~~~

The generated files are derived from the schema map rather than from free-form assistant output.

---

## Verification

Verification is deterministic and independent of the assistant.

For every mapped entity, the verifier checks:

- source document count against target row count
- transformed source values against target values
- canonical row checksums
- selected root-field spot checks
- child-table row counts

Rows are normalized, sorted, serialized canonically, and hashed with SHA-256 so harmless row-order differences do not create false failures. The result contains individual checks and an overall passed value.

---

## SQL-to-NoSQL bidirectional bonus

The reverse implementation is in reverse.py. It:

1. inspects SQLite metadata using sqlite_master, PRAGMA table_info, and PRAGMA foreign_key_list;
2. identifies root and child tables;
3. infers document collections and nested arrays;
4. optionally uses the forward frozen map to recover original source field names;
5. calculates deterministic reverse similarity scores;
6. pauses for human approval;
7. freezes a reverse schema map;
8. generates reverse exporter and ORM artifacts;
9. exports SQL rows into nested JSON documents; and
10. verifies root documents and embedded child counts.

For example, orders and order_items can be reconstructed as documents containing nested items arrays. The reverse path follows the same hybrid rule: deterministic Python owns model creation, export, and verification, while the assistant remains advisory.

---

## LangGraph orchestration

The repository includes an actual LangGraph implementation.

Forward graph:

~~~text
inspect -> infer -> similarity -> approval -> freeze
        -> generate -> migrate -> verify
~~~

Reverse graph:

~~~text
inspect -> infer -> similarity -> approval -> freeze
        -> generate -> export -> verify
~~~

LangGraph provides typed shared state, explicit nodes and edges, in-memory checkpointing for the demonstration, a real interrupt approval point, and resume support using a thread ID and Command.

The deterministic pipeline functions remain separate from LangGraph, so the same logic can be tested without the framework.

~~~bash
python3 -m pip install -r requirements-langgraph.txt
python3 -m schemashift.langgraph_app --approve
python3 -m schemashift.langgraph_reverse_app --approve
~~~

Without the approve flag, the graphs pause before migration or export and require a human decision.

---

## n8n orchestration

The repository includes:

- workflows/schemashift.n8n.json
- workflows/schemashift_reverse.n8n.json

The workflows use Execute Command, Wait, Code, If, and Stop and Error nodes.

n8n acts as the conductor. Python remains responsible for schema decisions, database writes, exports, and verification. The workflows are intended for trusted local or self-hosted n8n installations and use the SCHEMASHIFT_ROOT environment variable to locate the repository.

The LangGraph path is the simplest local demonstration because it does not require a separate n8n service.

---

## Optional assistant

The project runs offline by default with a deterministic heuristic explanation layer.

An optional OpenAI-backed explanation layer can be enabled with:

~~~bash
python3 -m pip install -r requirements-optional.txt
export OPENAI_API_KEY="your-key"
export SCHEMASHIFT_LLM=1
python3 -m schemashift demo --approve
~~~

The assistant receives reports and returns explanations or risk notes. It cannot execute migration SQL, change the frozen map, write database rows, mark verification as passed, or bypass approval. If the optional API is unavailable, the project falls back to the offline explanation layer.

---

## Reproducing the demonstration

Requirements:

- Python 3.10 or newer
- no external database server for the sample
- optional LangGraph installation for the graph test
- optional n8n installation for the visual workflow

Run the complete deterministic sample:

~~~bash
python3 -m unittest discover -s tests -v
python3 -m schemashift demo --approve
~~~

Expected result:

~~~text
Migration complete: {'orders': 2, 'order_items': 3, 'products': 3, 'users': 3}
Verification passed: True
~~~

The evidence is stored under artifacts/sample/:

~~~text
inspection.json
proposal.json
similarity.json
schema_map.json
generated/schema.sql
generated/rollback.sql
generated/load.py
generated/generated_orm.py
generated/schema.prisma
verification.json
workflow_run.json
reverse_inspection.json
reverse_model.json
reverse_similarity.json
reverse_schema_map.json
reverse_documents/
reverse_generated/
reverse_verification.json
~~~

The reverse CLI stages are available as reverse-inspect, reverse-infer, reverse-similarity, reverse-freeze, reverse-generate, reverse-export, and reverse-verify. They are documented in the source CLI and learning guide.

---

## Test coverage

The test suite covers:

- reproducible forward inference and migration
- foreign-key and generated-DDL structure
- ORM CRUD shape
- SQL-to-NoSQL reconstruction
- nested child-array export
- reverse verification
- the real LangGraph path when the optional dependency is installed

The standard-library tests run without a database server. The LangGraph test is skipped only when LangGraph is not installed.

---

## Design decisions and limitations

The implementation intentionally uses JSON files and SQLite for a portable demonstration. In a production deployment, the same deterministic core could be connected to MongoDB and PostgreSQL adapters.

The sample does not claim to be a complete production zero-downtime system. A design for expand, backfill, dual-write, verification, cutover, and rollback is documented in docs/zero-downtime.md.

Possible production extensions include:

- MongoDB and PostgreSQL connectors
- bulk loading for large datasets
- richer policies for mixed field types
- encrypted secret management
- persistent LangGraph checkpoint storage
- change-data-capture or dual-write support
- operational metrics and alerting
- stronger schema compatibility checks
- resumable migration batches

Implementation decisions, rejected alternatives, benchmark notes, and failure analysis are documented in DESIGN.md, BENCH.md, and docs/failure-log.md.

---

## Evaluation guide

The most relevant files for review are:

- README.md for the submission overview and reproducibility
- DESIGN.md for architectural decisions
- CODE_WALKTHROUGH.md for a file-by-file explanation
- schemashift/ for the implementation
- tests/ for executable correctness checks
- artifacts/sample/ for generated evidence
- workflows/ for LangGraph-compatible and n8n orchestration paths

The central implementation claim is that the assistant is advisory while deterministic code owns the migration contract and every data-changing operation.

