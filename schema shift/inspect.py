from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import load_collections


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _record(fields: dict[str, dict[str, Any]], path: str, value: Any) -> None:
    entry = fields.setdefault(path, {"type_counts": {}, "present": 0, "nulls": 0, "examples": []})
    kind = value_type(value)
    entry["type_counts"][kind] = entry["type_counts"].get(kind, 0) + 1
    entry["present"] += 1
    if value is None:
        entry["nulls"] += 1
    elif len(entry["examples"]) < 3 and kind not in {"object", "array"}:
        entry["examples"].append(value)


def _walk(fields: dict[str, dict[str, Any]], path: str, value: Any) -> None:
    _record(fields, path, value)
    if isinstance(value, dict):
        for key, child in sorted(value.items()):
            _walk(fields, f"{path}.{key}" if path else key, child)
    elif isinstance(value, list):
        for child in value:
            _walk(fields, f"{path}[]", child)


def inspect_source(source_dir: str | Path) -> dict[str, Any]:
    collections = load_collections(source_dir)
    report: dict[str, Any] = {
        "tool": "SchemaShift",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": "json-document-store",
        "source_directory": str(Path(source_dir)),
        "collections": {},
    }
    for name, documents in collections.items():
        fields: dict[str, dict[str, Any]] = {}
        for document in documents:
            for key, value in sorted(document.items()):
                _walk(fields, key, value)
        for entry in fields.values():
            entry["type"] = max(entry["type_counts"], key=entry["type_counts"].get)
        report["collections"][name] = {
            "document_count": len(documents),
            "fields": fields,
            "candidate_id": "_id" if any("_id" in d for d in documents) else "id",
        }
    return report
