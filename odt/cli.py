"""Command line entry point."""
import argparse
import json
from pathlib import Path
import sys
import yaml
from . import HONESTY
from .engine import simulate, metrics, canonical
from .model import read_model, apply_scenario
from .fixtures import write_fixtures
from .report import compare, report


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=HONESTY)
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("validate")
    p.add_argument("model")
    p = subs.add_parser("simulate")
    p.add_argument("--model", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out")
    p = subs.add_parser("scenario")
    p.add_argument("--base", required=True)
    p.add_argument("--change", required=True)
    p.add_argument("--out")
    p = subs.add_parser("compare")
    p.add_argument("--base", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--out")
    p = subs.add_parser("report")
    p.add_argument("--trace", required=True)
    p.add_argument("--scenario")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--out")
    p = subs.add_parser("fixtures")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            read_model(args.model)
            output = "Valid fictional declared model.\n"
        elif args.command == "fixtures":
            write_fixtures(args.out)
            output = "Synthetic fictional fixtures written.\n"
        elif args.command == "scenario":
            change = yaml.safe_load(Path(args.change).read_text(encoding="utf-8"))
            output = yaml.safe_dump(apply_scenario(read_model(args.base), change), sort_keys=True)
        elif args.command == "simulate":
            trace = simulate(read_model(args.model), args.seed)
            trace["metrics"] = metrics(trace)
            output = canonical(trace)
        elif args.command == "compare":
            output = canonical(compare(load(args.base), load(args.scenario)))
        else:
            output = report(load(args.trace), load(args.scenario) if args.scenario else None, args.format)
        if getattr(args, "out", None) and args.command != "fixtures":
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(output, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(output)
        return 0
    except (ValueError, OSError, yaml.YAMLError) as e:
        print(str(e), file=sys.stderr)
        return 2
