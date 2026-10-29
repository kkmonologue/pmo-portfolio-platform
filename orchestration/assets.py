"""Assets: the simulated source, the raw layer loaded by dlt, and every dbt model.

Asset keys are chosen so Dagster draws one connected lineage graph:
    pmo_app_simulation -> app/<table>, tracker/tracker_rows -> stg_* -> int_* -> dim_* / fct_* / mart_*
dlt writes the tables that dbt declares as sources `app` and `tracker`, and dagster-dbt
keys dbt sources as [source_name, table_name], so the ingestion assets use the same keys.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import duckdb
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    Config,
    MaterializeResult,
    MetadataValue,
    asset,
    multi_asset,
    multi_asset_check,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets
from sqlalchemy import create_engine, text

from ingestion.__main__ import run as run_ingestion
from ingestion.app_db import TABLES
from simulator.api import advance_world, init_world, is_initialised

from .resources import REPO_ROOT, PmoSettings

# ---------------------------------------------------------------- source (simulation)


class SimulationConfig(Config):
    """How far to move the simulated organisation forward in one run."""

    days: int = 7


@asset(
    group_name="source",
    kinds={"python", "sqlite"},
    description="The fictional company's PMO application database and weekly tracker files. Backfills from 2024-07-01 on first run, then advances `days` per run.",
)
def pmo_app_simulation(context: AssetExecutionContext, config: SimulationConfig, settings: PmoSettings) -> MaterializeResult:
    if is_initialised(settings.source_url, settings.data_path, settings.seed):
        summary = advance_world(settings.source_url, settings.data_path, settings.seed, config.days)
    else:
        context.log.info("No simulation yet: backfilling history up to today")
        summary = init_world(settings.source_url, settings.data_path, settings.seed)
    context.log.info(f"Simulated {summary['days_simulated']} days up to {summary['simulated_until']}")
    return MaterializeResult(
        metadata={
            "simulated_until": summary["simulated_until"],
            "days_simulated": summary["days_simulated"],
            "rows_written": sum(summary["rows_written"].values()),
            "tracker_files_written": summary["tracker_files"],
            "rows_written_by_table": MetadataValue.json(summary["rows_written"]),
        }
    )


# ---------------------------------------------------------------- raw layer (dlt)

RAW_SPECS = [
    *(
        AssetSpec(
            AssetKey(["app", t]),
            deps=[pmo_app_simulation],
            group_name="raw",
            kinds={"dlt", "duckdb"},
            description=f"raw.{t}, merged incrementally on updated_at",
        )
        for t in TABLES
    ),
    AssetSpec(
        AssetKey(["tracker", "tracker_rows"]),
        deps=[pmo_app_simulation],
        group_name="raw",
        kinds={"dlt", "duckdb"},
        description="raw.tracker_rows from the weekly Excel tracker",
    ),
]


@multi_asset(
    specs=RAW_SPECS, name="raw_ingestion", description="dlt load of the application DB (incremental) and new tracker workbooks into DuckDB."
)
def raw_ingestion(context: AssetExecutionContext, settings: PmoSettings) -> Iterator[MaterializeResult]:
    loaded = run_ingestion(settings.source_url, settings.warehouse_path, settings.tracker_dir)
    context.log.info(f"Loaded {sum(loaded.values())} rows")
    for spec in RAW_SPECS:
        table = spec.key.path[-1]
        yield MaterializeResult(asset_key=spec.key, metadata={"rows_loaded_this_run": loaded.get(table, 0)})


@multi_asset_check(
    specs=[
        AssetCheckSpec("matches_source_row_count", asset=AssetKey(["app", t]), description="raw row count equals the source table's")
        for t in TABLES
    ],
)
def raw_matches_source(settings: PmoSettings) -> Iterator[AssetCheckResult]:
    """After a load, every raw table must hold exactly as many rows as its source table."""
    source = create_engine(settings.source_url)
    with source.connect() as src, duckdb.connect(str(settings.warehouse_path), read_only=True) as wh:
        for t in TABLES:
            n_src = src.execute(text(f"select count(*) from {t}")).scalar()
            n_raw = wh.execute(f"select count(*) from raw.{t}").fetchone()[0]
            yield AssetCheckResult(
                asset_key=AssetKey(["app", t]),
                check_name="matches_source_row_count",
                passed=n_src == n_raw,
                severity=AssetCheckSeverity.ERROR,
                metadata={"source_rows": n_src, "raw_rows": n_raw},
            )


# ---------------------------------------------------------------- warehouse (dbt)

dbt_project = DbtProject(project_dir=REPO_ROOT / "warehouse", profiles_dir=REPO_ROOT / "warehouse")
dbt_project.prepare_if_dev()
if not Path(dbt_project.manifest_path).exists():
    # outside `dagster dev` (tests, CI, a fresh clone) parse the project once to get the manifest
    dbt_project.preparer.prepare(dbt_project)


class LayerTranslator(DagsterDbtTranslator):
    """Group dbt assets by layer (staging / intermediate / marts / reference) in the Dagster UI."""

    def get_group_name(self, dbt_resource_props) -> str | None:
        if dbt_resource_props["resource_type"] == "seed":
            return "reference"
        fqn = dbt_resource_props.get("fqn", [])
        return fqn[1] if len(fqn) > 2 else None


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project, dagster_dbt_translator=LayerTranslator())
def warehouse_dbt(context: AssetExecutionContext, dbt: DbtCliResource, settings: PmoSettings):
    """dbt build: every model is an asset, every dbt test becomes an asset check."""
    os.environ["WAREHOUSE_PATH"] = str(settings.warehouse_path)  # profiles.yml reads this; dbt runs from warehouse/
    yield from dbt.cli(["build"], context=context).stream()
