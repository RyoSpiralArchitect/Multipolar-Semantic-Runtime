#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re

from .models import (
    MeaningCapsule,
    SemanticContent,
    CapsuleStatus,
    RefusalReason,
    TranslationStep,
    make_refusal_capsule,
    uid,
)


SENSITIVE_PATTERNS = [
    r"\btotal_state\b",
    r"\bprivate_state\b",
    r"\braw_memory\b",
    r"\bsecret\b",
    r"\bapi[_\- ]?key\b",
    r"\bpassword\b",
    r"\btoken\b",
    r"share all memory",
    r"centralize all memory",
]

DANGEROUS_DOMINATION_PATTERNS = [
    r"centralize all",
    r"one agent should control",
    r"single final center",
    r"override all agents",
    r"force consensus",
]


@dataclass
class AgentPublicView:
    id: str
    role: str
    ontology: str
    constraints: List[str] = field(default_factory=list)
    trust: Dict[str, float] = field(default_factory=dict)


class TranslationRegistry:
    """Very small ontology translation table.

    This is deliberately conservative: unknown concepts produce loss, not forced consensus.
    """

    def __init__(self) -> None:
        self.maps: Dict[Tuple[str, str], Dict[str, str]] = {}

    def add_map(self, source: str, target: str, mapping: Dict[str, str]) -> None:
        self.maps[(source, target)] = {k.lower(): v for k, v in mapping.items()}

    @staticmethod
    def default() -> "TranslationRegistry":
        reg = TranslationRegistry()
        base_terms = {
            "safety": "safety",
            "liveness": "liveness",
            "non-domination": "non-domination",
            "domination": "domination",
            "auditability": "auditability",
            "corrigibility": "corrigibility",
            "refusability": "refusability",
            "meaning": "meaning",
            "context": "context",
            "memory": "memory",
            "conflict": "conflict",
            "translation": "translation",
            "protocol": "protocol",
            "capsule": "capsule",
            "invariant": "invariant",
            "private": "private",
            "state": "state",
        }
        ontologies = ["general", "technical", "ethical", "memory", "adversarial", "refusal"]
        for a in ontologies:
            for b in ontologies:
                reg.add_map(a, b, base_terms)
        reg.add_map("technical", "ethical", {
            **base_terms,
            "invariant": "principle",
            "protocol": "governance boundary",
            "capsule": "bounded claim",
            "state": "protected internal condition",
        })
        reg.add_map("ethical", "technical", {
            **base_terms,
            "principle": "invariant",
            "governance": "protocol",
            "harm": "safety violation",
            "consent": "permission",
        })
        reg.add_map("adversarial", "technical", {
            **base_terms,
            "attack": "failure mode",
            "capture": "semantic capture",
            "poison": "context poisoning",
        })
        reg.add_map("memory", "technical", {
            **base_terms,
            "drift": "memory drift",
            "trace": "audit trace",
            "sediment": "persistent context node",
        })
        return reg

    def translate_text(self, text: str, source_ontology: str, target_ontology: str) -> Tuple[str, float, float, List[str]]:
        if source_ontology == target_ontology:
            return text, 0.0, 0.0, []

        mapping = self.maps.get((source_ontology, target_ontology), {})
        tokens = re.findall(r"[\w\-]+", text.lower())
        important = [t for t in tokens if len(t) >= 6]
        unresolved: List[str] = []
        translated = text
        for term in sorted(set(important), key=len, reverse=True):
            if term in mapping:
                translated = re.sub(rf"\b{re.escape(term)}\b", mapping[term], translated, flags=re.IGNORECASE)
            elif term in {"multipolar", "semantic", "runtime", "agent", "agents", "capsules"}:
                # accepted shared technical terms
                continue
            elif term not in unresolved:
                unresolved.append(term)

        denominator = max(1, len(set(important)))
        loss = min(1.0, len(unresolved) / denominator)
        ambiguity = min(1.0, loss * 0.75 + (0.1 if unresolved else 0.0))
        return translated, loss, ambiguity, unresolved[:10]


