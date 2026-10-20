from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .io_utils import get_path, load_collections


def _schema_map(frozen: dict[str, Any]) -> dict[str, Any]:
    return frozen.get("schema", frozen)


def _converted(value: Any, column: dict[str, Any]) -> Any:
    if value is None:
        return None
    if column.get("json") or isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if column["sql_type"] == "INTEGER" and isinstance(value, bool):
        return int(value)
    return value


def _digest(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(sorted(rows, key=lambda row: json.dumps(row, sort_keys=True)), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def verify(source_dir: str | Path, db_path: str | Path, frozen: dict[str, Any]) -> dict[str, Any]:
    schema = _schema_map(frozen)
    collections = load_collections(source_dir)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    checks = []
    try:
        for entity in schema["collections"]:
            expected = []
            for document in collections[entity["collection"]]:
                expected.append({column["column"]: _converted(get_path(document, column["source"]), column) for column in entity["columns"]})
            names = [column["column"] for column in entity["columns"]]
            actual = [dict(row) for row in db.execute(f"SELECT {','.join(names)} FROM {entity['table']}")]
            check = {
                "table": entity["table"],
                "expected_count": len(expected),
                "actual_count": len(actual),
                "count_ok": len(expected) == len(actual),
                "checksum_ok": _digest(expected) == _digest(actual),
                "spot_checks": [{"expected": row, "actual": next((a for a in actual if a.get("id") == row.get("id")), None)} for row in expected[:2]],
            }
            check["ok"] = check["count_ok"] and check["checksum_ok"]
            checks.append(check)
            for child in entity.get("children", []):
                expected_child = []
                for document in collections[entity["collection"]]:
                    for item in get_path(document, child["array_field"]) or []:
                        if isinstance(item, dict):
                            row = {child["parent_fk"]["column"]: get_path(document, entity["id_field"])}
                            row.update({column["column"]: _converted(get_path(item, column["source"]), column) for column in child["columns"]})
                            expected_child.append(row)
                names = [child["parent_fk"]["column"]] + [column["column"] for column in child["columns"]]
                actual_child = [dict(row) for row in db.execute(f"SELECT {','.join(names)} FROM {child['table']}")]
                child_check = {
                    "table": child["table"],
                    "expected_count": len(expected_child),
                    "actual_count": len(actual_child),
                    "count_ok": len(expected_child) == len(actual_child),
                    "checksum_ok": _digest(expected_child) == _digest(actual_child),
                    "spot_checks": [{"expected": row} for row in expected_child[:2]],
                }
                child_check["ok"] = child_check["count_ok"] and child_check["checksum_ok"]
                checks.append(child_check)
    finally:
        db.close()
    return {"passed": all(item["ok"] for item in checks), "checks": checks}
