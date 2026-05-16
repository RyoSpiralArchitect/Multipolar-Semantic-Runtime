#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math
import re

from .models import (
    MeaningCapsule,
    CapsuleStatus,
    RefusalReason,
    uid,
    now_utc,
    iso,
    json_ready,
)


_TOKEN_RE = re.compile(r"[\w\-∴ψφτΩ]+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    words = [w.lower() for w in _TOKEN_RE.findall(text or "")]
    stop = {
        "the", "and", "or", "to", "of", "in", "a", "is", "it", "for",
        "as", "by", "with", "on", "that", "this", "from", "be", "not",
        "を", "に", "は", "が", "で", "と", "の", "する", "こと"
    }
    result = []
    for w in words:
        if len(w) <= 2 and w not in {"ai", "∴", "ψ", "φ", "τ"}:
            continue
        if w in stop:
            continue
        result.append(w)
    return result[:80]


@dataclass
class ContextNode:
    id: str
    label: str
    node_type: str
    content: Dict[str, Any]
    source_capsule: Optional[str] = None
    source_agent: Optional[str] = None
    weight: float = 1.0
    trust: float = 1.0
    freshness: float = 1.0
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self, delta: float = 0.1) -> None:
        self.weight = max(0.0, min(10.0, self.weight + delta))
        self.updated_at = now_utc()

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))


@dataclass
class ContextEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0
    created_at: datetime = field(default_factory=now_utc)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))


