"""Real LangGraph orchestration for SchemaShift.

The migration functions remain deterministic and are imported as graph nodes.
LangGraph owns sequencing, checkpointing, and the human approval interrupt.
Install with: python3 -m pip install -r requirements-langgraph.txt
Run with:     python3 -m schemashift.langgraph_app --approve
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, TypedDict

from .assistant import generate_assist
from .freeze import freeze_schema
from .generate import generate_artifacts
from .infer import infer_schema
from .inspect import inspect_source
from .io_utils import write_json
from .migrate import migrate
from .similarity import calculate_similarity
from .verify import verify


class MigrationState(TypedDict, total=False):
    source: str
    artifacts: str
    database: str
    auto_approve: bool
    inspection: dict[str, Any]
    proposal: dict[str, Any]
    similarity: dict[str, Any]
    frozen: dict[str, Any]
    verification: dict[str, Any]
    migration: dict[str, Any]
    approved: bool
    generated: list[str]


def _require_langgraph() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Command, interrupt
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Run: python3 -m pip install -r requirements-langgraph.txt"
        ) from exc
    return StateGraph, START, END, InMemorySaver, Command, interrupt


def build_graph() -> Any:
    StateGraph, START, END, InMemorySaver, _Command, interrupt = _require_langgraph()

    def inspect_node(state: MigrationState) -> dict[str, Any]:
        report = inspect_source(state["source"])
        write_json(Path(state["artifacts"]) / "langgraph_inspection.json", report)
        return {"inspection": report}

    def infer_node(state: MigrationState) -> dict[str, Any]:
        proposal = infer_schema(state["inspection"])
        proposal["assistant"] = generate_assist(proposal)
        write_json(Path(state["artifacts"]) / "langgraph_proposal.json", proposal)
        return {"proposal": proposal}

    def similarity_node(state: MigrationState) -> dict[str, Any]:
        report = calculate_similarity(state["inspection"], state["proposal"])
        report["assistant"] = generate_assist(state["proposal"], report)
        write_json(Path(state["artifacts"]) / "langgraph_similarity.json", report)
        return {"similarity": report}

    def approval_node(state: MigrationState) -> dict[str, Any]:
        if state.get("auto_approve"):
            return {"approved": True}
        decision = interrupt({
            "type": "schema_approval",
            "message": "Review langgraph_similarity.json. Resume with {approved: true} to continue.",
            "needs_review": state["similarity"].get("needs_review", []),
        })
        if not isinstance(decision, dict) or decision.get("approved") is not True:
            raise ValueError("Schema was not approved; migration stopped before side effects")
        return {"approved": True}

    def freeze_node(state: MigrationState) -> dict[str, Any]:
        frozen = freeze_schema(state["proposal"], state["similarity"], state["approved"])
        write_json(Path(state["artifacts"]) / "langgraph_schema_map.json", frozen)
        return {"frozen": frozen}

    def generate_node(state: MigrationState) -> dict[str, Any]:
        generated = generate_artifacts(state["frozen"], Path(state["artifacts"]) / "langgraph_generated")
        return {"generated": list(generated)}

    def migrate_node(state: MigrationState) -> dict[str, Any]:
        return {"migration": migrate(state["source"], state["database"], state["frozen"])}

    def verify_node(state: MigrationState) -> dict[str, Any]:
        result = verify(state["source"], state["database"], state["frozen"])
        write_json(Path(state["artifacts"]) / "langgraph_verification.json", result)
        return {"verification": result}

    graph = StateGraph(MigrationState)
    graph.add_node("inspect", inspect_node)
    graph.add_node("infer", infer_node)
    graph.add_node("similarity", similarity_node)
    graph.add_node("approval", approval_node)
    graph.add_node("freeze", freeze_node)
    graph.add_node("generate", generate_node)
    graph.add_node("migrate", migrate_node)
    graph.add_node("verify", verify_node)
    graph.add_edge(START, "inspect")
    graph.add_edge("inspect", "infer")
    graph.add_edge("infer", "similarity")
    graph.add_edge("similarity", "approval")
    graph.add_edge("approval", "freeze")
    graph.add_edge("freeze", "generate")
    graph.add_edge("generate", "migrate")
    graph.add_edge("migrate", "verify")
    graph.add_edge("verify", END)
    return graph.compile(checkpointer=InMemorySaver())


def run_langgraph(source: str, artifacts: str, database: str, approve: bool = False) -> dict[str, Any]:
    import sys

    graph = build_graph()
    config = {"configurable": {"thread_id": "schemashift-demo"}}
    initial: MigrationState = {
        "source": source,
        "artifacts": artifacts,
        "database": database,
        "auto_approve": approve,
    }
    result = graph.invoke(initial, config)
    if result.get("__interrupt__"):
        if not sys.stdin.isatty():
            return result
        print("Schema approval is required before migration.")
        answer = input("Type APPROVE to continue: ").strip().upper()
        _StateGraph, _START, _END, _InMemorySaver, Command, _interrupt = _require_langgraph()
        result = graph.invoke(Command(resume={"approved": answer == "APPROVE"}), config)
    if not result.get("verification", {}).get("passed"):
        raise RuntimeError("LangGraph workflow completed, but verification failed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SchemaShift through LangGraph")
    parser.add_argument("--source", default="sample/source")
    parser.add_argument("--artifacts", default="artifacts/langgraph")
    parser.add_argument("--db", default="artifacts/langgraph/demo.sqlite")
    parser.add_argument("--approve", action="store_true", help="automatically approve the reviewed schema")
    args = parser.parse_args()
    result = run_langgraph(args.source, args.artifacts, args.db, args.approve)
    print(f"LangGraph migration complete: {result['migration']['rows_written']}")
    print(f"LangGraph verification passed: {result['verification']['passed']}")


if __name__ == "__main__":
    main()
