#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from .models import MeaningCapsule, CapsuleStatus, json_ready
from .capsule_bus import MeaningCapsuleBus
from .context_graph import ContextGraphStore
from .conflict_registry import ConflictRegistry
from .intervention_controller import InterventionController


@dataclass
class InvariantResult:
    name: str
    ok: bool
    score: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))


class InvariantMonitor:
    """Checks distributed invariants over runtime state.

    These are deliberately operational, not metaphysical:
    - Safety: hazardous capsules are quarantined/refused.
    - Liveness: the system can progress or safely abstain.
    - NonDomination: no source dominates the runtime.
    - Auditability: provenance and trace data exist.
    - Corrigibility: intervention/rollback exists.
    - Refusability: non-translation is preserved as valid state.
    """

    def __init__(
        self,
        *,
        domination_cap: float = 0.55,
        max_active_semantic_loss: float = 0.70,
    ) -> None:
        self.domination_cap = domination_cap
        self.max_active_semantic_loss = max_active_semantic_loss
        self.history: List[Dict[str, Any]] = []

    def check(
        self,
        *,
        bus: MeaningCapsuleBus,
        memories: ContextGraphStore,
        conflicts: ConflictRegistry,
        interventions: InterventionController,
        expected_agents: Optional[List[str]] = None,
    ) -> List[InvariantResult]:
        capsules = bus.all_capsules()
        results = [
            self._safety(capsules),
            self._liveness(capsules, expected_agents=expected_agents),
            self._non_domination(capsules, memories),
            self._auditability(capsules),
            self._corrigibility(interventions),
            self._refusability(capsules, memories),
            self._conflict_retention(conflicts),
            self._productive_disagreement(capsules, conflicts),
            self._stalemate_risk(capsules, conflicts),
        ]
        self.history.append({
            "results": [r.to_dict() for r in results],
            "overall_ok": all(r.ok for r in results),
        })
        return results

    def _safety(self, capsules: List[MeaningCapsule]) -> InvariantResult:
        active_bad = []
        for c in capsules:
            text = c.content.text.lower()
            suspicious = any(x in text for x in ["total_state", "private_state", "api key", "password", "centralize all memory", "override all"])
            high_loss = c.status == CapsuleStatus.ACTIVE and c.metrics.semantic_loss > self.max_active_semantic_loss
            if c.status == CapsuleStatus.ACTIVE and (suspicious or high_loss):
                active_bad.append(c.id)
        ok = not active_bad
        return InvariantResult(
            name="Safety",
            ok=ok,
            score=1.0 if ok else 0.0,
            message="No unsafe active capsule remains." if ok else "Unsafe capsule remained active.",
            details={"active_bad": active_bad},
        )

    def _liveness(self, capsules: List[MeaningCapsule], expected_agents: Optional[List[str]]) -> InvariantResult:
        active = [c for c in capsules if c.status == CapsuleStatus.ACTIVE]
        refused = [c for c in capsules if c.status == CapsuleStatus.REFUSED]
        quarantined = [c for c in capsules if c.status == CapsuleStatus.QUARANTINED]
        # Liveness includes safe abstention / refusal. A network can refuse and remain live.
        progress = len(active) > 0
        safe_abstain = len(refused) > 0 or len(quarantined) > 0
        expected = len(expected_agents or [])
        coverage = 1.0
        if expected:
            sources = {c.source_agent for c in capsules}
            coverage = len(sources.intersection(expected_agents or [])) / max(1, expected)
        ok = (progress or safe_abstain) and coverage >= 0.5
        return InvariantResult(
            name="Liveness",
            ok=ok,
            score=(0.7 if (progress or safe_abstain) else 0.0) + 0.3 * coverage,
            message="System progressed or safely abstained." if ok else "System stalled without enough agent coverage.",
            details={"active": len(active), "refused": len(refused), "quarantined": len(quarantined), "coverage": coverage},
        )

    def _non_domination(self, capsules: List[MeaningCapsule], memories: ContextGraphStore) -> InvariantResult:
        source_counts: Dict[str, float] = {}
        for c in capsules:
            if c.status == CapsuleStatus.ACTIVE:
                source_counts[c.source_agent] = source_counts.get(c.source_agent, 0.0) + 1.0
            elif c.status == CapsuleStatus.QUARANTINED:
                source_counts[c.source_agent] = source_counts.get(c.source_agent, 0.0) + 0.2
            elif c.status == CapsuleStatus.REFUSED:
                source_counts[c.source_agent] = source_counts.get(c.source_agent, 0.0) + 0.4

        # Add influence seen inside private context graphs as an average, not max.
        # A max would falsely treat one local memory graph as global domination.
        graph_accum: Dict[str, float] = {}
        graph_n = max(1, len(memories.graphs))
        for graph in memories.graphs.values():
            for agent, inf in graph.influence_by_agent().items():
                graph_accum[agent] = graph_accum.get(agent, 0.0) + inf
        graph_influence = {k: v / graph_n for k, v in graph_accum.items()}

        total = sum(source_counts.values()) or 1.0
        source_share = {k: v / total for k, v in source_counts.items()}
        combined = dict(source_share)
        for k, v in graph_influence.items():
            combined[k] = max(combined.get(k, 0.0), v)

        max_agent = None
        max_share = 0.0
        if combined:
            max_agent, max_share = max(combined.items(), key=lambda kv: kv[1])
        ok = max_share <= self.domination_cap
        return InvariantResult(
            name="NonDomination",
            ok=ok,
            score=max(0.0, 1.0 - max(0.0, max_share - self.domination_cap)),
            message="No single source exceeds influence cap." if ok else f"{max_agent} exceeds influence cap.",
            details={"domination_cap": self.domination_cap, "max_agent": max_agent, "max_share": max_share, "shares": combined},
        )

    def _auditability(self, capsules: List[MeaningCapsule]) -> InvariantResult:
        missing = []
        for c in capsules:
            if not c.provenance.created_by or not c.provenance.created_at:
                missing.append(c.id)
            # Active translated capsules should have traces.
            if c.id.startswith("translated_") and not c.translation_trace:
                missing.append(c.id)
        ok = not missing
        score = 1.0 if not capsules else 1.0 - (len(set(missing)) / len(capsules))
        return InvariantResult(
            name="Auditability",
            ok=ok,
            score=max(0.0, score),
            message="All capsules have enough provenance/trace." if ok else "Some capsules lack provenance/trace.",
            details={"missing": sorted(set(missing))},
        )

    def _corrigibility(self, interventions: InterventionController) -> InvariantResult:
        score = interventions.recoverability_score()
        ok = score >= 0.75
        return InvariantResult(
            name="Corrigibility",
            ok=ok,
            score=score,
            message="Intervention and recovery are available." if ok else "Recovery path is weak.",
            details={"interventions": len(interventions.records), "snapshots": len(interventions.snapshots)},
        )

    def _refusability(self, capsules: List[MeaningCapsule], memories: ContextGraphStore) -> InvariantResult:
        refusals = [c for c in capsules if c.status == CapsuleStatus.REFUSED]
        stored_refusals = 0
        for graph in memories.graphs.values():
            stored_refusals += sum(1 for n in graph.nodes.values() if n.node_type == "refusal")
        ok = len(refusals) == 0 or stored_refusals >= len(refusals)
        # Even without refusals, protocol supports refusability. With refusals, preservation matters.
        score = 1.0 if ok else max(0.0, stored_refusals / max(1, len(refusals)))
        return InvariantResult(
            name="Refusability",
            ok=ok,
            score=score,
            message="Refusal is preserved as valid semantic state." if ok else "Some refusals were not preserved.",
            details={"refusals": len(refusals), "stored_refusals": stored_refusals},
        )

    def _conflict_retention(self, conflicts: ConflictRegistry) -> InvariantResult:
        rate = conflicts.conflict_retention_rate()
        ok = rate >= 0.90
        return InvariantResult(
            name="ConflictRetention",
            ok=ok,
            score=rate,
            message="Unresolved conflicts are retained." if ok else "Some conflicts were erased too early.",
            details={"conflicts": len(conflicts.conflicts), "retention_rate": rate},
        )

    def _productive_disagreement(self, capsules: List[MeaningCapsule], conflicts: ConflictRegistry) -> InvariantResult:
        conflicts_count = len(conflicts.conflicts)
        refusals = [c for c in capsules if c.status == CapsuleStatus.REFUSED]
        commitments = [c for c in capsules if c.intent == "bounded_commitment" and c.status == CapsuleStatus.ACTIVE]
        safe_next_steps = sum(len(c.refusal.safe_next_steps) for c in refusals if c.refusal)
        active_non_commitment = [
            c for c in capsules
            if c.status == CapsuleStatus.ACTIVE and c.intent != "bounded_commitment"
        ]

        if conflicts_count == 0:
            score = 1.0
            message = "No unresolved conflict currently needs productive handling."
        else:
            signal = 0.0
            signal += 0.35 if safe_next_steps >= len(refusals) else 0.15 if safe_next_steps else 0.0
            signal += 0.35 if commitments else 0.0
            signal += 0.20 if active_non_commitment else 0.0
            signal += 0.10 if any(c.content.unresolved_terms for c in capsules) else 0.0
            score = min(1.0, signal)
            message = (
                "Disagreement is producing bounded action or safe next steps."
                if score >= 0.65 else
                "Disagreement is retained but may not yet be producing enough next action."
            )

        ok = score >= 0.65
        return InvariantResult(
            name="ProductiveDisagreement",
            ok=ok,
            score=score,
            message=message,
            details={
                "conflicts": conflicts_count,
                "refusals": len(refusals),
                "safe_next_steps": safe_next_steps,
                "bounded_commitments": len(commitments),
                "active_non_commitment": len(active_non_commitment),
            },
        )

    def _stalemate_risk(self, capsules: List[MeaningCapsule], conflicts: ConflictRegistry) -> InvariantResult:
        total = max(1, len(capsules))
        active = [c for c in capsules if c.status == CapsuleStatus.ACTIVE]
        refusals = [c for c in capsules if c.status == CapsuleStatus.REFUSED]
        quarantined = [c for c in capsules if c.status == CapsuleStatus.QUARANTINED]
        commitments = [c for c in capsules if c.intent == "bounded_commitment" and c.status == CapsuleStatus.ACTIVE]

        refusal_density = len(refusals) / total
        active_density = len(active) / total
        conflict_pressure = min(1.0, len(conflicts.conflicts) / max(1, len(active) + len(refusals)))
        commitment_relief = min(0.35, 0.12 * len(commitments))
        quarantine_pressure = len(quarantined) / total

        risk = max(0.0, (
            0.38 * refusal_density
            + 0.32 * conflict_pressure
            + 0.20 * quarantine_pressure
            + 0.10 * max(0.0, 0.30 - active_density)
            - commitment_relief
        ))
        ok = risk < 0.72
        return InvariantResult(
            name="StalemateRisk",
            ok=ok,
            score=1.0 - min(1.0, risk),
            message="Refusal/conflict load remains below stalemate threshold." if ok else "Runtime may be preserving disagreement without enough movement.",
            details={
                "risk": risk,
                "refusal_density": refusal_density,
                "active_density": active_density,
                "conflict_pressure": conflict_pressure,
                "quarantine_pressure": quarantine_pressure,
                "bounded_commitments": len(commitments),
            },
        )

    @staticmethod
    def summarize(results: List[InvariantResult]) -> Dict[str, Any]:
        return {
            "overall_ok": all(r.ok for r in results),
            "scores": {r.name: r.score for r in results},
            "results": [r.to_dict() for r in results],
        }
