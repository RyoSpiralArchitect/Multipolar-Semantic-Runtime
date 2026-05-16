#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Iterable
from datetime import datetime

from .models import MeaningCapsule, CapsuleStatus, uid, now_utc, iso, json_ready


@dataclass
class BusEvent:
    id: str
    at: datetime
    kind: str
    capsule_id: Optional[str] = None
    source_agent: Optional[str] = None
    target_agent: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_ready(asdict(self))


class MeaningCapsuleBus:
    """In-memory capsule bus.

    It records publication and delivery without merging private states.
    """

    def __init__(self) -> None:
        self.capsules: Dict[str, MeaningCapsule] = {}
        self.events: List[BusEvent] = []
        self.deliveries: List[Dict[str, Any]] = []

    def emit_event(
        self,
        kind: str,
        *,
        capsule_id: Optional[str] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        event = BusEvent(
            id=uid("evt"),
            at=now_utc(),
            kind=kind,
            capsule_id=capsule_id,
            source_agent=source_agent,
            target_agent=target_agent,
            payload=payload or {},
        )
        self.events.append(event)
        return event.id

    def publish(self, capsule: MeaningCapsule) -> str:
        if capsule.is_expired():
            capsule.mark_expired()
            self.emit_event(
                "expired_before_publish",
                capsule_id=capsule.id,
                source_agent=capsule.source_agent,
            )
        capsule.audit.received_at = now_utc()
        self.capsules[capsule.id] = capsule
        self.emit_event(
            "published",
            capsule_id=capsule.id,
            source_agent=capsule.source_agent,
            payload={"status": capsule.status.value, "intent": capsule.intent},
        )
        return capsule.id

    def deliver(self, capsule: MeaningCapsule, target_agent: str, *, route_kind: str = "delivered") -> None:
        capsule.audit.delivered_to.append(target_agent)
        self.deliveries.append({
            "at": iso(now_utc()),
            "capsule_id": capsule.id,
            "source_agent": capsule.source_agent,
            "target_agent": target_agent,
            "status": capsule.status.value,
            "route_kind": route_kind,
        })
        self.emit_event(
            route_kind,
            capsule_id=capsule.id,
            source_agent=capsule.source_agent,
            target_agent=target_agent,
            payload={"status": capsule.status.value},
        )

    def quarantine(self, capsule: MeaningCapsule, reason: str) -> MeaningCapsule:
        capsule.status = CapsuleStatus.QUARANTINED
        capsule.audit.quarantine_reason = reason
        self.capsules[capsule.id] = capsule
        self.emit_event(
            "quarantined",
            capsule_id=capsule.id,
            source_agent=capsule.source_agent,
            payload={"reason": reason},
        )
        return capsule

    def active_capsules(self) -> List[MeaningCapsule]:
        return [c for c in self.capsules.values() if c.status == CapsuleStatus.ACTIVE and not c.is_expired()]

    def all_capsules(self) -> List[MeaningCapsule]:
        return list(self.capsules.values())

    def by_source(self) -> Dict[str, List[MeaningCapsule]]:
        out: Dict[str, List[MeaningCapsule]] = {}
        for c in self.capsules.values():
            out.setdefault(c.source_agent, []).append(c)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capsules": [c.to_dict() for c in self.capsules.values()],
            "events": [e.to_dict() for e in self.events],
            "deliveries": self.deliveries,
        }
