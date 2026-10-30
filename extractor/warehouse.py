"""Incremental extraction for the warehouse: read raw.status_updates from DuckDB, extract the
updates this extractor has not seen yet, append to extract.status_update_signals.

dbt reads that table as source `extract`; when an update has been extracted by both the
rules and an LLM, the dbt model prefers the LLM result.
"""

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path

import duckdb

from .schema import SEVERITY_ORDER, Extraction

DDL = """
create schema if not exists extract;
create table if not exists extract.status_update_signals (
    update_id bigint,
    extractor varchar,
    rag varchar,
    stated_rag varchar,
    blocked boolean,
    risk_count integer,
    max_risk_severity varchar,
    risks_json varchar,
    next_milestone_date date,
    next_milestone_date_precision varchar,
    extracted_at timestamp,
    primary key (update_id, extractor)
);
"""


def extract_new(warehouse: Path, extractor_name: str, extract: Callable[[str, dt.date], Extraction], max_new: int | None = None) -> dict:
    """Extract updates not yet processed by `extractor_name`; returns counts."""
    with duckdb.connect(str(warehouse)) as con:
        con.execute(DDL)
        exists = con.execute(
            "select count(*) from information_schema.tables where table_schema = 'raw' and table_name = 'status_updates'"
        ).fetchone()[0]
        if not exists:
            return {"extracted": 0, "remaining": 0}
        todo = con.execute(
            """select u.update_id, u.body, u.posted_at from raw.status_updates as u
               where not exists (select 1 from extract.status_update_signals s where s.update_id = u.update_id and s.extractor = ?)
               order by u.posted_at desc""",
            [extractor_name],
        ).fetchall()
        batch = todo[:max_new] if max_new else todo
        rows = []
        for update_id, body, posted_at in batch:
            e = extract(body, posted_at.date())
            top = max((r.severity for r in e.risks), key=SEVERITY_ORDER.get, default=None)
            rows.append((update_id, extractor_name, e.rag, e.stated_rag, e.blocked, len(e.risks), top,
                         json.dumps([r.model_dump() for r in e.risks]), e.next_milestone_date, e.next_milestone_date_precision,
                         dt.datetime.now()))  # fmt: skip
        if rows:
            con.executemany("insert or replace into extract.status_update_signals values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        return {"extracted": len(rows), "remaining": len(todo) - len(rows)}
