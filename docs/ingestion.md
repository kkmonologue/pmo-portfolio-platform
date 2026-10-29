# Ingestion (stage 2)

`ingestion/` loads both sources into the **raw** layer of a DuckDB warehouse (`data/warehouse.duckdb`) with [dlt](https://dlthub.com/docs). Raw means "as the source delivered it": no renaming, no business logic. Cleaning happens in dbt (stage 3), where it can be tested.

```bash
uv run python -m ingestion run                 # incremental: only what changed since the last run
uv run python -m ingestion run --full-refresh  # drop the raw layer and reload everything
uv run python -m ingestion status              # row counts in raw
```

By default it reads `data/source.db`; set `SOURCE_DB_URL` to read the Postgres source instead (`make ingest` does this).

## Application database → `raw.<table>`

| Choice | Why |
|---|---|
| One `sql_database` source, 15 tables listed explicitly in `ingestion/app_db.py` | The ingestion layer only knows what any client of the application DB would know; it doesn't import the simulator's schema. New source tables are opt-in. |
| Incremental on `updated_at` | dlt stores the highest `updated_at` per table in the pipeline state and only selects newer rows. A run after one simulated week moves a few hundred rows instead of ~18,000. |
| `merge` on the primary key | An updated row replaces its previous version, so `raw.projects` always holds each project's latest state. History is not lost: it lives in `project_events`, `requests` and `team_managers.valid_from/valid_to`, which dbt turns into SCD2 dimensions. |
| Soft deletes kept as rows | Projects are never physically deleted in the source; `is_deleted = true` arrives like any other update and is filtered in staging. |
| Types from SQL reflection | Dates, timestamps, booleans and integers land typed; dlt adds `_dlt_load_id` / `_dlt_id` for lineage. |

## Legacy tracker → `raw.tracker_rows`

Each weekly workbook has one sheet per team in two layouts. `ingestion/tracker.py`:

1. scans the first 5 rows of each sheet for a header row containing a project reference, a project name and a status column, in either layout;
2. maps both layouts to one set of columns: `row_no, project_ref, project_name, owner, status, start_raw, end_raw, extensions, latest_update`;
3. skips blank rows, keeps everything else as text (real Excel dates become ISO strings; text dates stay as typed);
4. adds `snapshot_week`, `file_name`, `sheet_name`, `layout` and the Excel row number `source_row`.

Rows are merged on `(snapshot_week, sheet_name, source_row)`, so reloading a file is idempotent. Weekly files never change once written, so the resource keeps the last loaded week in dlt's state and only opens newer workbooks.

Deliberately **not** done here: mapping old statuses (`Ongoing`, `Done`, `Close report pending`…), parsing `dd/mm/yyyy` vs `30.06.2025`, resolving `TRK` legacy codes, removing pasted duplicate rows. Those are stage 3 models with tests.

## Tests (`tests/test_ingestion.py`)

- full load: every raw table has the same row count as its source table;
- rerun without source changes loads 0 rows;
- after the simulation advances two weeks, the incremental run loads exactly the new status updates, only changed projects, the new tracker weeks, and raw still matches the source (counts and every project's current status);
- both tracker layouts map to the same columns; blank rows are skipped; sheets without a header are ignored.

A rebuilt source (`simulator init`) leaves a `.full_refresh_requested` marker in the data folder. The next run then reloads everything and removes the marker, because load positions from the old source would be wrong. A test covers this case.

dlt's anonymous usage telemetry is switched off in `.dlt/config.toml`.
