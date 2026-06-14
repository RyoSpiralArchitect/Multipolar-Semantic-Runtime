#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from .agents import AgentConfig
from .runtime import RuntimeConfig, MultipolarRuntime


DEFAULT_SCENARIO_DIR = Path("scenarios")


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    queries: List[str]
    agents: List[AgentConfig]
    runtime: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    story: Dict[str, Any] = field(default_factory=dict)
    source_path: Optional[str] = None

    @staticmethod
    def from_dict(raw: Dict[str, Any], *, source_path: Optional[str] = None) -> "Scenario":
        return Scenario(
            id=raw["id"],
            title=raw.get("title", raw["id"]),
            description=raw.get("description", ""),
            queries=list(raw.get("queries", [])),
            agents=[AgentConfig.from_dict(agent) for agent in raw.get("agents", [])],
            runtime=dict(raw.get("runtime", {})),
            tags=list(raw.get("tags", [])),
            notes=list(raw.get("notes", [])),
            story=dict(raw.get("story", {})),
            source_path=source_path,
        )

    def metadata(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "notes": self.notes,
            "story": self.story,
            "source_path": self.source_path,
        }

    def runtime_config(self) -> RuntimeConfig:
        return RuntimeConfig(
            agents=self.agents,
            domination_cap=float(self.runtime.get("domination_cap", 0.55)),
            max_translation_loss=float(self.runtime.get("max_translation_loss", 0.58)),
            max_ambiguity=float(self.runtime.get("max_ambiguity", 0.62)),
            metadata={"scenario": self.metadata()},
        )


def resolve_scenario_path(name_or_path: str | Path, scenario_dir: str | Path = DEFAULT_SCENARIO_DIR) -> Path:
    candidate = Path(name_or_path)
    if candidate.exists():
        return candidate
    if candidate.suffix != ".json":
        candidate = candidate.with_suffix(".json")
    return Path(scenario_dir) / candidate


def load_scenario(name_or_path: str | Path, scenario_dir: str | Path = DEFAULT_SCENARIO_DIR) -> Scenario:
    path = resolve_scenario_path(name_or_path, scenario_dir)
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return Scenario.from_dict(raw, source_path=str(path))


def list_scenarios(scenario_dir: str | Path = DEFAULT_SCENARIO_DIR) -> List[Dict[str, Any]]:
    root = Path(scenario_dir)
    scenarios = []
    for path in sorted(root.glob("*.json")):
        scenario = load_scenario(path, scenario_dir=root)
        scenarios.append(scenario.metadata())
    return scenarios


def run_scenario(
    *,
    scenario: str | Path,
    output_dir: str | Path,
    scenario_dir: str | Path = DEFAULT_SCENARIO_DIR,
    queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    loaded = load_scenario(scenario, scenario_dir=scenario_dir)
    runtime = MultipolarRuntime(loaded.runtime_config())
    active_queries = queries or loaded.queries
    result = runtime.run_experiment(active_queries)
    files = runtime.export(output_dir)

    out = Path(output_dir)
    manifest_path = out / "scenario_manifest.json"
    manifest_path.write_text(json.dumps(loaded.metadata(), ensure_ascii=False, indent=2), encoding="utf-8")
    files["scenario_manifest.json"] = str(manifest_path)

    return {
        "experiment": f"scenario:{loaded.id}",
        "scenario": loaded.metadata(),
        "queries": active_queries,
        "files": files,
        "summary": result["summaries"],
        "overall_ok": runtime.monitor.history[-1]["overall_ok"] if runtime.monitor.history else None,
    }