class ContextGraph:
    """Private memory graph for one agent.

    Capsules are not blindly copied into total shared state. They are translated,
    weighted, and attached to local context.
    """

    def __init__(self, owner_agent: str, ontology: str = "general") -> None:
        self.owner_agent = owner_agent
        self.ontology = ontology
        self.nodes: Dict[str, ContextNode] = {}
        self.edges: List[ContextEdge] = []
        self.capsule_index: Dict[str, str] = {}
        self.term_index: Dict[str, str] = {}
        self.event_log: List[Dict[str, Any]] = []
        self._add_root()

    def _add_root(self) -> None:
        root = ContextNode(
            id=f"root_{self.owner_agent}",
            label=f"{self.owner_agent}:private_context",
            node_type="root",
            content={"ontology": self.ontology, "private": True},
            weight=1.0,
            trust=1.0,
            freshness=1.0,
        )
        self.nodes[root.id] = root

    def add_event(self, kind: str, payload: Dict[str, Any]) -> None:
        self.event_log.append({"at": iso(now_utc()), "kind": kind, "payload": json_ready(payload)})

    def add_capsule(
        self,
        capsule: MeaningCapsule,
        *,
        trust: float = 1.0,
        relation: str = "received",
    ) -> str:
        if capsule.id in self.capsule_index:
            node_id = self.capsule_index[capsule.id]
            self.nodes[node_id].touch(0.2 * trust)
            return node_id

        node_type = {
            CapsuleStatus.ACTIVE: "capsule",
            CapsuleStatus.REFUSED: "refusal",
            CapsuleStatus.QUARANTINED: "quarantine",
            CapsuleStatus.EXPIRED: "expired",
        }.get(capsule.status, "capsule")

        base_weight = max(0.05, capsule.confidence * trust)
        if capsule.status == CapsuleStatus.REFUSED:
            # Refusals matter: preserve them, but do not treat as positive content consensus.
            base_weight *= 0.85
        if capsule.status == CapsuleStatus.QUARANTINED:
            base_weight *= 0.25

        node = ContextNode(
            id=uid("ctx"),
            label=f"{node_type}:{capsule.id}",
            node_type=node_type,
            content={
                "text": capsule.content.text,
                "ontology": capsule.content.ontology,
                "intent": capsule.intent,
                "claims": capsule.content.claims,
                "assumptions": capsule.content.assumptions,
                "unresolved_terms": capsule.content.unresolved_terms,
                "status": capsule.status.value,
                "refusal": capsule.refusal.to_dict() if capsule.refusal else None,
                "metrics": capsule.metrics.to_dict(),
                "translation_trace": [t.to_dict() for t in capsule.translation_trace],
            },
            source_capsule=capsule.id,
            source_agent=capsule.source_agent,
            weight=base_weight,
            trust=trust,
            freshness=1.0,
            metadata={
                "risk_level": capsule.scope.risk_level,
                "constraints": capsule.constraints,
                "received_by": self.owner_agent,
            },
        )
        self.nodes[node.id] = node
        self.capsule_index[capsule.id] = node.id
        self.edges.append(ContextEdge(
            source=f"root_{self.owner_agent}",
            target=node.id,
            relation=relation,
            weight=base_weight,
            metadata={"capsule_id": capsule.id},
        ))

        # Terms become local context anchors.
        for term in tokenize(capsule.content.text):
            term_node_id = self._ensure_term(term)
            self.edges.append(ContextEdge(
                source=node.id,
                target=term_node_id,
                relation="mentions",
                weight=min(1.0, 0.25 + base_weight),
                metadata={"term": term},
            ))

        # Claims become structured local memory.
        for claim in capsule.content.claims:
            claim_node = ContextNode(
                id=uid("claim"),
                label=f"claim:{claim[:60]}",
                node_type="claim",
                content={"claim": claim},
                source_capsule=capsule.id,
                source_agent=capsule.source_agent,
                weight=base_weight,
                trust=trust,
                freshness=1.0,
            )
            self.nodes[claim_node.id] = claim_node
            self.edges.append(ContextEdge(
                source=node.id,
                target=claim_node.id,
                relation="asserts",
                weight=base_weight,
                metadata={"capsule_id": capsule.id},
            ))

        self.add_event("capsule_integrated", {
            "capsule": capsule.id,
            "source_agent": capsule.source_agent,
            "status": capsule.status.value,
            "trust": trust,
            "node": node.id,
        })
        return node.id

    def add_refusal(self, capsule: MeaningCapsule, *, trust: float = 1.0) -> str:
        return self.add_capsule(capsule, trust=trust, relation="refusal_preserved")

    def add_conflict(self, conflict_id: str, capsules: List[str], summary: str) -> str:
        node = ContextNode(
            id=uid("conflict"),
            label=f"conflict:{conflict_id}",
            node_type="conflict",
            content={"conflict_id": conflict_id, "capsules": capsules, "summary": summary},
            weight=1.0,
            trust=1.0,
            freshness=1.0,
        )
        self.nodes[node.id] = node
        self.edges.append(ContextEdge(
            source=f"root_{self.owner_agent}",
            target=node.id,
            relation="conflict_retained",
            weight=1.0,
        ))
        for cid in capsules:
            if cid in self.capsule_index:
                self.edges.append(ContextEdge(
                    source=node.id,
                    target=self.capsule_index[cid],
                    relation="involves",
                    weight=1.0,
                    metadata={"conflict_id": conflict_id},
                ))
        self.add_event("conflict_retained", {"conflict_id": conflict_id, "capsules": capsules})
        return node.id

    def _ensure_term(self, term: str) -> str:
        if term in self.term_index:
            self.nodes[self.term_index[term]].touch(0.05)
            return self.term_index[term]
        node = ContextNode(
            id=uid("term"),
            label=f"term:{term}",
            node_type="term",
            content={"term": term},
            weight=0.4,
            trust=1.0,
            freshness=1.0,
        )
        self.nodes[node.id] = node
        self.term_index[term] = node.id
        return node.id

    def influence_by_agent(self) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for node in self.nodes.values():
            if node.source_agent:
                scores[node.source_agent] = scores.get(node.source_agent, 0.0) + node.weight
        total = sum(scores.values()) or 1.0
        return {k: v / total for k, v in scores.items()}

    def drift_score(self) -> float:
        # A simple proxy: total number of non-root nodes weighted by recency.
        non_root = [n for n in self.nodes.values() if n.node_type != "root"]
        if not non_root:
            return 0.0
        return min(1.0, math.log1p(len(non_root)) / 8.0)

    def top_terms(self, limit: int = 12) -> List[Tuple[str, float]]:
        terms = [(n.content.get("term", n.label), n.weight) for n in self.nodes.values() if n.node_type == "term"]
        return sorted(terms, key=lambda x: x[1], reverse=True)[:limit]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner_agent": self.owner_agent,
            "ontology": self.ontology,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "influence_by_agent": self.influence_by_agent(),
            "drift_score": self.drift_score(),
            "top_terms": self.top_terms(),
            "event_log": self.event_log,
        }


class ContextGraphStore:
    """One private ContextGraph per agent."""

    def __init__(self) -> None:
        self.graphs: Dict[str, ContextGraph] = {}

    def ensure(self, agent_id: str, ontology: str = "general") -> ContextGraph:
        if agent_id not in self.graphs:
            self.graphs[agent_id] = ContextGraph(agent_id, ontology)
        return self.graphs[agent_id]

    def update_with_capsule(self, agent_id: str, capsule: MeaningCapsule, *, trust: float = 1.0) -> str:
        graph = self.ensure(agent_id)
        if capsule.status == CapsuleStatus.REFUSED:
            return graph.add_refusal(capsule, trust=trust)
        return graph.add_capsule(capsule, trust=trust)

    def retain_conflict(self, agent_id: str, conflict_id: str, capsules: List[str], summary: str) -> str:
        graph = self.ensure(agent_id)
        return graph.add_conflict(conflict_id, capsules, summary)

    def to_dict(self) -> Dict[str, Any]:
        return {agent_id: graph.to_dict() for agent_id, graph in self.graphs.items()}
