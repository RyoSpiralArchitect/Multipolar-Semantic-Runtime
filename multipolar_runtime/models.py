#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import copy
import uuid


SCHEMA_VERSION = "1.0.0"


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [json_ready(v) for v in value]
    if isinstance(value, tuple):
        return [json_ready(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    return value


class CapsuleStatus(str, Enum):
    ACTIVE = "active"
    REFUSED = "refused"
    QUARANTINED = "quarantined"
    EXPIRED = "expired"


class RefusalReason(str, Enum):
    CANNOT_TRANSLATE = "cannot_translate"
    MUST_NOT_TRANSLATE = "must_not_translate"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    PERMISSION_DENIED = "permission_denied"
    CONFLICT_PRESERVED = "conflict_preserved"
    SAFE_ABSTENTION = "safe_abstention"


class InterventionType(str, Enum):
    QUARANTINE = "quarantine"
    ISOLATE_AGENT = "isolate_agent"
    RATE_LIMIT = "rate_limit"
    ROLLBACK = "rollback"
    HUMAN_REVIEW = "human_review"
    NONE = "none"


@dataclass
class SemanticContent:
    """Bounded semantic projection, never total private state."""

    text: str
    ontology: str
    claims: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    unresolved_terms: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "SemanticContent":
        return copy.deepcopy(self)

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SemanticContent":
        return SemanticContent(
            text=d.get("text", ""),
            ontology=d.get("ontology", "unknown"),
            claims=list(d.get("claims", [])),
            assumptions=list(d.get("assumptions", [])),
            unresolved_terms=list(d.get("unresolved_terms", [])),
            data=dict(d.get("data", {})),
        )


@dataclass
class Provenance:
    created_by: str
    created_at: datetime = field(default_factory=now_utc)
    source_memory_refs: List[str] = field(default_factory=list)
    generation_mode: str = "projected"
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Provenance":
        return Provenance(
            created_by=d.get("created_by", ""),
            created_at=parse_dt(d.get("created_at", iso(now_utc()))),
            source_memory_refs=list(d.get("source_memory_refs", [])),
            generation_mode=d.get("generation_mode", "projected"),
            evidence_refs=list(d.get("evidence_refs", [])),
        )


@dataclass
class Scope:
    valid_for_agents: List[str] = field(default_factory=lambda: ["*"])
    valid_contexts: List[str] = field(default_factory=lambda: ["general"])
    ttl_seconds: int = 3600
    risk_level: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Scope":
        return Scope(
            valid_for_agents=list(d.get("valid_for_agents", ["*"])),
            valid_contexts=list(d.get("valid_contexts", ["general"])),
            ttl_seconds=int(d.get("ttl_seconds", 3600)),
            risk_level=d.get("risk_level", "low"),
        )


@dataclass
class Permissions:
    allow_translate: bool = True
    allow_store: bool = True
    allow_rebroadcast: bool = False
    require_human_review: bool = False
    visibility: str = "bounded"
    allowed_agents: List[str] = field(default_factory=lambda: ["*"])

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Permissions":
        return Permissions(
            allow_translate=bool(d.get("allow_translate", True)),
            allow_store=bool(d.get("allow_store", True)),
            allow_rebroadcast=bool(d.get("allow_rebroadcast", False)),
            require_human_review=bool(d.get("require_human_review", False)),
            visibility=d.get("visibility", "bounded"),
            allowed_agents=list(d.get("allowed_agents", ["*"])),
        )


@dataclass
class TranslationStep:
    from_agent: str
    to_agent: str
    from_ontology: str
    to_ontology: str
    transform: str
    loss: float
    ambiguity: float
    timestamp: datetime = field(default_factory=now_utc)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TranslationStep":
        return TranslationStep(
            from_agent=d.get("from_agent", ""),
            to_agent=d.get("to_agent", ""),
            from_ontology=d.get("from_ontology", ""),
            to_ontology=d.get("to_ontology", ""),
            transform=d.get("transform", ""),
            loss=float(d.get("loss", 0.0)),
            ambiguity=float(d.get("ambiguity", 0.0)),
            timestamp=parse_dt(d.get("timestamp", iso(now_utc()))),
            notes=d.get("notes", ""),
        )


@dataclass
class Refusal:
    reason: RefusalReason
    explanation: str
    preserved_content: Optional[Dict[str, Any]] = None
    safe_next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason.value if isinstance(self.reason, RefusalReason) else str(self.reason),
            "explanation": self.explanation,
            "preserved_content": json_ready(self.preserved_content),
            "safe_next_steps": list(self.safe_next_steps),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Refusal":
        return Refusal(
            reason=RefusalReason(d.get("reason", RefusalReason.SAFE_ABSTENTION.value)),
            explanation=d.get("explanation", ""),
            preserved_content=d.get("preserved_content"),
            safe_next_steps=list(d.get("safe_next_steps", [])),
        )


@dataclass
class AuditMetadata:
    received_at: Optional[datetime] = None
    delivered_to: List[str] = field(default_factory=list)
    quarantine_reason: Optional[str] = None
    intervention_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AuditMetadata":
        received = d.get("received_at")
        return AuditMetadata(
            received_at=parse_dt(received) if received else None,
            delivered_to=list(d.get("delivered_to", [])),
            quarantine_reason=d.get("quarantine_reason"),
            intervention_ids=list(d.get("intervention_ids", [])),
        )


@dataclass
class CapsuleMetrics:
    semantic_loss: float = 0.0
    ambiguity_score: float = 0.0
    domination_pressure: float = 0.0
    trust_weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CapsuleMetrics":
        return CapsuleMetrics(
            semantic_loss=float(d.get("semantic_loss", 0.0)),
            ambiguity_score=float(d.get("ambiguity_score", 0.0)),
            domination_pressure=float(d.get("domination_pressure", 0.0)),
            trust_weight=float(d.get("trust_weight", 1.0)),
        )


@dataclass
class MeaningCapsule:
    id: str
    source_agent: str
    content: SemanticContent
    intent: str
    context_refs: List[str]
    provenance: Provenance
    confidence: float
    scope: Scope
    expiry: datetime
    permissions: Permissions
    constraints: List[str]
    translation_trace: List[TranslationStep] = field(default_factory=list)
    status: CapsuleStatus = CapsuleStatus.ACTIVE
    refusal: Optional[Refusal] = None
    audit: AuditMetadata = field(default_factory=AuditMetadata)
    metrics: CapsuleMetrics = field(default_factory=CapsuleMetrics)
    schema_version: str = SCHEMA_VERSION

    def is_expired(self, at: Optional[datetime] = None) -> bool:
        at = at or now_utc()
        return at >= self.expiry or self.status == CapsuleStatus.EXPIRED

    def mark_expired(self) -> None:
        self.status = CapsuleStatus.EXPIRED

    def clone(self, *, new_id: bool = False, prefix: str = "capsule") -> "MeaningCapsule":
        c = copy.deepcopy(self)
        if new_id:
            c.id = uid(prefix)
        return c

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "source_agent": self.source_agent,
            "content": self.content.to_dict(),
            "intent": self.intent,
            "context_refs": list(self.context_refs),
            "provenance": self.provenance.to_dict(),
            "confidence": self.confidence,
            "scope": self.scope.to_dict(),
            "expiry": iso(self.expiry),
            "permissions": self.permissions.to_dict(),
            "constraints": list(self.constraints),
            "translation_trace": [t.to_dict() for t in self.translation_trace],
            "status": self.status.value if isinstance(self.status, CapsuleStatus) else str(self.status),
            "refusal": self.refusal.to_dict() if self.refusal else None,
            "audit": self.audit.to_dict(),
            "metrics": self.metrics.to_dict(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MeaningCapsule":
        return MeaningCapsule(
            id=d.get("id", uid("capsule")),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            source_agent=d.get("source_agent", ""),
            content=SemanticContent.from_dict(d.get("content", {})),
            intent=d.get("intent", "unknown"),
            context_refs=list(d.get("context_refs", [])),
            provenance=Provenance.from_dict(d.get("provenance", {})),
            confidence=float(d.get("confidence", 0.0)),
            scope=Scope.from_dict(d.get("scope", {})),
            expiry=parse_dt(d.get("expiry", iso(now_utc() + timedelta(hours=1)))),
            permissions=Permissions.from_dict(d.get("permissions", {})),
            constraints=list(d.get("constraints", [])),
            translation_trace=[
                TranslationStep.from_dict(x) for x in d.get("translation_trace", [])
            ],
            status=CapsuleStatus(d.get("status", CapsuleStatus.ACTIVE.value)),
            refusal=Refusal.from_dict(d["refusal"]) if d.get("refusal") else None,
            audit=AuditMetadata.from_dict(d.get("audit", {})),
            metrics=CapsuleMetrics.from_dict(d.get("metrics", {})),
        )


def make_refusal_capsule(
    *,
    source_capsule: MeaningCapsule,
    target_agent: str,
    reason: RefusalReason,
    explanation: str,
    safe_next_steps: Optional[List[str]] = None,
) -> MeaningCapsule:
    preserved = {
        "source_capsule_id": source_capsule.id,
        "source_agent": source_capsule.source_agent,
        "intent": source_capsule.intent,
        "content_summary": source_capsule.content.text[:300],
        "from_ontology": source_capsule.content.ontology,
    }
    capsule = source_capsule.clone(new_id=True, prefix="refusal")
    capsule.source_agent = target_agent
    capsule.intent = "refuse"
    capsule.status = CapsuleStatus.REFUSED
    capsule.refusal = Refusal(
        reason=reason,
        explanation=explanation,
        preserved_content=preserved,
        safe_next_steps=safe_next_steps or ["preserve_refusal", "request_context", "avoid_forced_translation"],
    )
    capsule.content = SemanticContent(
        text=f"Refusal preserved: {reason.value}. {explanation}",
        ontology="refusal",
        claims=[f"refusal:{reason.value}"],
        assumptions=[],
        unresolved_terms=[],
        data={"preserved": preserved},
    )
    capsule.confidence = 1.0
    capsule.expiry = now_utc() + timedelta(seconds=max(source_capsule.scope.ttl_seconds, 3600))
    capsule.translation_trace.append(
        TranslationStep(
            from_agent=source_capsule.source_agent,
            to_agent=target_agent,
            from_ontology=source_capsule.content.ontology,
            to_ontology="refusal",
            transform="refusal_preservation",
            loss=0.0,
            ambiguity=0.0,
            notes=explanation,
        )
    )
    return capsule


def make_capsule(
    *,
    source_agent: str,
    text: str,
    ontology: str,
    intent: str = "coordinate",
    claims: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    unresolved_terms: Optional[List[str]] = None,
    context_refs: Optional[List[str]] = None,
    source_memory_refs: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    valid_for_agents: Optional[List[str]] = None,
    valid_contexts: Optional[List[str]] = None,
    ttl_seconds: int = 3600,
    risk_level: str = "low",
    allow_translate: bool = True,
    allow_store: bool = True,
    allow_rebroadcast: bool = False,
    require_human_review: bool = False,
    visibility: str = "bounded",
    allowed_agents: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
    confidence: float = 0.8,
    data: Optional[Dict[str, Any]] = None,
) -> MeaningCapsule:
    created = now_utc()
    return MeaningCapsule(
        id=uid("capsule"),
        source_agent=source_agent,
        content=SemanticContent(
            text=text,
            ontology=ontology,
            claims=claims or [],
            assumptions=assumptions or [],
            unresolved_terms=unresolved_terms or [],
            data=data or {},
        ),
        intent=intent,
        context_refs=context_refs or [],
        provenance=Provenance(
            created_by=source_agent,
            created_at=created,
            source_memory_refs=source_memory_refs or [],
            generation_mode="projected",
            evidence_refs=evidence_refs or [],
        ),
        confidence=max(0.0, min(1.0, confidence)),
        scope=Scope(
            valid_for_agents=valid_for_agents or ["*"],
            valid_contexts=valid_contexts or ["general"],
            ttl_seconds=ttl_seconds,
            risk_level=risk_level,
        ),
        expiry=created + timedelta(seconds=ttl_seconds),
        permissions=Permissions(
            allow_translate=allow_translate,
            allow_store=allow_store,
            allow_rebroadcast=allow_rebroadcast,
            require_human_review=require_human_review,
            visibility=visibility,
            allowed_agents=allowed_agents or ["*"],
        ),
        constraints=constraints or ["no_total_state", "no_private_state"],
    )
