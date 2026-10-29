"""Run the ingestion pipeline.

python -m ingestion run                 # load app DB + tracker into data/warehouse.duckdb (incremental)
python -m ingestion run --full-refresh  # drop the raw layer and reload everything
python -m ingestion status              # row counts in the raw layer
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import dlt
import duckdb

from .app_db import TABLES, app_db_source
from .tracker import tracker_rows

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
SOURCE_DB_URL = os.getenv("SOURCE_DB_URL", f"sqlite:///{DATA_DIR / 'source.db'}")
WAREHOUSE = Path(os.getenv("WAREHOUSE_PATH", DATA_DIR / "warehouse.duckdb"))
DATASET = "raw"


def make_pipeline(warehouse: Path, pipelines_dir: Path) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name="pmo_ingest",
        destination=dlt.destinations.duckdb(str(warehouse)),
        dataset_name=DATASET,
        pipelines_dir=str(pipelines_dir),
    )


def run(source_db: str, warehouse: Path, tracker_dir: Path, full_refresh: bool = False) -> dict[str, int]:
    """Load both sources; returns rows loaded per table in this run."""
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    pipeline = make_pipeline(warehouse, warehouse.parent / ".dlt")
    refresh = "drop_sources" if full_refresh else None
    pipeline.run(app_db_source(source_db), refresh=refresh)
    loaded = dict(pipeline.last_trace.last_normalize_info.row_counts)
    if tracker_dir.exists():
        pipeline.run(tracker_rows(tracker_dir), refresh="drop_resources" if full_refresh else None)
        loaded.update(pipeline.last_trace.last_normalize_info.row_counts)
    return {k: v for k, v in loaded.items() if not k.startswith("_dlt")}


def raw_counts(warehouse: Path) -> dict[str, int]:
    with duckdb.connect(str(warehouse), read_only=True) as con:
        tables = [
            r[0]
            for r in con.execute("select table_name from information_schema.tables where table_schema = ? order by 1", [DATASET]).fetchall()
        ]
        return {t: con.execute(f'select count(*) from {DATASET}."{t}"').fetchone()[0] for t in tables if not t.startswith("_dlt")}


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="ingestion", description="Load the PMO application DB and legacy tracker into the warehouse raw layer"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--source-db", default=SOURCE_DB_URL)
    r.add_argument("--warehouse", type=Path, default=WAREHOUSE)
    r.add_argument("--tracker-dir", type=Path, default=DATA_DIR / "excel")
    r.add_argument("--full-refresh", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--warehouse", type=Path, default=WAREHOUSE)
    args = ap.parse_args()

    if args.cmd == "run":
        loaded = run(args.source_db, args.warehouse, args.tracker_dir, args.full_refresh)
        print(f"loaded into {args.warehouse} (schema '{DATASET}'):")
        for table in [*TABLES, "tracker_rows"]:
            print(f"  {table:22} {loaded.get(table, 0):>7} rows")
    else:
        for table, n in raw_counts(args.warehouse).items():
            print(f"  {table:22} {n:>7}")


if __name__ == "__main__":
    main()
