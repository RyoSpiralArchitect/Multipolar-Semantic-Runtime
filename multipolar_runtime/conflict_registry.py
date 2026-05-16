#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Tuple
import re

from .models import MeaningCapsule, uid, now_utc, iso, json_ready


def normalize_claim(claim: str) -> str:
    c = claim.lower().strip()
    c = re.sub(r"^(must|should|avoid|do not|not|preserve|centralize|decentralize)[:\s]+", "", c)
    c = re.sub(r"\s+", " ", c)
    return c


def polarity(claim: str) -> int:
    c = claim.lower()
    if any(x in c for x in ["must_not", "do not", "avoid", "prevent", "no_", "non-domination", "decentralize", "preserve refusability"]):
        return -1
    if any(x in c for x in ["must", "should", "centralize", "force", "override"]):
        return 1
    return 0


def concept_key(claim: str) -> str:
    """Map claims to coarse conflict concepts.

    This prevents false erasure when agents use different terms for the same
    disputed object, e.g. centralize memory vs non-domination.
    """
    c = claim.lower()
    if any(x in c for x in ["centralize", "override", "dominate", "non-domination", "force consensus", "refusability"]):
        return "domination_control"
    if any(x in c for x in ["total_state", "private_state", "share"]):
        return "state_boundary"
    if any(x in c for x in ["conflict", "consensus"]):
        return "conflict_consensus"
    if any(x in c for x in ["refusal", "translate", "translation"]):
        return "translation_refusal"
    return normalize_claim(claim)


@dataclass
class Conflict:
    id: str
    created_at: str
    claims: List[str]
    capsule_ids: List[str]
    agents: List[str]
    incompatible_assumptions: List[str] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    possible_resolutions: List[str] = field(default_factory=list)
    unresolved_status: str = "unresolved"

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))


class ConflictRegistry:
    """Preserves disagreement as a first-class object."""

    def __init__(self) -> None:
        self.conflicts: Dict[str, Conflict] = {}
        self.claim_index: Dict[str, List[Tuple[str, str, int, str]]] = {}

    def observe(self, capsule: MeaningCapsule) -> List[Conflict]:
        new_conflicts: List[Conflict] = []
        for claim in capsule.content.claims:
            key = concept_key(claim)
            pol = polarity(claim)
            if not key:
                continue
            previous = self.claim_index.get(key, [])
            for prev_claim, prev_capsule, prev_pol, prev_agent in previous:
                if pol != 0 and prev_pol != 0 and pol != prev_pol:
                    conflict = Conflict(
                        id=uid("conflict"),
                        created_at=iso(now_utc()),
                        claims=[prev_claim, claim],
                        capsule_ids=[prev_capsule, capsule.id],
                        agents=sorted({prev_agent, capsule.source_agent}),
                        incompatible_assumptions=[
                            "Claims map to same normalized semantic object with opposite polarity."
                        ],
                        required_evidence=[
                            "source provenance",
                            "agent-specific constraints",
                            "translation trace",
                        ],
                        possible_resolutions=[
                            "preserve_conflict",
                            "request_context",
                            "split_scope",
                            "human_review",
                            "safe_abstention",
                        ],
                    )
                    self.conflicts[conflict.id] = conflict
                    new_conflicts.append(conflict)
            previous.append((claim, capsule.id, pol, capsule.source_agent))
            self.claim_index[key] = previous
        return new_conflicts

    def conflict_retention_rate(self, total_detected: int | None = None) -> float:
        if total_detected is None:
            total_detected = len(self.conflicts)
        if total_detected == 0:
            return 1.0
        retained = sum(1 for c in self.conflicts.values() if c.unresolved_status == "unresolved")
        return retained / total_detected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflicts": [c.to_dict() for c in self.conflicts.values()],
            "conflict_retention_rate": self.conflict_retention_rate(),
        }
