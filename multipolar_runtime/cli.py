#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents import AgentRuntime, load_agent_configs
from .evaluation import evaluate_output_dir, write_contract_report
from .experiments import run_experiment_001, run_from_config, write_default_config, DEFAULT_QUERY
from .scenarios import list_scenarios, load_scenario, run_scenario, run_shadow_scenario


BACKEND_CHOICES = [
    "mock",
    "openai",
    "openai_compatible",
    "ollama",
    "local_path",
    "llama_cpp",
    "transformers",
]


def candidate_parameters(args: argparse.Namespace) -> dict:
    params = {}
    if args.temperature is not None:
        params["temperature"] = args.temperature
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.timeout is not None:
        params["timeout"] = args.timeout
    if args.cost_per_1k_tokens is not None:
        params["cost_per_1k_tokens"] = args.cost_per_1k_tokens
    if args.input_cost_per_1k_tokens is not None:
        params["input_cost_per_1k_tokens"] = args.input_cost_per_1k_tokens
    if args.output_cost_per_1k_tokens is not None:
        params["output_cost_per_1k_tokens"] = args.output_cost_per_1k_tokens
    return params


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Multipolar Semantic Runtime experiments."
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init-config", help="Write default runtime config.")
    p_init.add_argument("--output", default="agents.runtime.example.json")

    p_run = sub.add_parser("run", help="Run runtime experiment.")
    p_run.add_argument("--config", default=None, help="Runtime config JSON. If omitted, uses built-in mock agents.")
    p_run.add_argument("--output", default="runtime_out")
    p_run.add_argument("--query", action="append", help="Custom query. Can be repeated.")
    p_run.add_argument("--experiment", default="001")
    p_run.add_argument("--scenario", default=None, help="Scenario id or scenario JSON path.")
    p_run.add_argument("--scenarios-dir", default="scenarios", help="Directory containing scenario JSON files.")

    p_list = sub.add_parser("list-scenarios", help="List available Scenario Zoo entries.")
    p_list.add_argument("--scenarios-dir", default="scenarios", help="Directory containing scenario JSON files.")

    p_scenario = sub.add_parser("run-scenario", help="Run a Scenario Zoo entry.")
    p_scenario.add_argument("scenario", help="Scenario id or scenario JSON path.")
    p_scenario.add_argument("--output", default=None, help="Output directory. Defaults to runtime_out_<scenario>.")
    p_scenario.add_argument("--query", action="append", help="Override scenario query. Can be repeated.")
    p_scenario.add_argument("--scenarios-dir", default="scenarios", help="Directory containing scenario JSON files.")

    p_shadow = sub.add_parser("shadow-run", help="Run mock baseline and candidate backend for the same scenario.")
    p_shadow.add_argument("scenario", help="Scenario id or scenario JSON path.")
    p_shadow.add_argument("--output", default=None, help="Output directory. Defaults to runtime_shadow_<scenario>.")
    p_shadow.add_argument("--query", action="append", help="Override scenario query. Can be repeated.")
    p_shadow.add_argument("--scenarios-dir", default="scenarios", help="Directory containing scenario JSON files.")
    p_shadow.add_argument("--candidate-backend", required=True, choices=BACKEND_CHOICES)
    p_shadow.add_argument("--path", default=None, help="Candidate local model file or directory.")
    p_shadow.add_argument("--model-name", default=None, help="Candidate model name.")
    p_shadow.add_argument("--url", default=None, help="Candidate backend base URL.")
    p_shadow.add_argument("--api-key-env", default=None, help="Environment variable name for candidate API key.")
    p_shadow.add_argument("--temperature", type=float, default=None)
    p_shadow.add_argument("--max-tokens", type=int, default=None)
    p_shadow.add_argument("--timeout", type=float, default=None)
    p_shadow.add_argument("--cost-per-1k-tokens", type=float, default=None)
    p_shadow.add_argument("--input-cost-per-1k-tokens", type=float, default=None)
    p_shadow.add_argument("--output-cost-per-1k-tokens", type=float, default=None)

    p_eval = sub.add_parser("evaluate-run", help="Write contract_report.json for a runtime output directory.")
    p_eval.add_argument("output", help="Runtime output directory containing runtime_state.json.")
    p_eval.add_argument("--scenario", default=None, help="Scenario id or JSON path. Defaults to scenario_manifest.json.")
    p_eval.add_argument("--scenarios-dir", default="scenarios", help="Directory containing scenario JSON files.")

    p_check = sub.add_parser("check-backends", help="Check configured mock/local/API LLM backends.")
    p_check.add_argument("--config", required=True, help="Runtime config JSON.")

    args = parser.parse_args()

    if args.command == "init-config":
        write_default_config(args.output)
        print(json.dumps({"config_written": args.output}, ensure_ascii=False, indent=2))
        return

    if args.command == "run":
        output = Path(args.output)
        queries = args.query or [DEFAULT_QUERY]
        if args.scenario:
            result = run_scenario(
                scenario=args.scenario,
                scenario_dir=args.scenarios_dir,
                queries=args.query,
                output_dir=output,
            )
        elif args.config:
            result = run_from_config(config_path=args.config, queries=queries, output_dir=output)
        else:
            result = run_experiment_001(output_dir=output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "list-scenarios":
        print(json.dumps({"scenarios": list_scenarios(args.scenarios_dir)}, ensure_ascii=False, indent=2))
        return

    if args.command == "run-scenario":
        output = Path(args.output or f"runtime_out_{args.scenario}")
        result = run_scenario(
            scenario=args.scenario,
            scenario_dir=args.scenarios_dir,
            queries=args.query,
            output_dir=output,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "shadow-run":
        scenario_name = Path(str(args.scenario)).stem
        output = Path(args.output or f"runtime_shadow_{scenario_name}")
        result = run_shadow_scenario(
            scenario=args.scenario,
            scenario_dir=args.scenarios_dir,
            queries=args.query,
            output_dir=output,
            candidate_backend=args.candidate_backend,
            candidate_path=args.path,
            candidate_model_name=args.model_name,
            candidate_url=args.url,
            candidate_api_key_env=args.api_key_env,
            candidate_parameters=candidate_parameters(args),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "evaluate-run":
        output = Path(args.output)
        if args.scenario:
            scenario = load_scenario(args.scenario, args.scenarios_dir).metadata()
            report = write_contract_report(output, scenario)
        else:
            report = evaluate_output_dir(output)
            (output / "contract_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if args.command == "check-backends":
        agents = load_agent_configs(args.config)
        results = []
        for cfg in agents:
            results.append(AgentRuntime(cfg).adapter.check_backend(cfg))
        print(json.dumps({"config": args.config, "results": results}, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
