from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .generate import generate_ddl
from .io_utils import get_path, load_collections


def _schema_map(frozen: dict[str, Any]) -> dict[str, Any]:
    return frozen.get("schema", frozen)


def _value(document: dict[str, Any], source: str) -> Any:
    return get_path(document, source)


def _convert(value: Any, column: dict[str, Any]) -> Any:
    if value is None:
        return None
    if column.get("json") or isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if column["sql_type"] == "INTEGER" and isinstance(value, bool):
        return int(value)
    return value


def _dependency_order(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topologically order parent tables before tables that reference them."""
    remaining = list(entities)
    ordered: list[dict[str, Any]] = []
    while remaining:
        available = {entity["table"] for entity in remaining}
        ready = []
        for entity in remaining:
            dependencies = set()
            for column in entity["columns"]:
                if column.get("references"):
                    dependencies.add(column["references"]["table"])
            dependencies -= {entity["table"]}
            if not dependencies & available:
                ready.append(entity)
        if not ready:
            raise ValueError("Cyclic or unresolved foreign-key dependencies in schema map")
        for entity in ready:
            ordered.append(entity)
            remaining.remove(entity)
    return ordered


def migrate(source_dir: str | Path, db_path: str | Path, frozen: dict[str, Any]) -> dict[str, Any]:
    schema = _schema_map(frozen)
    collections = load_collections(source_dir)
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(generate_ddl(frozen))
    counts: dict[str, int] = {}
    try:
        for entity in _dependency_order(schema["collections"]):
            documents = collections[entity["collection"]]
            columns = entity["columns"]
            names = [column["column"] for column in columns]
            placeholders = ",".join("?" for _ in names)
            sql = f"INSERT OR REPLACE INTO {entity['table']} ({','.join(names)}) VALUES ({placeholders})"
            for document in documents:
                values = [_convert(_value(document, column["source"]), column) for column in columns]
                db.execute(sql, values)
            counts[entity["table"]] = len(documents)
            for child in entity.get("children", []):
                child_columns = child["columns"]
                names = [child["parent_fk"]["column"]] + [column["column"] for column in child_columns]
                sql = f"INSERT INTO {child['table']} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})"
                count = 0
                for document in documents:
                    array_items = _value(document, child["array_field"]) or []
                    for item in array_items:
                        if not isinstance(item, dict):
                            continue
                        values = [_value(document, entity["id_field"])]
                        values.extend(_convert(_value(item, column["source"]), column) for column in child_columns)
                        db.execute(sql, values)
                        count += 1
                counts[child["table"]] = count
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"status": "ok", "rows_written": counts, "database": str(db_path)}