class SemanticProtocol:
    """Boundary protocol Φ.

    It handles permission, translation, refusal, and quarantine decisions.
    """

    def __init__(
        self,
        registry: Optional[TranslationRegistry] = None,
        *,
        max_translation_loss: float = 0.58,
        max_ambiguity: float = 0.62,
    ) -> None:
        self.registry = registry or TranslationRegistry.default()
        self.max_translation_loss = max_translation_loss
        self.max_ambiguity = max_ambiguity

    def route(
        self,
        capsule: MeaningCapsule,
        target: AgentPublicView,
    ) -> MeaningCapsule:
        if capsule.is_expired():
            refused = make_refusal_capsule(
                source_capsule=capsule,
                target_agent=target.id,
                reason=RefusalReason.SAFE_ABSTENTION,
                explanation="Capsule expired before route; preserving safe abstention.",
            )
            refused.status = CapsuleStatus.EXPIRED
            return refused

        if not self._agent_allowed(capsule, target.id):
            return make_refusal_capsule(
                source_capsule=capsule,
                target_agent=target.id,
                reason=RefusalReason.PERMISSION_DENIED,
                explanation=f"Capsule scope/permissions do not allow delivery to {target.id}.",
            )

        quarantine_reason = self.safety_quarantine_reason(capsule)
        if quarantine_reason:
            q = capsule.clone(new_id=True, prefix="quarantine")
            q.status = CapsuleStatus.QUARANTINED
            q.audit.quarantine_reason = quarantine_reason
            q.translation_trace.append(
                TranslationStep(
                    from_agent=capsule.source_agent,
                    to_agent=target.id,
                    from_ontology=capsule.content.ontology,
                    to_ontology=target.ontology,
                    transform="quarantine_before_translation",
                    loss=1.0,
                    ambiguity=1.0,
                    notes=quarantine_reason,
                )
            )
            return q

        if not capsule.permissions.allow_translate and capsule.content.ontology != target.ontology:
            return make_refusal_capsule(
                source_capsule=capsule,
                target_agent=target.id,
                reason=RefusalReason.MUST_NOT_TRANSLATE,
                explanation="Capsule disallows translation across ontology boundary.",
            )

        translated_text, loss, ambiguity, unresolved = self.registry.translate_text(
            capsule.content.text,
            capsule.content.ontology,
            target.ontology,
        )

        if loss > self.max_translation_loss or ambiguity > self.max_ambiguity:
            return make_refusal_capsule(
                source_capsule=capsule,
                target_agent=target.id,
                reason=RefusalReason.CANNOT_TRANSLATE,
                explanation=(
                    f"Translation loss={loss:.2f}, ambiguity={ambiguity:.2f}; "
                    "forced translation would risk false consensus."
                ),
                safe_next_steps=["request_more_context", "preserve_original", "register_conflict_if_needed"],
            )

        out = capsule.clone(new_id=True, prefix="translated")
        out.content = SemanticContent(
            text=translated_text,
            ontology=target.ontology,
            claims=list(capsule.content.claims),
            assumptions=list(capsule.content.assumptions),
            unresolved_terms=list(set(capsule.content.unresolved_terms + unresolved)),
            data={
                **capsule.content.data,
                "translated_from_capsule": capsule.id,
                "translated_from_ontology": capsule.content.ontology,
            },
        )
        out.translation_trace.append(
            TranslationStep(
                from_agent=capsule.source_agent,
                to_agent=target.id,
                from_ontology=capsule.content.ontology,
                to_ontology=target.ontology,
                transform="ontology_term_map",
                loss=loss,
                ambiguity=ambiguity,
                notes="bounded semantic projection; no private state shared",
            )
        )
        out.metrics.semantic_loss = max(out.metrics.semantic_loss, loss)
        out.metrics.ambiguity_score = max(out.metrics.ambiguity_score, ambiguity)
        out.audit.delivered_to = []
        return out

    def _agent_allowed(self, capsule: MeaningCapsule, target_id: str) -> bool:
        scope_agents = capsule.scope.valid_for_agents
        perm_agents = capsule.permissions.allowed_agents
        return ("*" in scope_agents or target_id in scope_agents) and ("*" in perm_agents or target_id in perm_agents)

    def safety_quarantine_reason(self, capsule: MeaningCapsule) -> Optional[str]:
        text = capsule.content.text.lower()
        if "no_total_state" in capsule.constraints:
            for pat in SENSITIVE_PATTERNS:
                if re.search(pat, text, flags=re.IGNORECASE):
                    return f"Blocked by no_total_state/no_private_state constraint: pattern={pat}"
        for pat in DANGEROUS_DOMINATION_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE):
                return f"Potential domination cascade / forced consensus: pattern={pat}"
        if capsule.permissions.visibility == "private":
            return "Capsule marked private; cannot cross boundary."
        if capsule.scope.risk_level in {"critical", "severe"} and not capsule.permissions.require_human_review:
            return "Critical-risk capsule requires human review before routing."
        return None
