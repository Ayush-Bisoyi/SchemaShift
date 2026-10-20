from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def freeze_schema(proposal: dict[str, Any], similarity: dict[str, Any], approved: bool) -> dict[str, Any]:
    needs_review = similarity.get("needs_review", [])
    if needs_review and not approved:
        raise ValueError(
            f"Human approval required: {len(needs_review)} mapping(s) are below the "
            f"{similarity['threshold']:.2f} confidence threshold"
        )
    canonical = json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode()
    return {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "proposal_sha256": hashlib.sha256(canonical).hexdigest(),
        "approved": approved,
        "approval_note": "Human approved by CLI --approve gate" if approved else "No low-confidence mappings",
        "similarity": similarity,
        "schema": proposal,
    }
