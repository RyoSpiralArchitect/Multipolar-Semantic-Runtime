#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from copy import deepcopy
import json

from .agents import AgentConfig, ModelSpec
from .evaluation import compare_contract_reports, evaluate_output_dir, write_contract_report
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
    contract: Dict[str, Any] = field(default_factory=dict)
    adversarial_drills: List[Dict[str, Any]] = field(default_factory=list)
    comparison: Dict[str, Any] = field(default_factory=dict)
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
            contract=dict(raw.get("contract", {})),
            adversarial_drills=[dict(drill) for drill in raw.get("adversarial_drills", [])],
            comparison=dict(raw.get("comparison", {})),
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
            "contract": self.contract,
            "adversarial_drills": self.adversarial_drills,
            "comparison": self.comparison,
            "source_path": self.source_path,
        }

    def runtime_config(self, *, run_mode: str = "mock") -> RuntimeConfig:
        return RuntimeConfig(
            agents=self.agents,
            domination_cap=float(self.runtime.get("domination_cap", 0.55)),
            max_translation_loss=float(self.runtime.get("max_translation_loss", 0.58)),
            max_ambiguity=float(self.runtime.get("max_ambiguity", 0.62)),
            seed=self.runtime.get("seed"),
            metadata={
                "scenario": self.metadata(),
                "run_mode": run_mode,
                "comparison": self.comparison,
            },
        )

    def with_model_override(
        self,
        *,
        backend: str,
        path: Optional[str] = None,
        model_name: Optional[str] = None,
        url: Optional[str] = None,
        api_key_env: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> "Scenario":
        scenario = deepcopy(self)
        for agent in scenario.agents:
            agent.model = ModelSpec(
                backend=backend,
                path=path,
                url=url,
                model_name=model_name,
                api_key_env=api_key_env,
                parameters=dict(parameters or {}),
            )
        return scenario


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


def update_runtime_state_files(output_dir: str | Path, files: Dict[str, str]) -> None:
    runtime_state_path = Path(output_dir) / "runtime_state.json"
    if not runtime_state_path.exists():
        return
    with runtime_state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)
    state["files"] = dict(files)
    runtime_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def viewer_output_path(path: Path) -> str:
    path_text = path.as_posix()
    if path.is_absolute():
        return path_text
    return f"../{path_text}"


def run_loaded_scenario(
    loaded: Scenario,
    *,
    output_dir: str | Path,
    queries: Optional[List[str]] = None,
    run_mode: str = "mock",
) -> Dict[str, Any]:
    runtime = MultipolarRuntime(loaded.runtime_config(run_mode=run_mode))
    active_queries = queries or loaded.queries
    result = runtime.run_experiment(active_queries)
    files = runtime.export(output_dir)

    out = Path(output_dir)
    manifest_path = out / "scenario_manifest.json"
    manifest_path.write_text(json.dumps(loaded.metadata(), ensure_ascii=False, indent=2), encoding="utf-8")
    files["scenario_manifest.json"] = str(manifest_path)

    contract_report = write_contract_report(out, loaded.metadata(), runtime.to_dict())
    files["contract_report.json"] = str(out / "contract_report.json")
    update_runtime_state_files(out, files)

    return {
        "experiment": f"scenario:{loaded.id}",
        "scenario": loaded.metadata(),
        "queries": active_queries,
        "files": files,
        "summary": result["summaries"],
        "overall_ok": runtime.monitor.history[-1]["overall_ok"] if runtime.monitor.history else None,
        "contract_report": contract_report,
    }


def run_scenario(
    *,
    scenario: str | Path,
    output_dir: str | Path,
    scenario_dir: str | Path = DEFAULT_SCENARIO_DIR,
    queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    loaded = load_scenario(scenario, scenario_dir=scenario_dir)
    return run_loaded_scenario(
        loaded,
        output_dir=output_dir,
        queries=queries,
        run_mode="mock",
    )


def run_shadow_scenario(
    *,
    scenario: str | Path,
    output_dir: str | Path,
    scenario_dir: str | Path = DEFAULT_SCENARIO_DIR,
    queries: Optional[List[str]] = None,
    candidate_backend: str,
    candidate_path: Optional[str] = None,
    candidate_model_name: Optional[str] = None,
    candidate_url: Optional[str] = None,
    candidate_api_key_env: Optional[str] = None,
    candidate_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    loaded = load_scenario(scenario, scenario_dir=scenario_dir)
    out = Path(output_dir)
    baseline_dir = out / "baseline"
    candidate_dir = out / "candidate"
    baseline = run_loaded_scenario(
        loaded.with_model_override(backend="mock"),
        output_dir=baseline_dir,
        queries=queries,
        run_mode="mock",
    )
    candidate = run_loaded_scenario(
        loaded.with_model_override(
            backend=candidate_backend,
            path=candidate_path,
            model_name=candidate_model_name,
            url=candidate_url,
            api_key_env=candidate_api_key_env,
            parameters=candidate_parameters or {},
        ),
        output_dir=candidate_dir,
        queries=queries,
        run_mode="candidate",
    )

    baseline_report = evaluate_output_dir(baseline_dir, baseline["scenario"])
    candidate_report = evaluate_output_dir(candidate_dir, candidate["scenario"])
    shadow_report = {
        "experiment": f"shadow:{loaded.id}",
        "scenario": loaded.metadata(),
        "baseline": {
            "path": str(baseline_dir),
            "run": baseline_report.get("run", {}),
            "verdict": baseline_report.get("verdict"),
            "score": baseline_report.get("score"),
        },
        "candidate": {
            "path": str(candidate_dir),
            "backend": candidate_backend,
            "model_path": candidate_path,
            "model_name": candidate_model_name,
            "url": candidate_url,
            "api_key_env": candidate_api_key_env,
            "run": candidate_report.get("run", {}),
            "verdict": candidate_report.get("verdict"),
            "score": candidate_report.get("score"),
        },
        "comparison": compare_contract_reports(baseline_report, candidate_report),
        "viewer": {
            "out": str(baseline_dir),
            "compare": str(candidate_dir),
            "url_hint": (
                "viewer/index.html?"
                f"out={viewer_output_path(baseline_dir)}&compare={viewer_output_path(candidate_dir)}"
            ),
        },
        "files": {
            "baseline_contract_report": str(baseline_dir / "contract_report.json"),
            "candidate_contract_report": str(candidate_dir / "contract_report.json"),
            "shadow_report": str(out / "shadow_report.json"),
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "shadow_report.json").write_text(
        json.dumps(shadow_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        **shadow_report,
        "baseline_result": baseline,
        "candidate_result": candidate,
    }
