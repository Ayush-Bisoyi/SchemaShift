"""Deterministic SQL-to-document migration support for the bonus feature."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .assistant import generate_assist
from .infer import snake_case, sql_type
from .io_utils import read_json, write_json


def inspect_sqlite(db_path: str | Path) -> dict[str, Any]:
    """Inspect SQLite tables, columns, indexes, and foreign keys deterministically."""
    db = sqlite3.connect(db_path)
    try:
        table_names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        tables = []
        for table in table_names:
            columns = []
            for row in db.execute(f"PRAGMA table_info({table})"):
                columns.append({
                    "name": row[1],
                    "type": row[2],
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "primary_key_position": row[5],
                })
            foreign_keys = []
            for row in db.execute(f"PRAGMA foreign_key_list({table})"):
                foreign_keys.append({"from": row[3], "to_table": row[2], "to": row[4], "on_delete": row[6]})
            indexes = []
            for row in db.execute(f"PRAGMA index_list({table})"):
                index_name = row[1]
                index_columns = [item[2] for item in db.execute(f"PRAGMA index_info({index_name})")]
                indexes.append({"name": index_name, "unique": bool(row[2]), "columns": index_columns})
            tables.append({"name": table, "columns": columns, "foreign_keys": foreign_keys, "indexes": indexes})
        return {"source_kind": "sqlite", "database": str(db_path), "tables": tables}
    finally:
        db.close()


def _forward_lookup(forward: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    root_lookup: dict[str, Any] = {}
    child_lookup: dict[str, Any] = {}
    if not forward:
        return root_lookup, child_lookup
    schema = forward.get("schema", forward)
    for entity in schema.get("collections", []):
        root_lookup[entity["table"]] = entity
        for child in entity.get("children", []):
            child_lookup[child["table"]] = (entity, child)
    return root_lookup, child_lookup


def infer_document_model(inspection: dict[str, Any], forward: dict[str, Any] | None = None) -> dict[str, Any]:
    """Infer a document model; use the forward map when available to preserve names."""
    root_lookup, child_lookup = _forward_lookup(forward)
    tables = {table["name"]: table for table in inspection["tables"]}
    child_tables = {table_name for table_name, table in tables.items() if table["foreign_keys"]}
    # A table is nested only when its name follows the parent_table_child convention.
    nested_tables = {
        table_name for table_name in child_tables
        if any(table_name.startswith((parent[:-1] if parent.endswith("s") else parent) + "_") for parent in tables if parent != table_name)
    }
    roots = [name for name in sorted(tables) if name not in nested_tables]
    collections = []
    for table_name in roots:
        table = tables[table_name]
        forward_entity = root_lookup.get(table_name)
        id_column = next((column["name"] for column in table["columns"] if column["primary_key_position"] == 1), "id")
        id_field = forward_entity.get("id_field", "_id") if forward_entity else "_id"
        fields = []
        if forward_entity:
            for column in forward_entity.get("columns", []):
                if column["column"] != id_column:
                    fields.append({"column": column["column"], "field": column["source"], "json": bool(column.get("json"))})
        else:
            for column in table["columns"]:
                if column["name"] != id_column:
                    fields.append({"column": column["name"], "field": column["name"], "json": column["type"].upper() == "JSON"})
        children = []
        for child_table_name, child_table in tables.items():
            if child_table_name not in nested_tables:
                continue
            forward_child = child_lookup.get(child_table_name)
            parent_fk = None
            if forward_child and forward_child[0]["table"] == table_name:
                parent_fk = forward_child[1]["parent_fk"]["column"]
            if not parent_fk:
                expected_prefix = (table_name[:-1] if table_name.endswith("s") else table_name) + "_"
                if not child_table_name.startswith(expected_prefix):
                    continue
                parent_fk = next((fk["from"] for fk in child_table["foreign_keys"] if fk["to_table"] == table_name), None)
            if not parent_fk:
                continue
            if forward_child:
                parent_entity, child_map = forward_child
                array_field = child_map["array_field"]
                child_fields = [{"column": column["column"], "field": column["source"], "json": bool(column.get("json"))} for column in child_map.get("columns", [])]
            else:
                array_field = child_table_name.removeprefix((table_name[:-1] if table_name.endswith("s") else table_name) + "_")
                child_fields = [
                    {"column": column["name"], "field": column["name"], "json": column["type"].upper() == "JSON"}
                    for column in child_table["columns"] if column["name"] not in {"id", parent_fk}
                ]
            children.append({"table": child_table_name, "array_field": array_field, "parent_fk": parent_fk, "fields": child_fields})
        collections.append({"collection": table_name, "table": table_name, "id_column": id_column, "id_field": id_field, "fields": fields, "children": children})
    model = {
        "direction": "sql-to-nosql",
        "source_kind": inspection.get("source_kind", "sqlite"),
        "strategy": {
            "root_tables": "tables not modeled as child tables become collections",
            "child_tables": "tables named parent_child are embedded as arrays",
            "foreign_keys": "preserved as ID fields inside documents",
            "json_columns": "decoded back into JSON values",
        },
        "collections": collections,
    }
    model["assistant"] = generate_assist({"collections": collections, "strategy": model["strategy"]})
    return model


def _reverse_score(field: str, column: str) -> tuple[float, dict[str, float]]:
    expected = snake_case(field.replace(".", "_"))
    if field == "_id" and column == "id":
        name = 1.0
    else:
        name = SequenceMatcher(None, expected, column).ratio()
    tokens_a, tokens_b = set(expected.split("_")), set(column.split("_"))
    token = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
    score = round(0.75 * name + 0.25 * token, 4)
    return score, {"name": round(name, 4), "token": round(token, 4)}


def calculate_reverse_similarity(inspection: dict[str, Any], model: dict[str, Any], threshold: float = 0.65) -> dict[str, Any]:
    table_map = {table["name"]: table for table in inspection["tables"]}
    entities, all_scores = [], []
    for entity in model["collections"]:
        table = table_map[entity["table"]]
        fields = [{"source": entity["id_field"], "target": f"{entity['table']}.{entity['id_column']}", "score": 1.0, "percent": 100.0, "classification": "matched", "components": {"name": 1.0, "token": 1.0}}]
        for field in entity["fields"]:
            score, components = _reverse_score(field["field"], field["column"])
            classification = "matched" if score >= 0.85 else ("guessed" if score >= threshold else "needs_review")
            fields.append({"source": field["field"], "target": f"{entity['table']}.{field['column']}", "score": score, "percent": round(score * 100, 2), "classification": classification, "components": components})
            all_scores.append(score)
        entities.append({"source_table": entity["table"], "target_collection": entity["collection"], "percent": round(sum(item["score"] for item in fields) / len(fields) * 100, 2), "fields": fields})
    overall = sum(all_scores) / max(1, len(all_scores)) * 100
    return {
        "direction": "sql-to-nosql",
        "algorithm": "0.75 normalized name + 0.25 token overlap",
        "threshold": threshold,
        "overall_percent": round(overall, 2),
        "entities": entities,
        "needs_review": [field for entity in entities for field in entity["fields"] if field["classification"] == "needs_review"],
        "deterministic": True,
    }


def _set_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = document
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _decode(value: Any, is_json: bool) -> Any:
    if not is_json or value is None:
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def export_sqlite_to_documents(db_path: str | Path, frozen: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    model = frozen.get("schema", frozen)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    counts = {}
    try:
        for entity in model["collections"]:
            documents = []
            for row in db.execute(f"SELECT * FROM {entity['table']}"):
                document: dict[str, Any] = {}
                _set_path(document, entity["id_field"], row[entity["id_column"]])
                for field in entity["fields"]:
                    _set_path(document, field["field"], _decode(row[field["column"]], field.get("json", False)))
                for child in entity.get("children", []):
                    items = []
                    child_rows = db.execute(
                        f"SELECT * FROM {child['table']} WHERE {child['parent_fk']} = ?",
                        (row[entity["id_column"]],),
                    )
                    for child_row in child_rows:
                        item = {}
                        for field in child["fields"]:
                            _set_path(item, field["field"], _decode(child_row[field["column"]], field.get("json", False)))
                        items.append(item)
                    _set_path(document, child["array_field"], items)
                documents.append(document)
            target = output / f"{entity['collection']}.json"
            target.write_text(json.dumps(documents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            counts[entity["collection"]] = len(documents)
    finally:
        db.close()
    return {"status": "ok", "documents_written": counts, "output_directory": str(output)}


def verify_reverse_export(db_path: str | Path, frozen: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    model = frozen.get("schema", frozen)
    checks = []
    db = sqlite3.connect(db_path)
    try:
        for entity in model["collections"]:
            expected = db.execute(f"SELECT COUNT(*) FROM {entity['table']}").fetchone()[0]
            actual = len(json.loads((Path(output_dir) / f"{entity['collection']}.json").read_text(encoding="utf-8")))
            checks.append({"collection": entity["collection"], "source_rows": expected, "documents": actual, "ok": expected == actual})
            for child in entity.get("children", []):
                expected_child = db.execute(f"SELECT COUNT(*) FROM {child['table']}").fetchone()[0]
                documents = json.loads((Path(output_dir) / f"{entity['collection']}.json").read_text(encoding="utf-8"))
                actual_child = sum(len(document.get(child["array_field"], [])) for document in documents)
                checks.append({"table": child["table"], "source_rows": expected_child, "embedded_items": actual_child, "ok": expected_child == actual_child})
    finally:
        db.close()
    return {"direction": "sql-to-nosql", "passed": all(check["ok"] for check in checks), "checks": checks}


def generate_reverse_artifacts(frozen: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "document_model.json", frozen)
    loader = '''"""Generated SQL-to-document export script."""
import argparse
from schemashift.io_utils import read_json
from schemashift.reverse import export_sqlite_to_documents

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--map", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()
print(export_sqlite_to_documents(args.db, read_json(args.map), args.out))
'''
    orm = '''"""Generated reverse data-access helper."""
import json
import sqlite3

class SqliteDocumentRepository:
    def __init__(self, database):
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row

    def rows(self, table):
        return [dict(row) for row in self.connection.execute(f"SELECT * FROM {table}")]

    def close(self):
        self.connection.close()
'''
    rollback = """# SQL-to-NoSQL rollback\n\nThe SQL source is preserved. To roll back, remove only the generated JSON output directory after checking its path. No source SQL rows are deleted by the reverse exporter.\n"""
    (output / "sql_to_nosql.py").write_text(loader, encoding="utf-8")
    (output / "reverse_orm.py").write_text(orm, encoding="utf-8")
    (output / "rollback.md").write_text(rollback, encoding="utf-8")
    return {"document_model.json": str(output / "document_model.json"), "sql_to_nosql.py": str(output / "sql_to_nosql.py"), "reverse_orm.py": str(output / "reverse_orm.py"), "rollback.md": str(output / "rollback.md")}
