"""Command line entry point.

python -m simulator init                 # fresh database, backfill from 2024-07-01 to today
python -m simulator advance --days 7     # continue one week (new inserts, updates, soft deletes)
python -m simulator status               # row counts and simulated date
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path

from .api import DEFAULT_START, advance_world, init_world, world_status

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DEFAULT_URL = os.getenv("SOURCE_DB_URL", f"sqlite:///{DATA_DIR / 'source.db'}")


def _print(summary: dict) -> None:
    print(f"simulated {summary['days_simulated']} days up to {summary['simulated_until']}")
    print("rows written:", ", ".join(f"{k}={v}" for k, v in summary["rows_written"].items()) or "none")
    print(f"excel files: {summary['tracker_files']}, new labelled updates: {summary['labelled_updates']}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="simulator", description="Elvanor (fictional) after-sales PMO data simulator")
    ap.add_argument("--db", default=DEFAULT_URL, help="SQLAlchemy URL of the source database")
    ap.add_argument("--seed", type=int, default=int(os.getenv("SIM_SEED", "42")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="create a fresh source database and backfill history")
    i.add_argument("--start", type=dt.date.fromisoformat, default=DEFAULT_START)
    i.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    i.add_argument("--excel-weeks", type=int, default=8, help="weekly Excel reports for the last N weeks of the backfill")
    a = sub.add_parser("advance", help="continue the simulation")
    a.add_argument("--days", type=int, default=7)
    sub.add_parser("status")
    args = ap.parse_args()

    if args.cmd == "init":
        _print(init_world(args.db, DATA_DIR, args.seed, args.start, args.end, args.excel_weeks))
    elif args.cmd == "advance":
        try:
            _print(advance_world(args.db, DATA_DIR, args.seed, args.days))
        except RuntimeError as e:
            raise SystemExit(str(e)) from e
    else:
        status = world_status(args.db, DATA_DIR, args.seed)
        print("simulated up to:", status["simulated_until"] or "(not initialised)")
        for table, n in status["rows"].items():
            print(f"  {table:22} {n:>7}")


if __name__ == "__main__":
    main()
