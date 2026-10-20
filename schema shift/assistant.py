from __future__ import annotations

import json
import os
from typing import Any


def _offline_assist(proposal: dict[str, Any], similarity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safe offline assist; it can explain but cannot mutate a schema or database."""
    notes = []
    for collection in proposal.get("collections", []):
        for child in collection.get("children", []):
            notes.append(
                f"{collection['table']}.{child['array_field']} is represented as child table "
                f"{child['table']} because each array element has its own identity and foreign key."
            )
        if collection.get("nested_json_columns"):
            notes.append(
                f"{collection['table']} keeps primitive arrays as JSON because flattening them would "
                "create a less useful one-to-many table for this sample."
            )
    if similarity:
        notes.append(
            f"The deterministic similarity score is {similarity['overall_percent']:.2f}%; "
            "review items below the configured threshold before freezing."
        )
    return {
        "provider": "offline-heuristic",
        "deterministic_writes_allowed": False,
        "summary": "Offline reviewer guidance generated from the frozen candidate schema.",
        "notes": notes,
        "risk_warnings": [
            "A human must approve low-confidence mappings before generation.",
            "The assistant is advisory only; DDL, ETL, and verification remain deterministic.",
        ],
    }


def generate_assist(proposal: dict[str, Any], similarity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Optionally call an LLM for explanations, never for production side effects.

    Set SCHEMASHIFT_LLM=1 and OPENAI_API_KEY to enable it. If the optional package or
    key is missing, the safe offline explanation is used.
    """
    if os.getenv("SCHEMASHIFT_LLM") != "1" or not os.getenv("OPENAI_API_KEY"):
        return _offline_assist(proposal, similarity)
    try:
        from openai import OpenAI

        client = OpenAI()
        prompt = {
            "task": "Explain a proposed NoSQL-to-SQL migration for a reviewer. Do not invent mappings.",
            "proposal": proposal,
            "similarity": similarity,
            "return_json_keys": ["summary", "notes", "risk_warnings"],
        }
        response = client.responses.create(
            model=os.getenv("SCHEMASHIFT_MODEL", "gpt-4.1-mini"),
            input=json.dumps(prompt),
        )
        text = response.output_text
        parsed = json.loads(text)
        return {
            "provider": "openai",
            "model": os.getenv("SCHEMASHIFT_MODEL", "gpt-4.1-mini"),
            "deterministic_writes_allowed": False,
            **parsed,
        }
    except Exception as exc:  # Optional assistance must never break migration safety.
        fallback = _offline_assist(proposal, similarity)
        fallback["provider"] = "offline-fallback-after-assist-error"
        fallback["error"] = str(exc)
        return fallback
