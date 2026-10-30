# Roadmap

| # | Stage | What gets built | Status |
|---|---|---|---|
| 1 | Source simulator | Fictional global after-sales PMO: 15-table application DB reproducing the PMO workflows, legacy Excel tracker, labelled status updates, incremental runs, tests | ✅ done |
| 2 | Ingestion | `dlt` pipelines into DuckDB: application DB → `raw` schema (incremental on `updated_at`, merged on primary key, soft deletes kept); legacy tracker → `raw.tracker_rows` with header/layout detection. See [ingestion.md](ingestion.md) | ✅ done |
| 3 | Transformation | dbt on DuckDB: `staging` (types, JSON payloads, tracker date formats, old status vocabulary via a seed, duplicate rows) → `intermediate` (status and owner history from the event log, evidence workflow, tracker-to-project matching, request cycle times) → `marts` (`dim_project_history` SCD2, `dim_project`, `dim_team`, `dim_person`, `dim_date`, `fct_projects`, `fct_milestones`, `fct_requests`, `fct_status_updates`, `fct_board_reviews`, `mart_project_risks`, `mart_tracker_reconciliation`, `mart_team_portfolio`); 131 tests. See [warehouse.md](warehouse.md) | ✅ done |
| 4 | Orchestration & CI | Dagster: simulation, dlt and dbt as one connected asset graph (53 assets, dbt tests as asset checks, raw-vs-source row-count check), `weekly_pipeline` and `refresh_warehouse` jobs, Monday-morning schedule; automatic full reload after a source rebuild; GitHub Actions runs ruff, pytest, the ingestion and dbt smoke tests and both Dagster jobs. See [orchestration.md](orchestration.md) | ✅ done |
| 5 | LLM extraction | `extractor/`: RAG, risks, blocker and next date from free text; rule baseline + provider-agnostic LLM client (Gemini, Groq, Mistral, Ollama) with validation, cache, rate limiting and retries; evaluation on 300 simulated + 29 hand-labelled challenge updates; signals in the warehouse (`fct_status_update_signals`, new `reported` risk) and in the Dagster graph. See [extraction.md](extraction.md) | ✅ done (LLM scores: run with your key) |
| 6 | Platform UI | The PMO platform (dashboard, Gantt, risks, approvals, bi-weekly view, board projects) reading from the marts | ⬜ |
| 7 | Extras | Milestone slip prediction, text-to-SQL Q&A over a whitelisted semantic layer, auto-generated weekly portfolio report | ⬜ |

The extractor is self-contained (text + posting date in, signals out) and has its own CLI for any CSV / Excel file, so it can be split into a separate `pmo-update-extractor` repository without changes.
