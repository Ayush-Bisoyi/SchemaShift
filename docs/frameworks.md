# Framework execution guide

SchemaShift provides two actual orchestration paths.

## LangGraph

LangGraph is the recommended Python path. Install it with:

```bash
python3 -m pip install -r requirements-langgraph.txt
```

Run with automatic approval:

```bash
python3 -m schemashift.langgraph_app --approve
```

Run without `--approve` to use the actual LangGraph `interrupt()`. The graph pauses after the similarity report and asks you to type `APPROVE` before it freezes the schema or writes to SQLite.

The graph is:

```text
inspect → infer → similarity → approval interrupt → freeze
        → generate → migrate → verify
```

`InMemorySaver` checkpoints graph state for this local demo. LangGraph controls sequencing and pausing; deterministic SchemaShift functions still own SQL, migration, and verification. A production deployment should replace the in-memory checkpointer with a durable one.

Generated LangGraph artifacts are written to `artifacts/langgraph/`.

## n8n

Import `workflows/schemashift.n8n.json` into a self-hosted n8n instance. It uses built-in nodes:

* Execute Command for deterministic Python stages
* Wait for the human approval gate
* Code to read the approval value
* If to branch on approval
* Stop and Error for a safe rejection path

Set the n8n environment variable `SCHEMASHIFT_ROOT` to the absolute repository path before running. The Execute Command nodes then run this project’s CLI.

The Wait node resumes through its generated webhook URL. Send an approval value such as `approved=true`; the Code node converts it to a Boolean. Rejection stops the workflow before freezing or migrating.

This n8n workflow requires self-hosted n8n because Execute Command is not available on n8n Cloud; recent n8n versions also disable Execute Command by default because it can run shell commands on the n8n host. Enable it only in a trusted local environment. LangGraph is the easiest local framework path.

## Why both exist

LangGraph demonstrates Python-native agentic orchestration and a real interrupt. n8n demonstrates a visual workflow that a reviewer can import and inspect. Both call the same deterministic migration functions, so the orchestration layer cannot invent a different migration behavior.

## Reverse bonus workflows

The reverse LangGraph entry point is:

```bash
python3 -m schemashift.langgraph_reverse_app --approve
```

It inspects SQLite, infers a document model, calculates reverse similarity, pauses for approval, generates reverse artifacts, exports JSON collections, and verifies embedded child counts.

Import `workflows/schemashift_reverse.n8n.json` for the n8n equivalent. It assumes the forward demo has produced `artifacts/sample/demo.sqlite` and `artifacts/sample/schema_map.json`.
