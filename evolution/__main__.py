from __future__ import annotations

import argparse
from pathlib import Path

from evolution.dataset import build_window_from_catalog
from evolution.runner import run_evolution
from evolution.spec import ALL_WINDOWS
from evolution.spec import INSTRUMENT_IDS
from evolution.spec import run_directory
from evolution.validator import promote_top_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and run isolated OpenEvolve strategy research.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-data", help="Build local split-specific datasets from the read-only catalog.")
    build.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
    build.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
    for name in ("evolve", "resume"):
        run = subparsers.add_parser(name, help=f"{name.title()} one instrument evolution run.")
        run.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
        run.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
        run.add_argument("--output-root", type=Path, default=Path("outputs/evolution"))
        run.add_argument("--run-id", required=True)
        run.add_argument("--iterations", type=int, default=30 if name == "evolve" else 300)
        if name == "resume":
            run.add_argument("--checkpoint", type=Path, required=True)
    promote = subparsers.add_parser("promote", help="Validate top 10 and consume holdout once.")
    promote.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
    promote.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
    promote.add_argument("--output-root", type=Path, default=Path("outputs/evolution"))
    promote.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build-data":
        for window in ALL_WINDOWS:
            manifest = build_window_from_catalog(args.instrument_id, window, args.dataset_root)
            print(f"{window.name}: {manifest.row_count} states")
        return
    if args.command == "promote":
        result = promote_top_candidates(
            args.instrument_id,
            args.dataset_root,
            run_directory(args.output_root, args.instrument_id, args.run_id),
        )
        print(f"Promotion status: {result['status']}")
        return
    result = run_evolution(
        args.instrument_id,
        args.dataset_root,
        args.output_root,
        args.run_id,
        args.iterations,
        getattr(args, "checkpoint", None),
    )
    print(f"OpenEvolve exit code: {result.returncode}")
    print(f"Output: {result.output_directory}")
    if result.resume_command:
        print(f"Resume: {result.resume_command}")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
