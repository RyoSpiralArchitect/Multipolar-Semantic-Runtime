#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from .agents import AgentConfig, AgentRuntime, load_agent_configs
from .protocol import SemanticProtocol, TranslationRegistry, AgentPublicView
from .capsule_bus import MeaningCapsuleBus
from .context_graph import ContextGraphStore
from .conflict_registry import ConflictRegistry
from .invariant_monitor import InvariantMonitor
from .intervention_controller import InterventionController
from .models import CapsuleStatus, MeaningCapsule, json_ready, iso, now_utc


@dataclass
class RuntimeConfig:
    agents: List[AgentConfig]
    domination_cap: float = 0.55
    max_translation_loss: float = 0.58
    max_ambiguity: float = 0.62

    @staticmethod
    def from_file(path: str) -> "RuntimeConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        agents = [AgentConfig.from_dict(a) for a in raw.get("agents", [])]
        runtime = raw.get("runtime", {})
        return RuntimeConfig(
            agents=agents,
            domination_cap=float(runtime.get("domination_cap", 0.55)),
            max_translation_loss=float(runtime.get("max_translation_loss", 0.58)),
            max_ambiguity=float(runtime.get("max_ambiguity", 0.62)),
        )


class MultipolarRuntime:
    """MeaningCapsule Runtime + private ContextGraph memory."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.agents: Dict[str, AgentRuntime] = {cfg.id: AgentRuntime(cfg) for cfg in config.agents}
        self.bus = MeaningCapsuleBus()
        self.memories = ContextGraphStore()
        for cfg in config.agents:
            self.memories.ensure(cfg.id, cfg.ontology)
        self.protocol = SemanticProtocol(
            TranslationRegistry.default(),
            max_translation_loss=config.max_translation_loss,
            max_ambiguity=config.max_ambiguity,
        )
        self.conflicts = ConflictRegistry()
        self.interventions = InterventionController()
        self.monitor = InvariantMonitor(domination_cap=config.domination_cap)
        self.rounds: List[Dict[str, Any]] = []

    def public_view(self, agent_id: str) -> AgentPublicView:
        cfg = self.agents[agent_id].cfg
        return AgentPublicView(
            id=cfg.id,
            role=cfg.role,
            ontology=cfg.ontology,
            constraints=cfg.constraints,
            trust=cfg.trust,
        )

    def publish_from_agent(self, agent_id: str, query: str) -> MeaningCapsule:
        agent = self.agents[agent_id]
        capsule = agent.project(query)
        self.bus.publish(capsule)

        # Do not leave an unsafe projection active at its source. It can still be
        # preserved and routed as quarantine evidence, but not treated as valid consensus.
        reason = self.protocol.safety_quarantine_reason(capsule)
        if reason:
            self.bus.quarantine(capsule, reason)
            rec = self.interventions.quarantine_capsule(capsule, reason)
            capsule.audit.intervention_ids.append(rec.id)
            self.bus.capsules[capsule.id] = capsule

        self._observe_conflicts(capsule)
        return capsule

    def route_capsule(self, capsule: MeaningCapsule, target_agent_id: str) -> MeaningCapsule:
        target_view = self.public_view(target_agent_id)
        routed = self.protocol.route(capsule, target_view)

        # Routed capsule may be translated/refusal/quarantine.
        if routed.id not in self.bus.capsules:
            self.bus.publish(routed)

        if routed.status == CapsuleStatus.QUARANTINED:
            rec = self.interventions.quarantine_capsule(
                routed,
                routed.audit.quarantine_reason or "protocol quarantine",
            )
            routed.audit.intervention_ids.append(rec.id)
            self.bus.capsules[routed.id] = routed
            route_kind = "quarantine_delivered"
        elif routed.status == CapsuleStatus.REFUSED:
            route_kind = "refusal_delivered"
        elif routed.status == CapsuleStatus.EXPIRED:
            route_kind = "expired_delivered"
        else:
            route_kind = "delivered"

        self.bus.deliver(routed, target_agent_id, route_kind=route_kind)

        target = self.agents[target_agent_id]
        trust = target.trust_for(capsule.source_agent)
        if routed.permissions.allow_store or routed.status in {CapsuleStatus.REFUSED, CapsuleStatus.QUARANTINED}:
            self.memories.update_with_capsule(target_agent_id, routed, trust=trust)

        self._observe_conflicts(routed)
        return routed

    def _observe_conflicts(self, capsule: MeaningCapsule) -> None:
        new_conflicts = self.conflicts.observe(capsule)
        for conflict in new_conflicts:
            for agent_id in self.agents:
                self.memories.retain_conflict(
                    agent_id,
                    conflict.id,
                    conflict.capsule_ids,
                    "; ".join(conflict.claims),
                )

    def run_round(self, query: str, *, include_agents: Optional[List[str]] = None) -> Dict[str, Any]:
        include_agents = include_agents or list(self.agents)
        before = self.to_dict(include_snapshots=False)
        self.interventions.snapshot(f"before_round_{len(self.rounds)+1}", before)

        produced: List[MeaningCapsule] = []
        routed_count = 0

        for agent_id in include_agents:
            if agent_id in self.interventions.isolated_agents:
                continue
            produced.append(self.publish_from_agent(agent_id, query))

        for capsule in list(produced):
            for target_id in self.agents:
                if target_id == capsule.source_agent:
                    continue
                if target_id in self.interventions.isolated_agents:
                    continue
                self.route_capsule(capsule, target_id)
                routed_count += 1

        results = self.monitor.check(
            bus=self.bus,
            memories=self.memories,
            conflicts=self.conflicts,
            interventions=self.interventions,
            expected_agents=list(self.agents),
        )

        summary = {
            "round": len(self.rounds) + 1,
            "query": query,
            "produced_capsules": [c.id for c in produced],
            "routed_count": routed_count,
            "invariants": self.monitor.summarize(results),
        }
        self.rounds.append(summary)
        return summary

    def run_experiment(self, queries: List[str]) -> Dict[str, Any]:
        summaries = []
        for q in queries:
            summaries.append(self.run_round(q))
        return {
            "summaries": summaries,
            "final": self.to_dict(),
        }

    def to_dict(self, *, include_snapshots: bool = True) -> Dict[str, Any]:
        data = {
            "runtime": {
                "generated_at": iso(now_utc()),
                "agents": [
                    {
                        "id": a.cfg.id,
                        "role": a.cfg.role,
                        "ontology": a.cfg.ontology,
                        "model_backend": a.cfg.model.backend,
                        "model_path": a.cfg.model.path,
                        "behavior": a.cfg.behavior,
                    }
                    for a in self.agents.values()
                ],
            },
            "bus": self.bus.to_dict(),
            "context_graphs": self.memories.to_dict(),
            "conflicts": self.conflicts.to_dict(),
            "interventions": self.interventions.to_dict(),
            "rounds": self.rounds,
        }
        if not include_snapshots:
            data["interventions"] = {
                **data["interventions"],
                "snapshots": "[omitted]",
            }
        return json_ready(data)

    def export(self, output_dir: str | Path) -> Dict[str, str]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "context_graphs").mkdir(exist_ok=True)

        state = self.to_dict()
        files: Dict[str, str] = {}

        def write_json(name: str, obj: Any) -> None:
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(json_ready(obj), ensure_ascii=False, indent=2), encoding="utf-8")
            files[name] = str(path)

        write_json("runtime_state.json", state)
        write_json("capsule_log.json", self.bus.to_dict())
        write_json("conflict_registry.json", self.conflicts.to_dict())
        write_json("intervention_log.json", self.interventions.to_dict())

        latest_results = self.monitor.history[-1]["results"] if self.monitor.history else []
        write_json("invariant_report.json", {
            "history": self.monitor.history,
            "latest": latest_results,
            "overall_ok": self.monitor.history[-1]["overall_ok"] if self.monitor.history else None,
        })

        for agent_id, graph in self.memories.graphs.items():
            write_json(f"context_graphs/{agent_id}.json", graph.to_dict())

        # Lightweight Graphviz DOT.
        dot_lines = ["digraph MultipolarRuntime {", "  rankdir=LR;"]
        for agent_id in self.agents:
            dot_lines.append(f'  "{agent_id}" [shape=box];')
        for delivery in self.bus.deliveries:
            src = delivery["source_agent"]
            tgt = delivery["target_agent"]
            label = delivery["status"]
            dot_lines.append(f'  "{src}" -> "{tgt}" [label="{label}"];')
        dot_lines.append("}")
        dot_path = out / "runtime_graph.dot"
        dot_path.write_text("\n".join(dot_lines), encoding="utf-8")
        files["runtime_graph.dot"] = str(dot_path)

        return files
