from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .infer import snake_case, sql_type


def _type_for_source(field: dict[str, Any]) -> str:
    counts = field.get("type_counts", {})
    non_null = [key for key in counts if key != "null"]
    return non_null[0] if len(non_null) == 1 else field.get("type", "string")


def _score(source: str, target: str, source_type: str, target_type: str) -> tuple[float, dict[str, float]]:
    expected = snake_case(source.replace("[].", "_"))
    if source in {"_id", "id"} and target == "id":
        name = 1.0
    else:
        name = SequenceMatcher(None, expected, target).ratio()
    source_tokens = set(expected.split("_"))
    target_tokens = set(target.split("_"))
    token = len(source_tokens & target_tokens) / max(1, len(source_tokens | target_tokens))
    compatible = sql_type(source_type) == target_type
    type_score = 1.0 if compatible else 0.35
    total = round(0.55 * name + 0.25 * token + 0.20 * type_score, 4)
    return total, {"name": round(name, 4), "token": round(token, 4), "type": type_score}


def calculate_similarity(inspection: dict[str, Any], proposal: dict[str, Any], threshold: float = 0.65) -> dict[str, Any]:
    by_entity = []
    all_scores = []
    for collection in proposal["collections"]:
        source = inspection["collections"][collection["collection"]]
        fields = []
        for column in collection["columns"]:
            source_path = column["source"]
            source_entry = source["fields"].get(source_path, {"type": "string", "type_counts": {"string": 1}})
            score, components = _score(source_path, column["column"], _type_for_source(source_entry), column["sql_type"])
            classification = "matched" if score >= 0.85 else ("guessed" if score >= threshold else "needs_review")
            item = {
                "source": source_path,
                "target": f"{collection['table']}.{column['column']}",
                "score": score,
                "percent": round(score * 100, 2),
                "classification": classification,
                "components": components,
            }
            fields.append(item)
            all_scores.append(score)
        by_entity.append({
            "source_collection": collection["collection"],
            "target_table": collection["table"],
            "percent": round((sum(item["score"] for item in fields) / max(1, len(fields))) * 100, 2),
            "fields": fields,
        })
    overall = (sum(all_scores) / max(1, len(all_scores))) * 100
    result = {
        "algorithm": "0.55 name + 0.25 token overlap + 0.20 type compatibility",
        "threshold": threshold,
        "overall_percent": round(overall, 2),
        "entities": by_entity,
        "needs_review": [field for entity in by_entity for field in entity["fields"] if field["classification"] == "needs_review"],
        "deterministic": True,
    }
    return result
