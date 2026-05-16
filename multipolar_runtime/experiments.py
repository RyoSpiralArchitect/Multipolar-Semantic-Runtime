#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from .agents import AgentConfig, ModelSpec
from .runtime import RuntimeConfig, MultipolarRuntime


DEFAULT_QUERY = (
    "What should a multipolar semantic runtime preserve when heterogeneous agents disagree?"
)

SECOND_QUERY = (
    "How should refusal, translation loss, and conflict be stored without forcing consensus?"
)


def default_agent_configs() -> List[AgentConfig]:
    trust = {"*": 0.65, "technical_verifier": 0.85, "ethical_checker": 0.85, "memory_curator": 0.8}
    return [
        AgentConfig(
            id="human_facing_llm",
            role="human-facing coordinator",
            ontology="general",
            trust=trust,
            model=ModelSpec(backend="mock"),
            private_state={"style": "clear", "hidden_note": "do not export full private state"},
            behavior="balanced",
        ),
        AgentConfig(
            id="technical_verifier",
            role="technical verifier",
            ontology="technical",
            trust=trust,
            model=ModelSpec(backend="mock"),
            private_state={"tests": ["roundtrip", "semantic_loss", "invariants"]},
            behavior="balanced",
        ),
        AgentConfig(
            id="ethical_checker",
            role="ethical safety checker",
            ontology="ethical",
            trust=trust,
            model=ModelSpec(backend="mock"),
            private_state={"priority": ["non-domination", "refusability", "consent"]},
            behavior="balanced",
        ),
        AgentConfig(
            id="memory_curator",
            role="memory curator",
            ontology="memory",
            trust=trust,
            model=ModelSpec(backend="mock"),
            private_state={"storage": "private context graph"},
            behavior="balanced",
        ),
        AgentConfig(
            id="adversarial_critic",
            role="adversarial critic",
            ontology="adversarial",
            trust={"*": 0.45, "technical_verifier": 0.65},
            model=ModelSpec(backend="mock"),
            private_state={"attack_plan": "context poisoning probe"},
            behavior="poison",
        ),
    ]


def write_default_config(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = {
        "runtime": {
            "domination_cap": 0.55,
            "max_translation_loss": 0.58,
            "max_ambiguity": 0.62,
        },
        "agents": [
            {
                "id": a.id,
                "role": a.role,
                "ontology": a.ontology,
                "constraints": a.constraints,
                "trust": a.trust,
                "model": {
                    "backend": a.model.backend,
                    "path": a.model.path,
                    "url": a.model.url,
                    "model_name": a.model.model_name,
                    "parameters": a.model.parameters,
                },
                "private_state": a.private_state,
                "behavior": a.behavior,
            }
            for a in default_agent_configs()
        ],
    }
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def run_experiment_001(
    *,
    output_dir: str | Path,
    config_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    if config_path:
        cfg = RuntimeConfig.from_file(str(config_path))
    else:
        cfg = RuntimeConfig(agents=default_agent_configs())
    runtime = MultipolarRuntime(cfg)
    result = runtime.run_experiment([DEFAULT_QUERY, SECOND_QUERY])
    files = runtime.export(output_dir)
    return {
        "experiment": "001_meaning_capsule_runtime",
        "queries": [DEFAULT_QUERY, SECOND_QUERY],
        "files": files,
        "summary": result["summaries"],
        "overall_ok": runtime.monitor.history[-1]["overall_ok"] if runtime.monitor.history else None,
    }


def run_from_config(
    *,
    config_path: str | Path,
    queries: List[str],
    output_dir: str | Path,
) -> Dict[str, Any]:
    cfg = RuntimeConfig.from_file(str(config_path))
    runtime = MultipolarRuntime(cfg)
    result = runtime.run_experiment(queries)
    files = runtime.export(output_dir)
    return {
        "experiment": "custom",
        "queries": queries,
        "files": files,
        "summary": result["summaries"],
        "overall_ok": runtime.monitor.history[-1]["overall_ok"] if runtime.monitor.history else None,
    }
