# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Command line for public collection, offline verification, and the performance refusal."""

from __future__ import annotations

import argparse
import json
import sys

from bybit_research.collect import build_official_plan, execute
from bybit_research.config import proposed_config, proposed_config_hash
from bybit_research.engine import MarketPerformanceNotAuthorized, run_market_performance
from bybit_research.jsonutil import dumps_pretty
from bybit_research.report import report_skeleton
from bybit_research.sufficiency import assess, render_markdown
from bybit_research.verify import VerifyError, verify_bundle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bybit_research")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--output", required=True)
    collect.add_argument("--resume", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", required=True)
    sufficiency = commands.add_parser("sufficiency")
    sufficiency.add_argument("--bundle", required=True)
    commands.add_parser("skeleton")
    commands.add_parser("performance")
    commands.add_parser("config-hash")
    live = commands.add_parser("live", help="Finite public ticker display. Does not open a socket unless both flags are set.")
    live.add_argument("--confirm-public-network", action="store_true")
    live.add_argument("--seconds", type=int)
    live.add_argument("--event-log")
    live.add_argument("--receive-stale-ms", type=int, default=5_000)
    live.add_argument("--exchange-stale-ms", type=int, default=15_000)
    live.add_argument("--ping-interval-ms", type=int, default=20_000)
    live.add_argument("--pong-timeout-ms", type=int, default=10_000)
    live.add_argument("--max-reconnects", type=int, default=8)
    commands.add_parser("plan")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            manifest = execute(build_official_plan(), args.output, resume=args.resume)
            sys.stdout.write(dumps_pretty(manifest).decode())
            if manifest["result"] == "blocked":
                return 4
            return 0 if manifest["strict_sufficient_for_primary"] else 1
        if args.command == "verify":
            sys.stdout.write(dumps_pretty(verify_bundle(args.bundle)).decode())
            return 0
        if args.command == "sufficiency":
            report = assess(args.bundle)
            sys.stdout.write(render_markdown(report))
            return 0 if report["strict_sufficient_for_primary"] else 1
        if args.command == "skeleton":
            sys.stdout.write(dumps_pretty(report_skeleton()).decode())
            return 0
        if args.command == "performance":
            run_market_performance()
            return 3
        if args.command == "config-hash":
            sys.stdout.write(proposed_config_hash() + "\n")
            return 0
        if args.command == "plan":
            plan = build_official_plan()
            sys.stdout.write(dumps_pretty({"requests": len(plan), "first": plan[0], "config": proposed_config()}).decode())
            return 0
        if args.command == "live":
            from bybit_research.live_public import execute_finite_live
            return execute_finite_live(sys.argv[2:] if argv is None else _live_argv(argv))
    except MarketPerformanceNotAuthorized as exc:
        sys.stderr.write(str(exc) + "\n")
        return 3
    except (VerifyError, FileExistsError, RuntimeError, ValueError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


def _live_argv(argv):
    if argv and argv[0] == "live":
        return list(argv[1:])
    return list(argv)
