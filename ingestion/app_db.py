"""dlt source for the PMO application database.

Every table is loaded incrementally: dlt remembers the highest ``updated_at``
it has seen per table and only pulls rows changed since then, then merges
them into ``raw.<table>`` on the primary key. Updated rows replace their
previous version; soft-deleted projects arrive as ``is_deleted = true``.

The table list is configured here on purpose, not imported from the
simulator: the ingestion layer only knows what any client of the
application database would know.
"""

from __future__ import annotations

import dlt
from dlt.sources.sql_database import sql_database

# table -> primary key
TABLES: dict[str, str] = {
    "teams": "team_id",
    "people": "person_id",
    "team_managers": "team_manager_id",
    "projects": "project_id",
    "project_executors": "executor_id",
    "milestones": "milestone_id",
    "milestone_submissions": "submission_id",
    "requests": "request_id",
    "board_reviews": "review_id",
    "board_votes": "vote_id",
    "meetings": "meeting_id",
    "status_updates": "update_id",
    "follow_ups": "follow_up_id",
    "project_events": "event_id",
    "emails": "email_id",
}
CURSOR = "updated_at"


def app_db_source(credentials: str):
    """All application tables, incremental on updated_at, merged on their primary key."""
    source = sql_database(credentials=credentials, table_names=list(TABLES), reflection_level="full", backend="sqlalchemy")
    for name, pk in TABLES.items():
        source.resources[name].apply_hints(
            primary_key=pk,
            write_disposition="merge",
            incremental=dlt.sources.incremental(CURSOR),
        )
    return source
