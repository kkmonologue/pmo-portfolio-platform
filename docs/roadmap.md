# Roadmap

| # | Stage | What gets built | Status |
|---|---|---|---|
| 1 | Source simulator | Fictional global after-sales PMO: 15-table application DB reproducing the PMO workflows, legacy Excel tracker, labelled status updates, incremental runs, tests | ✅ done |
| 2 | Ingestion | `dlt` pipelines into DuckDB: application DB → `raw` schema (incremental on `updated_at`, merged on primary key, soft deletes kept); legacy tracker → `raw.tracker_rows` with header/layout detection. See [ingestion.md](ingestion.md) | ✅ done |
| 3 | Transformation | dbt on DuckDB: `staging` (types, JSON payloads, tracker date formats, old status vocabulary via a seed, duplicate rows) → `intermediate` (status and owner history from the event log, evidence workflow, tracker-to-project matching, request cycle times) → `marts` (`dim_project_history` SCD2, `dim_project`, `dim_team`, `dim_person`, `dim_date`, `fct_projects`, `fct_milestones`, `fct_requests`, `fct_status_updates`, `fct_board_reviews`, `mart_project_risks`, `mart_tracker_reconciliation`, `mart_team_portfolio`); 131 tests. See [warehouse.md](warehouse.md) | ✅ done |
| 4 | Orchestration & CI | Dagster assets for simulate → ingest → dbt → extract; schedules; GitHub Actions running ruff, pytest and `dbt build` | ⬜ |
| 5 | LLM extraction | `pmo-update-extractor` turns update text into RAG, risks, blockers and dates; evaluated against the simulator's labels; cost and cache tracking | ⬜ |
| 6 | Platform UI | The PMO platform (dashboard, Gantt, risks, approvals, bi-weekly view, board projects) reading from the marts | ⬜ |
| 7 | Extras | Milestone slip prediction, text-to-SQL Q&A over a whitelisted semantic layer, auto-generated weekly portfolio report | ⬜ |

Companion repository: **`pmo-update-extractor`**, a small standalone CLI and Python package that extracts structured status from free-text project updates in any CSV or Excel file, so other PMOs can use it without this platform.
