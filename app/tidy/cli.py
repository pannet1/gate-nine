"""Command line. Thin — all the work lives in the modules above."""

import argparse
import json
from pathlib import Path

from .workspace import DEFAULT_RECORDINGS_DIR, DEFAULT_RUNS_ROOT, Workspace


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link recordings into a run and report what needs a human.",
        epilog=(
            "tidy.py <case> <run_id>   one case into one run\n"
            "tidy.py                    every case into the latest run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("case", nargs="?", help="case name, e.g. sales-invoice")
    parser.add_argument("run_id", nargs="?", help="target run id, e.g. 001")
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument(
        "--recordings", dest="recordings_dir", default=str(DEFAULT_RECORDINGS_DIR)
    )
    parser.add_argument("--run-id", dest="run_id_opt")
    parser.add_argument("--cases", help="comma-separated names, overrides discovery")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ws = Workspace(
        runs_root=Path(args.runs_root), recordings_dir=Path(args.recordings_dir)
    )

    if args.case:
        report = ws.sync_case(
            case=args.case,
            run_id=args.run_id or args.run_id_opt,
            dry_run=args.dry_run,
        )
    else:
        names = [n.strip() for n in args.cases.split(",") if n.strip()] if args.cases else None
        report = ws.sync_run(
            run_id=args.run_id_opt or args.run_id,
            cases=names,
            dry_run=args.dry_run,
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))