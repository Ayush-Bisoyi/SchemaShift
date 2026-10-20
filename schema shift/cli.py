from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .assistant import generate_assist
from .freeze import freeze_schema
from .generate import generate_artifacts
from .infer import infer_schema
from .inspect import inspect_source
from .io_utils import read_json, write_json
from .migrate import migrate
from .reverse import (
    calculate_reverse_similarity,
    export_sqlite_to_documents,
    generate_reverse_artifacts,
    infer_document_model,
    inspect_sqlite,
    verify_reverse_export,
)
from .similarity import calculate_similarity
from .verify import verify
from .workflow import run_workflow


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "sample" / "source"
DEFAULT_ARTIFACTS = ROOT / "artifacts" / "sample"
DEFAULT_DB = DEFAULT_ARTIFACTS / "demo.sqlite"


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="schemashift", description="Hybrid NoSQL-to-SQL migration pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect", help="inspect JSON collections")
    p.add_argument("--source", default=str(DEFAULT_SOURCE)); p.add_argument("--out", required=True)
    p = sub.add_parser("infer", help="infer a candidate relational schema")
    p.add_argument("--inspection", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("similarity", help="calculate reproducible match percentages")
    p.add_argument("--inspection", required=True); p.add_argument("--proposal", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("assist", help="write advisory explanation; never performs database writes")
    p.add_argument("--proposal", required=True); p.add_argument("--similarity"); p.add_argument("--out", required=True)
    p = sub.add_parser("freeze", help="freeze a schema after the human gate")
    p.add_argument("--proposal", required=True); p.add_argument("--similarity", required=True); p.add_argument("--out", required=True); p.add_argument("--approve", action="store_true")
    p = sub.add_parser("generate", help="generate DDL, ETL documentation, rollback, and ORM")
    p.add_argument("--map", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("migrate", help="load source documents into SQLite")
    p.add_argument("--source", default=str(DEFAULT_SOURCE)); p.add_argument("--map", required=True); p.add_argument("--db", required=True)
    p = sub.add_parser("verify", help="verify counts, checksums, and spot checks")
    p.add_argument("--source", default=str(DEFAULT_SOURCE)); p.add_argument("--map", required=True); p.add_argument("--db", required=True)
    p = sub.add_parser("reverse-inspect", help="inspect a SQL database for reverse migration")
    p.add_argument("--db", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("reverse-infer", help="infer a document model from SQL tables")
    p.add_argument("--inspection", required=True); p.add_argument("--forward-map"); p.add_argument("--out", required=True)
    p = sub.add_parser("reverse-similarity", help="calculate SQL-to-document match percentages")
    p.add_argument("--inspection", required=True); p.add_argument("--model", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("reverse-freeze", help="freeze the reverse document model after approval")
    p.add_argument("--model", required=True); p.add_argument("--similarity", required=True); p.add_argument("--out", required=True); p.add_argument("--approve", action="store_true")
    p = sub.add_parser("reverse-generate", help="generate reverse loader, model, ORM, and rollback docs")
    p.add_argument("--map", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("reverse-export", help="export SQL rows as nested JSON documents")
    p.add_argument("--db", required=True); p.add_argument("--map", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("reverse-verify", help="verify reverse document counts and embedded child rows")
    p.add_argument("--db", required=True); p.add_argument("--map", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("demo", help="run the complete sample workflow")
    p.add_argument("--source", default=str(DEFAULT_SOURCE)); p.add_argument("--artifacts", default=str(DEFAULT_ARTIFACTS)); p.add_argument("--db", default=str(DEFAULT_DB)); p.add_argument("--approve", action="store_true")
    sub.add_parser("clean", help="remove generated sample artifacts")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            write_json(args.out, inspect_source(_path(args.source))); print(f"Wrote {args.out}")
        elif args.command == "infer":
            write_json(args.out, infer_schema(read_json(args.inspection))); print(f"Wrote {args.out}")
        elif args.command == "similarity":
            result = calculate_similarity(read_json(args.inspection), read_json(args.proposal)); write_json(args.out, result); print(f"Overall match: {result['overall_percent']:.2f}%")
        elif args.command == "assist":
            similarity = read_json(args.similarity) if args.similarity else None
            result = generate_assist(read_json(args.proposal), similarity); write_json(args.out, result); print(f"Assistant provider: {result['provider']}")
        elif args.command == "freeze":
            result = freeze_schema(read_json(args.proposal), read_json(args.similarity), args.approve); write_json(args.out, result); print(f"Frozen schema written to {args.out}")
        elif args.command == "generate":
            generate_artifacts(read_json(args.map), args.out); print(f"Generated artifacts in {args.out}")
        elif args.command == "migrate":
            print(migrate(_path(args.source), _path(args.db), read_json(args.map)))
        elif args.command == "verify":
            result = verify(_path(args.source), _path(args.db), read_json(args.map)); print(result); sys.exit(0 if result["passed"] else 1)
        elif args.command == "reverse-inspect":
            write_json(args.out, inspect_sqlite(_path(args.db))); print(f"Wrote {args.out}")
        elif args.command == "reverse-infer":
            forward = read_json(args.forward_map) if args.forward_map else None
            write_json(args.out, infer_document_model(read_json(args.inspection), forward)); print(f"Wrote {args.out}")
        elif args.command == "reverse-similarity":
            result = calculate_reverse_similarity(read_json(args.inspection), read_json(args.model)); write_json(args.out, result); print(f"Reverse match: {result['overall_percent']:.2f}%")
        elif args.command == "reverse-freeze":
            result = freeze_schema(read_json(args.model), read_json(args.similarity), args.approve); write_json(args.out, result); print(f"Frozen reverse map written to {args.out}")
        elif args.command == "reverse-generate":
            generate_reverse_artifacts(read_json(args.map), args.out); print(f"Generated reverse artifacts in {args.out}")
        elif args.command == "reverse-export":
            print(export_sqlite_to_documents(_path(args.db), read_json(args.map), _path(args.out)))
        elif args.command == "reverse-verify":
            result = verify_reverse_export(_path(args.db), read_json(args.map), _path(args.out)); write_json(_path(args.out) / "reverse_verification.json", result); print(result); sys.exit(0 if result["passed"] else 1)
        elif args.command == "demo":
            result = run_workflow(str(_path(args.source)), str(_path(args.artifacts)), str(_path(args.db)), args.approve)
            print(f"Migration complete: {result['migration']['rows_written']}")
            print(f"Verification passed: {result['verification']['passed']}")
        elif args.command == "clean":
            target = ROOT / "artifacts" / "sample"
            if target.exists(): shutil.rmtree(target)
            print(f"Removed {target}")
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
