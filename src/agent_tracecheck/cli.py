from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from .engine import scan
from .io import atomic_write_text, discover, strict_json
from .model import Config
from .reporters import render
from .reproduce import reproduce
from .rules import RULES


def load_config(path: str | None) -> Config:
    if path is None:
        return Config()
    target = Path(path)
    if target.suffix.lower() == ".json":
        data = strict_json(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Configuration must be an object/table")
        # Reproduction metadata can be used directly, preserving exact policy.
        values = data.get("config", data)
    else:
        data = tomllib.loads(target.read_text(encoding="utf-8"))
        values = data.get("tracecheck", data)
    if not isinstance(values, dict):
        raise ValueError("Configuration must be an object/table")
    try:
        config = Config(**values)
    except TypeError as exc:
        raise ValueError(f"Invalid configuration keys: {exc}") from exc
    config.validate()
    return config


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-tracecheck", description="Lint agent trajectories before SFT / RL training."
    )
    p.add_argument("--version", action="version", version="agent-tracecheck 0.2.0")
    commands = p.add_subparsers(dest="command", required=True)
    s = commands.add_parser("scan", help="Scan JSON/JSONL files or directories")
    s.add_argument("paths", nargs="+")
    s.add_argument("--config", help="TOML policy or reproduction metadata JSON")
    s.add_argument("--format", choices=["text", "json", "html", "sarif", "markdown"], default="text")
    s.add_argument("--output", "-o", help="Write primary report to this path")
    for fmt in ("json", "html", "sarif", "markdown"):
        s.add_argument(f"--{fmt}", metavar="PATH", help=f"Also write a {fmt} report")
    s.add_argument("--fail-on", choices=["error", "warning", "info", "none"], default="error")
    s.add_argument("--disable", action="append", default=[], metavar="RULE")
    s.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Exclude relative input paths, e.g. reports/* (repeatable)",
    )
    commands.add_parser("rules", help="List checks and their default severity")
    e = commands.add_parser("explain", help="Explain one check and its remediation")
    e.add_argument("rule", choices=sorted(RULES))
    r = commands.add_parser("repro", help="Extract and minimize a finding from a JSON report")
    r.add_argument("report")
    r.add_argument("issue_id")
    r.add_argument("--output", "-o", required=True)
    r.add_argument("--max-checks", type=int, default=300)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "rules":
            for key, rule in RULES.items():
                print(f"{key:28} {rule.severity:7} {rule.category:11} {rule.title}")
            return 0
        if args.command == "explain":
            rule = RULES[args.rule]
            print(f"{args.rule} [{rule.severity}]\n{rule.title}\n\n{rule.suggestion}")
            return 0
        if args.command == "repro":
            if args.max_checks < 1:
                raise ValueError("--max-checks must be positive")
            result = reproduce(args.report, args.issue_id, args.output, args.max_checks)
            print(f"Verified {result['rule']} reproduction: {args.output}\n{result['minimality']}")
            return 0
        config = load_config(args.config)
        config.disabled_rules = list(dict.fromkeys(config.disabled_rules + args.disable))
        config.validate()
        files = discover(args.paths, args.exclude)
        destinations = [(args.format, args.output)] if args.output else []
        destinations += [
            (fmt, getattr(args, fmt)) for fmt in ("json", "html", "sarif", "markdown") if getattr(args, fmt)
        ]
        output_paths = [Path(path).resolve() for _, path in destinations]
        if len(set(output_paths)) != len(output_paths):
            raise ValueError("Report output paths must be distinct")
        protected = set(files)
        if args.config:
            protected.add(Path(args.config).resolve())
        if any(path in protected for path in output_paths):
            raise ValueError("Report output cannot overwrite input data or configuration")
        if any(out.exists() and out.samefile(src) for out in output_paths for src in protected):
            raise ValueError("Report output cannot overwrite a hard link to input data or configuration")
        report = scan(files, config)
        for fmt, path in destinations:
            atomic_write_text(path, render(report, fmt))
        if not args.output:
            sys.stdout.write(render(report, args.format))
        else:
            summary = report.to_dict()["summary"]
            print(
                f"Scanned {summary['records']} records; {summary['error']} errors, {summary['warning']} warnings. Report: {args.output}",
                file=sys.stderr,
            )
        levels = {"none": 4, "error": 3, "warning": 2, "info": 1}
        return int(any(levels[i.severity] >= levels[args.fail_on] for i in report.issues))
    except (OSError, ValueError, TypeError, KeyError, EOFError, RecursionError) as exc:
        print(f"agent-tracecheck: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("agent-tracecheck: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
