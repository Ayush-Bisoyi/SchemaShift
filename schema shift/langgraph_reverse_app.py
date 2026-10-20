"""Real LangGraph orchestration for the SQL-to-NoSQL bonus path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, TypedDict

from .assistant import generate_assist
from .freeze import freeze_schema
from .io_utils import read_json, write_json
from .reverse import (
    calculate_reverse_similarity,
    export_sqlite_to_documents,
    generate_reverse_artifacts,
    infer_document_model,
    inspect_sqlite,
    verify_reverse_export,
)


class ReverseState(TypedDict, total=False):
    database: str
    forward_map: dict[str, Any]
    artifacts: str
    auto_approve: bool
    inspection: dict[str, Any]
    model: dict[str, Any]
    similarity: dict[str, Any]
    frozen: dict[str, Any]
    export: dict[str, Any]
    verification: dict[str, Any]
    approved: bool


def _imports() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Command, interrupt
    except ImportError as exc:
        raise RuntimeError("Install LangGraph with: python3 -m pip install -r requirements-langgraph.txt") from exc
    return StateGraph, START, END, InMemorySaver, Command, interrupt


def build_reverse_graph() -> Any:
    StateGraph, START, END, InMemorySaver, _Command, interrupt = _imports()

    def inspect_node(state: ReverseState) -> dict[str, Any]:
        report = inspect_sqlite(state["database"])
        write_json(Path(state["artifacts"]) / "reverse_inspection.json", report)
        return {"inspection": report}

    def infer_node(state: ReverseState) -> dict[str, Any]:
        model = infer_document_model(state["inspection"], state.get("forward_map"))
        model["assistant"] = generate_assist({"collections": model["collections"], "strategy": model["strategy"]})
        write_json(Path(state["artifacts"]) / "reverse_model.json", model)
        return {"model": model}

    def similarity_node(state: ReverseState) -> dict[str, Any]:
        result = calculate_reverse_similarity(state["inspection"], state["model"])
        result["assistant"] = generate_assist(state["model"], result)
        write_json(Path(state["artifacts"]) / "reverse_similarity.json", result)
        return {"similarity": result}

    def approval_node(state: ReverseState) -> dict[str, Any]:
        if state.get("auto_approve"):
            return {"approved": True}
        decision = interrupt({"type": "reverse_schema_approval", "message": "Review reverse_similarity.json and approve.", "needs_review": state["similarity"].get("needs_review", [])})
        if not isinstance(decision, dict) or decision.get("approved") is not True:
            raise ValueError("Reverse schema was not approved")
        return {"approved": True}

    def freeze_node(state: ReverseState) -> dict[str, Any]:
        frozen = freeze_schema(state["model"], state["similarity"], state["approved"])
        write_json(Path(state["artifacts"]) / "reverse_schema_map.json", frozen)
        return {"frozen": frozen}

    def generate_node(state: ReverseState) -> dict[str, Any]:
        generate_reverse_artifacts(state["frozen"], Path(state["artifacts"]) / "reverse_generated")
        return {}

    def export_node(state: ReverseState) -> dict[str, Any]:
        result = export_sqlite_to_documents(state["database"], state["frozen"], Path(state["artifacts"]) / "reverse_documents")
        return {"export": result}

    def verify_node(state: ReverseState) -> dict[str, Any]:
        result = verify_reverse_export(state["database"], state["frozen"], Path(state["artifacts"]) / "reverse_documents")
        write_json(Path(state["artifacts"]) / "reverse_verification.json", result)
        return {"verification": result}

    graph = StateGraph(ReverseState)
    for name, function in [("inspect", inspect_node), ("infer", infer_node), ("similarity", similarity_node), ("approval", approval_node), ("freeze", freeze_node), ("generate", generate_node), ("export", export_node), ("verify", verify_node)]:
        graph.add_node(name, function)
    graph.add_edge(START, "inspect")
    graph.add_edge("inspect", "infer")
    graph.add_edge("infer", "similarity")
    graph.add_edge("similarity", "approval")
    graph.add_edge("approval", "freeze")
    graph.add_edge("freeze", "generate")
    graph.add_edge("generate", "export")
    graph.add_edge("export", "verify")
    graph.add_edge("verify", END)
    return graph.compile(checkpointer=InMemorySaver())


def run_reverse_langgraph(database: str, forward_map: dict[str, Any], artifacts: str, approve: bool = False) -> dict[str, Any]:
    graph = build_reverse_graph()
    config = {"configurable": {"thread_id": "schemashift-reverse-demo"}}
    result = graph.invoke({"database": database, "forward_map": forward_map, "artifacts": artifacts, "auto_approve": approve}, config)
    if result.get("__interrupt__") and sys.stdin.isatty():
        answer = input("Type APPROVE to continue the reverse migration: ").strip().upper()
        _, _, _, _, Command, _ = _imports()
        result = graph.invoke(Command(resume={"approved": answer == "APPROVE"}), config)
    if not result.get("verification", {}).get("passed"):
        raise RuntimeError("Reverse LangGraph verification failed or was not approved")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SchemaShift SQL-to-NoSQL through LangGraph")
    parser.add_argument("--db", default="artifacts/sample/demo.sqlite")
    parser.add_argument("--forward-map", default="artifacts/sample/schema_map.json")
    parser.add_argument("--artifacts", default="artifacts/reverse-langgraph")
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    result = run_reverse_langgraph(args.db, read_json(args.forward_map), args.artifacts, args.approve)
    print(f"Reverse LangGraph export complete: {result['export']['documents_written']}")
    print(f"Reverse verification passed: {result['verification']['passed']}")


if __name__ == "__main__":
    main()
