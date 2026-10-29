"""Dagster definitions: start the UI with

    uv run dagster dev -m orchestration.definitions

then open http://localhost:3000.
"""

from dagster import AssetSelection, DefaultScheduleStatus, Definitions, ScheduleDefinition, define_asset_job
from dagster_dbt import DbtCliResource

from .assets import dbt_project, pmo_app_simulation, raw_ingestion, raw_matches_source, warehouse_dbt
from .resources import PmoSettings

# Everything: simulate a week, load it, rebuild and test the warehouse.
weekly_pipeline = define_asset_job(
    name="weekly_pipeline",
    selection=AssetSelection.all(),
    description="Advance the simulated PMO by one week, load the changes, rebuild and test the warehouse.",
)

# Same without the simulation, for when the source changed by itself (a real deployment).
refresh_warehouse = define_asset_job(
    name="refresh_warehouse",
    selection=AssetSelection.all() - AssetSelection.assets(pmo_app_simulation),
    description="Load whatever changed in the source and rebuild the warehouse.",
)

weekly_schedule = ScheduleDefinition(
    name="weekly_pipeline_monday_morning",
    job=weekly_pipeline,
    cron_schedule="0 6 * * 1",
    execution_timezone="Europe/Amsterdam",
    default_status=DefaultScheduleStatus.STOPPED,  # switch on in the UI
    description="Every Monday 06:00, before the PMO's weekly review.",
)

defs = Definitions(
    assets=[pmo_app_simulation, raw_ingestion, warehouse_dbt],
    asset_checks=[raw_matches_source],
    jobs=[weekly_pipeline, refresh_warehouse],
    schedules=[weekly_schedule],
    resources={
        "settings": PmoSettings(),
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
)
