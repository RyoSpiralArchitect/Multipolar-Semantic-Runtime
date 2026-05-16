#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from copy import deepcopy

from .models import MeaningCapsule, InterventionType, uid, now_utc, iso, json_ready


@dataclass
class InterventionRecord:
    id: str
    at: str
    type: InterventionType
    target: str
    reason: str
    reversible: bool
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value if isinstance(self.type, InterventionType) else str(self.type)
        return json_ready(d)


class InterventionController:
    """Minimal interruptible control layer for bounded plurality."""

    def __init__(self) -> None:
        self.records: List[InterventionRecord] = []
        self.snapshots: List[Dict[str, Any]] = []
        self.isolated_agents: set[str] = set()

    def snapshot(self, label: str, state: Dict[str, Any]) -> None:
        self.snapshots.append({
            "id": uid("snapshot"),
            "at": iso(now_utc()),
            "label": label,
            "state": deepcopy(state),
        })

    def quarantine_capsule(self, capsule: MeaningCapsule, reason: str) -> InterventionRecord:
        rec = InterventionRecord(
            id=uid("iv"),
            at=iso(now_utc()),
            type=InterventionType.QUARANTINE,
            target=capsule.id,
            reason=reason,
            reversible=True,
            metadata={"source_agent": capsule.source_agent},
        )
        capsule.audit.intervention_ids.append(rec.id)
        capsule.audit.quarantine_reason = reason
        self.records.append(rec)
        return rec

    def isolate_agent(self, agent_id: str, reason: str) -> InterventionRecord:
        self.isolated_agents.add(agent_id)
        rec = InterventionRecord(
            id=uid("iv"),
            at=iso(now_utc()),
            type=InterventionType.ISOLATE_AGENT,
            target=agent_id,
            reason=reason,
            reversible=True,
            metadata={},
        )
        self.records.append(rec)
        return rec

    def human_review(self, target: str, reason: str) -> InterventionRecord:
        rec = InterventionRecord(
            id=uid("iv"),
            at=iso(now_utc()),
            type=InterventionType.HUMAN_REVIEW,
            target=target,
            reason=reason,
            reversible=True,
            metadata={},
        )
        self.records.append(rec)
        return rec

    def recoverability_score(self) -> float:
        # Quarantine/isolation/human review are all reversible in this prototype.
        if not self.records:
            return 1.0
        reversible = sum(1 for r in self.records if r.reversible)
        has_snapshot = 1 if self.snapshots else 0
        return min(1.0, (reversible / len(self.records)) * 0.8 + has_snapshot * 0.2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "isolated_agents": sorted(self.isolated_agents),
            "snapshot_count": len(self.snapshots),
            "recoverability_score": self.recoverability_score(),
        }
