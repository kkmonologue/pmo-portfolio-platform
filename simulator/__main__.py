"""Command line entry point.

python -m simulator init                 # fresh database, backfill from 2024-07-01 to today
python -m simulator advance --days 7     # continue one week (new inserts, updates, soft deletes)
python -m simulator status               # row counts and simulated date
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select

from . import schema as S
from .engine import Simulation
from .excel_export import write_week

DEFAULT_URL = os.getenv("SOURCE_DB_URL", "sqlite:///data/source.db")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def _engine(url: str):
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url)


def _run(sim: Simulation, end: dt.date, excel_weeks: int) -> None:
    excel_from = end - dt.timedelta(weeks=excel_weeks) if excel_weeks else None
    days = sim.run_until(end, excel_from)
    counts = sim.save()
    files = sum(len(write_week(DATA_DIR / "excel", d, snap, sim.seed)) for d, snap in sim.weekly_snapshots)
    print(f"simulated {days} days up to {sim.state['last_date']}")
    print("rows written:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none")
    print(f"excel files: {files}, new labelled updates: {len(sim.new_labels)}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="simulator", description="Elvanor (fictional) after-sales PMO data simulator")
    ap.add_argument("--db", default=DEFAULT_URL, help="SQLAlchemy URL of the source database")
    ap.add_argument("--seed", type=int, default=int(os.getenv("SIM_SEED", "42")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="create a fresh source database and backfill history")
    i.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2024, 7, 1))
    i.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    i.add_argument("--excel-weeks", type=int, default=8, help="weekly Excel reports for the last N weeks of the backfill")
    a = sub.add_parser("advance", help="continue the simulation")
    a.add_argument("--days", type=int, default=7)
    sub.add_parser("status")
    args = ap.parse_args()

    eng = _engine(args.db)
    if args.cmd == "init":
        # drop every table, including ones left over from older versions of the schema
        old = MetaData()
        old.reflect(eng)
        old.drop_all(eng)
        for p in [DATA_DIR / "excel", DATA_DIR / "labels"]:
            shutil.rmtree(p, ignore_errors=True)
        sim = Simulation(eng, args.seed, DATA_DIR)
        sim.bootstrap(args.start)
        _run(sim, args.end, args.excel_weeks)
    elif args.cmd == "advance":
        sim = Simulation(eng, args.seed, DATA_DIR)
        if not sim.state:
            raise SystemExit("No simulation found. Run `python -m simulator init` first.")
        end = dt.date.fromisoformat(sim.state["last_date"]) + dt.timedelta(days=args.days)
        _run(sim, end, excel_weeks=args.days // 7 + 1)
    else:
        sim = Simulation(eng, args.seed, DATA_DIR)
        print("simulated up to:", sim.state["last_date"] if sim.state else "(not initialised)")
        with eng.connect() as c:
            for t in S.SOURCE_TABLES:
                print(f"  {t.name:22} {c.execute(select(func.count()).select_from(t)).scalar():>7}")


if __name__ == "__main__":
    main()
