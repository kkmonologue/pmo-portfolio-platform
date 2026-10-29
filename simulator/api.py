"""Functions to create and advance the simulated PMO, used by the CLI and by Dagster."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from sqlalchemy import Engine, MetaData, create_engine, func, select

from . import schema as S
from .engine import Simulation
from .excel_export import write_week

DEFAULT_START = dt.date(2024, 7, 1)
# Written when the source is rebuilt from scratch: the next ingestion run must reload everything,
# otherwise rows and load positions from the old source would mix with the new one.
FULL_REFRESH_MARKER = ".full_refresh_requested"


def make_engine(db_url: str) -> Engine:
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(db_url)


def _run(sim: Simulation, data_dir: Path, end: dt.date, excel_weeks: int) -> dict:
    excel_from = end - dt.timedelta(weeks=excel_weeks) if excel_weeks else None
    days = sim.run_until(end, excel_from)
    counts = sim.save()
    files = sum(len(write_week(data_dir / "excel", d, snap, sim.seed)) for d, snap in sim.weekly_snapshots)
    return {
        "simulated_until": sim.state["last_date"],
        "days_simulated": days,
        "rows_written": dict(sorted(counts.items())),
        "tracker_files": files,
        "labelled_updates": len(sim.new_labels),
    }


def init_world(
    db_url: str, data_dir: Path, seed: int = 42, start: dt.date = DEFAULT_START, end: dt.date | None = None, excel_weeks: int = 8
) -> dict:
    """Drop everything and backfill the organisation from `start` to `end` (default: today)."""
    eng = make_engine(db_url)
    old = MetaData()  # drop every table, including ones left over from older versions of the schema
    old.reflect(eng)
    old.drop_all(eng)
    for p in [data_dir / "excel", data_dir / "labels"]:
        shutil.rmtree(p, ignore_errors=True)
    sim = Simulation(eng, seed, data_dir)
    sim.bootstrap(start)
    summary = _run(sim, data_dir, end or dt.date.today(), excel_weeks)
    (data_dir / FULL_REFRESH_MARKER).write_text("source rebuilt by simulator init\n")
    return summary


def advance_world(db_url: str, data_dir: Path, seed: int = 42, days: int = 7) -> dict:
    """Continue an existing simulation by `days` days."""
    sim = Simulation(make_engine(db_url), seed, data_dir)
    if not sim.state:
        raise RuntimeError("No simulation found. Run `python -m simulator init` first.")
    end = dt.date.fromisoformat(sim.state["last_date"]) + dt.timedelta(days=days)
    return _run(sim, data_dir, end, excel_weeks=days // 7 + 1)


def is_initialised(db_url: str, data_dir: Path, seed: int = 42) -> bool:
    return Simulation(make_engine(db_url), seed, data_dir).state is not None


def world_status(db_url: str, data_dir: Path, seed: int = 42) -> dict:
    eng = make_engine(db_url)
    sim = Simulation(eng, seed, data_dir)
    with eng.connect() as c:
        counts = {t.name: c.execute(select(func.count()).select_from(t)).scalar() for t in S.SOURCE_TABLES}
    return {"simulated_until": sim.state["last_date"] if sim.state else None, "rows": counts}
