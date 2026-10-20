from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .assistant import generate_assist
from .freeze import freeze_schema
from .generate import generate_artifacts
from .infer import infer_schema
from .inspect import inspect_source
from .io_utils import read_json, write_json
from .migrate import migrate
from .similarity import calculate_similarity
from .verify import verify


class SchemaShiftWorkflow:
    """Explicit graph with deterministic nodes, assist nodes, and a human gate."""

    def __init__(self, source: str, artifacts: str, database: str, approve: bool = False):
        self.source = source
        self.artifacts = Path(artifacts)
        self.database = database
        self.approve = approve
        self.events: list[dict[str, Any]] = []

    def _node(self, name: str, deterministic: bool, function: Callable[[], Any]) -> Any:
        started = datetime.now(timezone.utc).isoformat()
        value = function()
        self.events.append({"node": name, "deterministic": deterministic, "started": started, "status": "ok"})
        return value

    def run(self) -> dict[str, Any]:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        inspection = self._node("inspect_deterministic", True, lambda: inspect_source(self.source))
        write_json(self.artifacts / "inspection.json", inspection)
        proposal = self._node("infer_deterministic", True, lambda: infer_schema(inspection))
        proposal["assistant"] = self._node("infer_assist_explain", False, lambda: generate_assist(proposal))
        write_json(self.artifacts / "proposal.json", proposal)
        similarity = self._node("similarity_deterministic", True, lambda: calculate_similarity(inspection, proposal))
        similarity["assistant"] = self._node("similarity_assist_explain", False, lambda: generate_assist(proposal, similarity))
        write_json(self.artifacts / "similarity.json", similarity)
        frozen = self._node("human_gate_freeze", True, lambda: freeze_schema(proposal, similarity, self.approve))
        write_json(self.artifacts / "schema_map.json", frozen)
        generated = self._node("generate_deterministic", True, lambda: generate_artifacts(frozen, self.artifacts / "generated"))
        migration = self._node("migrate_deterministic", True, lambda: migrate(self.source, self.database, frozen))
        verification = self._node("verify_deterministic", True, lambda: verify(self.source, self.database, frozen))
        verification["assistant"] = self._node("verify_assist_summary", False, lambda: generate_assist(proposal, similarity))
        write_json(self.artifacts / "verification.json", verification)
        result = {"migration": migration, "verification": verification, "events": self.events, "generated": list(generated)}
        write_json(self.artifacts / "workflow_run.json", result)
        return result


def run_workflow(source: str, artifacts: str, database: str, approve: bool = False) -> dict[str, Any]:
    return SchemaShiftWorkflow(source, artifacts, database, approve).run()
