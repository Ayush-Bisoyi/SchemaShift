# SchemaShift design log

These entries record decisions made while implementing the sample. Each entry includes the rejected alternative and the evidence or reasoning used.

## 2026-10-16 — Use a JSON document adapter for the source

I chose JSON files as a small document-store adapter. I rejected requiring a running MongoDB server because the challenge asks for a thin sample and a reviewer should be able to run it without credentials or network access. The adapter preserves document-store behavior: collections, nested objects, and arrays remain visible to inference.

## 2026-10-16 — Use SQLite for the target

I chose SQLite for the executable demonstration. I rejected requiring PostgreSQL because a beginner should be able to reproduce the full migration with one command. The generated SQL is intentionally ordinary relational SQL, and the mapping can later be pointed at PostgreSQL by changing the dialect/connection adapter.

## 2026-10-16 — Deterministic inference owns the candidate map

The inference stage uses structural field statistics and explicit rules. I rejected letting an LLM directly write the schema because a small prompt or model-version change could silently change production DDL. The proposal is a JSON artifact, so it can be reviewed and diffed.

## 2026-10-16 — Flatten one level of nested objects

`address.city` becomes `address_city`. I rejected storing every nested object as opaque JSON because common query fields would become difficult to index. One-level flattening keeps the sample understandable while documenting a clear boundary for deeper structures.

## 2026-10-16 — Separate arrays of objects into child tables

`orders.items` becomes `order_items` with `order_id`. I rejected serializing the whole array because item-level queries and referential integrity would be lost. Primitive arrays such as `users.tags` remain JSON because they do not need their own identity for this sample.

## 2026-10-16 — Score before asking for explanations

Similarity is calculated from normalized names, token overlap, and type compatibility. I rejected using an LLM-provided percentage because the number would not be reproducible. The assistant only explains scores and highlights ambiguous fields after the deterministic calculation.

## 2026-10-16 — Freeze before side effects

DDL generation, migration, and verification consume only `schema_map.json`. I rejected allowing each later stage to reinterpret the proposal because that could make the generated DDL and loader disagree. Low-confidence mappings require an explicit human approval flag.

## 2026-10-16 — Verify transformed rows, not only counts

Verification compares counts, canonical row checksums, and sample rows. I rejected count-only verification because a loader can insert the right number of wrong rows. The checksum excludes generated child IDs and compares the meaningful mapped columns.

## 2026-10-16 — Keep an offline assistant fallback

The default assistant is an offline heuristic explainer; OpenAI is optional. I rejected making network access a prerequisite because schema inspection, script generation, and migration must remain available and deterministic in a restricted environment. The optional path is still non-deterministic and is explicitly marked as advisory.

## 2026-10-17 — Implement the bidirectional bonus from the same frozen contract

The reverse path inspects SQL metadata and reconstructs document collections. When the forward schema map is available, it preserves original field paths such as `address.city` and `orders.items`; otherwise it uses deterministic table/column naming rules. I rejected writing a completely separate reverse mapper because that would duplicate relationship knowledge and make round trips inconsistent. Reverse export has its own similarity report, approval gate, generated artifacts, and verification.
