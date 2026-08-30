from __future__ import annotations

import argparse
from pathlib import Path

from evolution.dataset import build_executable_discovery_from_fast
from evolution.dataset import build_window_from_catalog
from evolution.diagnostic import run_discovery_diagnostic
from evolution.rerank import rerank_discovery_candidates
from evolution.runner import run_evolution
from evolution.spec import ALL_WINDOWS
from evolution.spec import DISCOVERY_FOLDS
from evolution.spec import INSTRUMENT_IDS
from evolution.spec import run_directory
from evolution.validator import promote_top_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and run isolated OpenEvolve strategy research.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-data", help="Build local split-specific datasets from the read-only catalog.")
    build.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
    build.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
    executable = subparsers.add_parser(
        "build-executable-discovery",
        help="Build one-second quote datasets for discovery folds only.",
    )
    executable.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
    executable.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
    executable.add_argument(
        "--output-root",
        type=Path,
        default=Path(".local/evolution-data-executable"),
    )
    for name in ("evolve", "resume"):
        run = subparsers.add_parser(name, help=f"{name.title()} one instrument evolution run.")
        run.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
        run.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
        run.add_argument("--output-root", type=Path, default=Path("outputs/evolution"))
        run.add_argument("--run-id", required=True)
        run.add_argument("--iterations", type=int, default=30 if name == "evolve" else 300)
        if name == "resume":
            run.add_argument("--checkpoint", type=Path, required=True)
    diagnose = subparsers.add_parser("diagnose", help="Run fixed baselines on discovery folds only.")
    diagnose.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
    diagnose.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
    diagnose.add_argument("--output-root", type=Path, default=Path("outputs/evolution-diagnostics"))
    diagnose.add_argument("--run-id", required=True)
    rerank = subparsers.add_parser("rerank", help="Rerank top candidates with executable discovery quotes.")
    rerank.add_argument("--instrument-id", choices=INSTRUMENT_IDS, required=True)
    rerank.add_argument("--dataset-root", type=Path, default=Path(".local/evolution-data"))
    rerank.add_argument(
        "--executable-dataset-root",
        type=Path,
        default=Path(".local/evolution-data-executable"),
    )
    rerank.add_argument("--output-root", type=Path, default=Path("outputs/evolution"))
    rerank.add_argument("--run-id", required=True)
    rerank.add_argument("--top-n", type=int, default=10)
    rerank.add_argument("--skip-baselines", action="store_true")
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
    if args.command == "diagnose":
        output = run_directory(args.output_root, args.instrument_id, args.run_id) / "diagnostic.json"
        run_discovery_diagnostic(args.instrument_id, args.dataset_root, output)
        print(f"Diagnostic: {output}")
        return
    if args.command == "rerank":
        run_dir = run_directory(args.output_root, args.instrument_id, args.run_id)
        output = run_dir / "rerank.json"
        rerank_discovery_candidates(
            args.instrument_id,
            args.dataset_root,
            args.executable_dataset_root,
            run_dir,
            output,
            args.top_n,
            not args.skip_baselines,
        )
        print(f"Rerank: {output}")
        return
    if args.command == "build-executable-discovery":
        for window in DISCOVERY_FOLDS:
            manifest = build_executable_discovery_from_fast(
                args.instrument_id,
                window,
                args.dataset_root,
                args.output_root,
            )
            print(f"{window.name}: {manifest.quote_count} executable quotes")
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
