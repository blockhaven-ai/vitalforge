"""Command-line interface.

Usage::

    vitalforge generate --persona examples/personas/alex_rivera.yaml \\
        --days 30 --seed 42 --out ./out --format jsonl
    vitalforge trajectory --persona examples/personas/jordan_kim.yaml \\
        --years 10 --seed 42 --out ./out --format json
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import List, Optional

from vitalforge.dataset import build_dataset, build_trajectory_dataset
from vitalforge.output import FORMATS, write_dataset
from vitalforge.personas import PersonaError, load_persona


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vitalforge",
        description="Persona-driven synthetic longitudinal health data generator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate daily-resolution signal and clinical data.")
    gen.add_argument("--persona", required=True, help="Path to a persona YAML/JSON file.")
    gen.add_argument("--days", type=int, default=30, help="Days of data to generate (default: 30).")
    gen.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    gen.add_argument(
        "--start-date",
        default=None,
        help="Override the persona's start_date (ISO date, e.g. 2025-03-01).",
    )
    gen.add_argument("--out", default="./out", help="Output directory (default: ./out).")
    gen.add_argument(
        "--format",
        choices=FORMATS,
        default="json",
        help="Output format (default: json).",
    )

    traj = sub.add_parser("trajectory", help="Generate multi-year trajectory data.")
    traj.add_argument("--persona", required=True, help="Path to a persona YAML/JSON file.")
    traj.add_argument("--years", type=int, default=10, help="Years to generate (default: 10).")
    traj.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    traj.add_argument("--out", default="./out", help="Output directory (default: ./out).")
    traj.add_argument(
        "--format",
        choices=("json", "jsonl", "csv"),
        default="json",
        help="Output format (default: json).",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        persona = load_persona(args.persona)
        if args.command == "generate":
            if args.days < 1:
                print("error: --days must be >= 1", file=sys.stderr)
                return 2
            start_date = (
                datetime.date.fromisoformat(args.start_date) if args.start_date else None
            )
            dataset = build_dataset(persona, args.days, args.seed, start_date=start_date)
            record_count = len(dataset["signals"]) + len(dataset["clinical"])
        else:
            if args.years < 1:
                print("error: --years must be >= 1", file=sys.stderr)
                return 2
            dataset = build_trajectory_dataset(persona, args.years, args.seed)
            record_count = len(dataset["trajectory"])
        paths = write_dataset(dataset, Path(args.out), args.format)
    except PersonaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"persona: {persona.profile.name}")
    print(f"records: {record_count}")
    for path in paths:
        print(f"wrote: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
