from __future__ import annotations

import re
from typing import Any

from .assistant import generate_assist


def snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value or "value"


def sql_type(kind: str) -> str:
    return {
        "integer": "INTEGER",
        "number": "REAL",
        "boolean": "INTEGER",
        "string": "TEXT",
        "null": "TEXT",
        "object": "TEXT",
        "array": "TEXT",
    }.get(kind, "TEXT")


def _field_type(entry: dict[str, Any]) -> str:
    kinds = entry.get("type_counts", {})
    non_null = [kind for kind in kinds if kind != "null"]
    return non_null[0] if len(non_null) == 1 else (entry.get("type") or "string")


def infer_schema(inspection: dict[str, Any]) -> dict[str, Any]:
    collections = []
    for name, info in sorted(inspection["collections"].items()):
        table = snake_case(name)
        id_field = info.get("candidate_id", "id")
        columns = [{"source": id_field, "column": "id", "sql_type": "TEXT", "primary_key": True}]
        children = []
        nested_json_columns = []
        known_fields = set()
        for path, entry in sorted(info["fields"].items()):
            if "[]" in path:
                continue
            if path == id_field:
                continue
            if path.count(".") == 1 and info["fields"].get(path, {}).get("type") == "object":
                continue
            if entry.get("type") == "object":
                continue
            if entry.get("type") == "array":
                item_entry = info["fields"].get(path + "[]", {})
                item_type = item_entry.get("type", "string")
                if item_type == "object":
                    singular_table = table[:-1] if table.endswith("s") else table
                    child = {
                        "table": f"{singular_table}_{snake_case(path)}",
                        "array_field": path,
                        "parent_fk": {"source": id_field, "column": f"{table[:-1] if table.endswith('s') else table}_id"},
                        "columns": [],
                    }
                    child["columns"] = [
                        {"source": child_path.removeprefix(path + "[]."), "column": snake_case(child_path.removeprefix(path + "[].")), "sql_type": sql_type(child_info.get("type", "string"))}
                        for child_path, child_info in sorted(info["fields"].items())
                        if child_path.startswith(path + "[].") and child_path.count(".") == path.count(".") + 1
                    ]
                    children.append(child)
                else:
                    columns.append({"source": path, "column": snake_case(path), "sql_type": "TEXT", "json": True})
                    nested_json_columns.append(path)
                continue
            column = snake_case(path)
            columns.append({"source": path, "column": column, "sql_type": sql_type(_field_type(entry))})
            known_fields.add(path)
        collection = {
            "collection": name,
            "table": table,
            "id_field": id_field,
            "columns": columns,
            "children": children,
            "nested_json_columns": nested_json_columns,
            "indexes": [],
        }
        for column in columns:
            if column["column"] in {"email", "user_id", "product_id"}:
                collection["indexes"].append(column["column"])
        collections.append(collection)
    table_names = {collection["table"] for collection in collections}
    for collection in collections:
        for column in collection["columns"]:
            if column["column"].endswith("_id") and column["column"] != "id":
                prefix = column["column"][:-3]
                candidates = [prefix, prefix + "s"]
                target = next((candidate for candidate in candidates if candidate in table_names), None)
                if target:
                    column["references"] = {"table": target, "column": "id"}
        for child in collection["children"]:
            for column in child["columns"]:
                if column["column"].endswith("_id"):
                    prefix = column["column"][:-3]
                    candidates = [prefix, prefix + "s"]
                    target = next((candidate for candidate in candidates if candidate in table_names), None)
                    if target:
                        column["references"] = {"table": target, "column": "id"}
    proposal = {
        "version": 1,
        "source_kind": inspection.get("source_kind", "json-document-store"),
        "strategy": {
            "nested_objects": "flatten one level into snake_case columns",
            "arrays_of_objects": "separate child table with parent foreign key",
            "arrays_of_primitives": "preserve as JSON text",
            "nulls": "load as SQL NULL",
        },
        "collections": collections,
    }
    proposal["assistant"] = generate_assist(proposal)
    return proposal
