#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents import AgentRuntime, load_agent_configs
from .experiments import run_experiment_001, run_from_config, write_default_config, DEFAULT_QUERY


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
        if args.config:
            result = run_from_config(config_path=args.config, queries=queries, output_dir=output)
        else:
            result = run_experiment_001(output_dir=output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
