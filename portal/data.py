"""Read models for the portal: every page is one function returning plain JSON-ready data.

All queries read the dbt marts (schema `marts`) read-only. The same functions feed the live API
(`portal.api`) and the static export (`portal.export`), so the two can never disagree.
"""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import duckdb

from simulator.company import COMPANY

IN_FLIGHT = ("not_started", "active", "to_report", "on_hold")
REQUIRED_MARTS = (
    "dim_date", "dim_person", "dim_project", "dim_project_history", "dim_team", "fct_board_reviews", "fct_milestones", "fct_projects",
    "fct_requests", "fct_status_update_signals", "fct_status_updates", "mart_project_risks", "mart_team_portfolio", "mart_tracker_reconciliation",
)  # fmt: skip


class WarehouseNotReady(RuntimeError):
    """The warehouse file exists but lacks marts the portal reads (built by an older dbt project)."""


def _clean(v):
    if isinstance(v, dt.datetime):
        return v.isoformat(timespec="minutes")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, float):
        return round(v, 3)
    return v


class Portal:
    def __init__(self, warehouse: str | Path):
        self.path = Path(warehouse)
        if not self.path.exists():
            raise FileNotFoundError(f"No warehouse at {self.path}; build it first (see README quick start)")
        self.con = duckdb.connect(str(self.path), read_only=True)
        missing = sorted(
            set(REQUIRED_MARTS)
            - {r[0] for r in self.con.execute("select table_name from information_schema.tables where table_schema = 'marts'").fetchall()}
        )
        if missing:
            self.con.close()
            raise WarehouseNotReady(
                f"The warehouse is missing {', '.join(missing)}: it was built by an older version of the dbt project. Rebuild it with "
                "`uv run python -m extractor warehouse --extractor rules` and then `uv run dbt build --project-dir warehouse --profiles-dir warehouse`."
            )
        self.as_of = self._as_of()

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ helpers

    def rows(self, sql: str, params: list | None = None) -> list[dict]:
        cur = self.con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [{c: _clean(v) for c, v in zip(cols, r, strict=True)} for r in cur.fetchall()]

    def one(self, sql: str, params: list | None = None) -> dict:
        r = self.rows(sql, params)
        return r[0] if r else {}

    def scalar(self, sql: str, params: list | None = None):
        r = self.con.execute(sql, params or []).fetchone()
        return _clean(r[0]) if r else None

    def _as_of(self) -> dt.date:
        d = self.con.execute(
            "select coalesce((select max(as_of_date) from marts.mart_project_risks), (select max(posted_at)::date from marts.fct_status_updates))"
        ).fetchone()[0]
        return d or dt.date.today()

    # ------------------------------------------------------------------ pages

    def meta(self) -> dict:
        extractors = self.rows("select extractor, count(*) as updates from marts.fct_status_update_signals group by 1 order by 2 desc")
        return {
            "company": COMPANY["name"].replace(" (fictional)", ""),
            "org": COMPANY["org"],
            "as_of": self.as_of.isoformat(),
            "generated_at": dt.datetime.now().isoformat(timespec="minutes"),
            "extractors": extractors,
            "teams": self.rows(
                "select team_code as code, team_name as name, office, region, meeting_track, manager_name from marts.dim_team "
                "where office <> 'pmo' order by office, team_code"
            ),
        }

    def overview(self) -> dict:
        y = self.as_of.year
        k = self.one(
            f"""
            select
                count(*) filter (where status in {IN_FLIGHT}) as in_flight,
                count(*) filter (where status = 'active') as active,
                count(*) filter (where status = 'to_report') as awaiting_close,
                count(*) filter (where status = 'on_hold') as on_hold,
                count(*) filter (where status = 'not_started') as not_started,
                count(*) filter (where status in {IN_FLIGHT} and office = 'front') as in_flight_front,
                count(*) filter (where status in {IN_FLIGHT} and office = 'middle') as in_flight_middle,
                count(*) filter (where status in {IN_FLIGHT} and is_strategic) as strategic_in_flight,
                count(*) filter (where year(start_date) = {y}) as started_this_year,
                count(*) filter (where status = 'closed' and year(actual_end) = {y}) as closed_this_year,
                sum(milestones_overdue) filter (where status in ('active', 'to_report')) as milestones_overdue
            from marts.fct_projects
            """
        )
        k["red_flags"] = self.scalar("select count(distinct project_id) from marts.mart_project_risks where risk_level = 'high'")
        k["pending_requests"] = self.scalar("select count(*) from marts.fct_requests where request_status = 'pending'")
        k["board_voting"] = self.scalar("select count(*) from marts.fct_board_reviews where review_status = 'voting'")
        quarters = self.rows(
            """
            with q as (
                select date_trunc('quarter', d) as q, kind from (
                    select start_date as d, 'started' as kind from marts.fct_projects
                    union all select actual_end, 'closed' from marts.fct_projects where status = 'closed'
                    union all select actual_end, 'canceled' from marts.fct_projects where status = 'canceled'
                ) where d is not null and d <= ?
            )
            select strftime(q, '%Y') || ' Q' || quarter(q) as quarter,
                   count(*) filter (where kind = 'started') as started,
                   count(*) filter (where kind = 'closed') as closed,
                   count(*) filter (where kind = 'canceled') as canceled
            from q group by q order by q
            """,
            [self.as_of],
        )
        status_by_office = self.rows(
            f"select office, status, count(*) as n from marts.fct_projects where status in {IN_FLIGHT} group by all order by all"
        )
        teams = self.rows("select * from marts.mart_team_portfolio order by office, team_code")
        risks = self.rows(
            """
            select r.project_id, r.project_code, p.project_title, r.team_code, r.category, r.risk_level, r.finding, r.is_strategic
            from marts.mart_project_risks r join marts.dim_project p using (project_id)
            where r.is_main_risk
            order by case r.risk_level when 'high' then 0 when 'mid' then 1 else 2 end, r.is_strategic desc, r.project_code
            limit 8
            """
        )
        # what the latest update of each in-flight project says, typed colour vs content
        reporting = self.one(
            """
            select count(*) as projects,
                   count(*) filter (where s.extracted_rag = 'red') as red,
                   count(*) filter (where s.extracted_rag = 'amber') as amber,
                   count(*) filter (where s.extracted_rag = 'green') as green,
                   count(*) filter (where s.stated_differs_from_content) as stated_differs,
                   count(*) filter (where s.stated_rag = 'green' and s.extracted_rag <> 'green') as stated_green_reads_worse
            from marts.fct_status_update_signals s join marts.fct_projects p using (project_id)
            where s.is_latest_for_project and p.status in ('active', 'to_report')
            """
        )
        return {
            "kpis": k,
            "quarters": quarters[-8:],
            "status_by_office": status_by_office,
            "teams": teams,
            "top_risks": risks,
            "reporting": reporting,
        }

    def projects(self) -> list[dict]:
        return self.rows(
            """
            with main_risk as (
                select project_id, risk_level, category, finding from marts.mart_project_risks where is_main_risk
            ),
            latest as (
                select project_id, extracted_rag, stated_rag, extracted_blocked from marts.fct_status_update_signals where is_latest_for_project
            )
            select p.project_id as id, p.project_code as code, p.project_title as title, p.team_code as team, p.office, p.status,
                   p.strategic_level, p.owner_name as owner, p.owner_has_left, p.start_date, p.planned_end, p.original_end, p.actual_end,
                   p.extension_count, f.milestones_planned, f.milestones_accepted, f.milestones_overdue, f.delivery_ratio,
                   f.days_since_update, r.risk_level, r.category as risk_category, r.finding as risk_finding,
                   l.extracted_rag as rag, l.stated_rag, l.extracted_blocked as blocked
            from marts.dim_project p
            join marts.fct_projects f using (project_id)
            left join main_risk r using (project_id)
            left join latest l using (project_id)
            order by p.start_date desc nulls last, p.project_code desc
            """
        )

    def project(self, project_id: int) -> dict | None:
        head = self.one(
            "select p.*, f.* exclude (project_id, project_code, team_code, office, region, status, is_strategic, strategic_level, owner_id, "
            "start_date, original_end, planned_end, actual_end, extension_count, days_extended) "
            "from marts.dim_project p join marts.fct_projects f using (project_id) where project_id = ?",
            [project_id],
        )
        if not head:
            return None
        head.pop("created_at", None)
        milestones = self.rows(
            "select milestone_seq as seq, milestone_name as name, milestone_status as status, evidence_forms, original_due_date, due_date, "
            "days_moved, accepted_on, is_overdue, days_overdue, submissions, times_returned "
            "from marts.fct_milestones where project_id = ? order by milestone_seq",
            [project_id],
        )
        history = self.rows(
            "select version_no, valid_from, valid_to, status, planned_end, o.display_name as owner "
            "from marts.dim_project_history h left join marts.dim_person o on o.person_id = h.owner_id "
            "where project_id = ? order by version_no",
            [project_id],
        )
        requests = self.rows(
            "select request_id, request_kind, change_types, request_status, request_version, submitted_at, decided_at, decision_days, "
            "requested_new_end, decision_comment, s.display_name as submitted_by "
            "from marts.fct_requests r left join marts.dim_person s on s.person_id = r.submitted_by_id "
            "where project_id = ? order by submitted_at desc",
            [project_id],
        )
        updates = self.rows(
            "select u.update_id, u.posted_at, u.meeting_date, u.meeting_track, u.posted_before_meeting, u.body, a.display_name as author, "
            "s.stated_rag, s.extracted_rag, s.stated_differs_from_content, s.extracted_blocked, s.risks_json, s.extractor, "
            "s.extracted_next_milestone_date "
            "from marts.fct_status_updates u left join marts.fct_status_update_signals s using (update_id) "
            "left join marts.dim_person a on a.person_id = u.author_id "
            "where u.project_id = ? order by u.posted_at desc",
            [project_id],
        )
        for u in updates:
            u["risks"] = json.loads(u.pop("risks_json") or "[]")
        risks = self.rows(
            "select category, risk_level, finding, is_main_risk from marts.mart_project_risks where project_id = ? "
            "order by case risk_level when 'high' then 0 when 'mid' then 1 else 2 end",
            [project_id],
        )
        return {"project": head, "milestones": milestones, "history": history, "requests": requests, "updates": updates, "risks": risks}

    def timeline(self) -> dict:
        projects = self.rows(
            """
            select p.project_id as id, p.project_code as code, p.project_title as title, p.team_code as team, p.office, p.status,
                   p.strategic_level, p.owner_name as owner, p.start_date, p.original_end, p.planned_end, f.delivery_ratio,
                   r.risk_level
            from marts.dim_project p join marts.fct_projects f using (project_id)
            left join marts.mart_project_risks r on r.project_id = p.project_id and r.is_main_risk
            where p.status in ('active', 'to_report', 'on_hold', 'not_started')
            order by p.office, p.team_code, p.start_date
            """
        )
        milestones = self.rows(
            """
            select m.project_id as id, m.milestone_seq as seq, m.milestone_name as name, m.milestone_status as status, m.due_date,
                   m.original_due_date, m.accepted_on, m.is_overdue, m.days_overdue
            from marts.fct_milestones m join marts.dim_project p using (project_id)
            where p.status in ('active', 'to_report', 'on_hold', 'not_started') and m.milestone_status <> 'dropped'
            order by m.project_id, m.milestone_seq
            """
        )
        return {"projects": projects, "milestones": milestones}

    def risks(self) -> dict:
        rows = self.rows(
            """
            select r.finding_key, r.project_id, r.project_code, p.project_title, r.team_code, r.office, r.status, r.is_strategic,
                   r.owner_name, r.category, r.risk_level, r.finding, r.is_main_risk
            from marts.mart_project_risks r join marts.dim_project p using (project_id)
            order by case r.risk_level when 'high' then 0 when 'mid' then 1 else 2 end, r.category, r.project_code
            """
        )
        on_hold = self.rows(
            "select p.project_id, p.project_code, p.project_title, p.team_code, p.owner_name, f.days_since_update "
            "from marts.dim_project p join marts.fct_projects f using (project_id) where p.status = 'on_hold' order by f.days_since_update desc nulls first"
        )
        return {"findings": rows, "on_hold": on_hold}

    def approvals(self) -> dict:
        pending = self.rows(
            """
            select r.request_id, r.request_kind, r.change_types, r.project_id, r.project_code, coalesce(r.requested_title, p.project_title) as title,
                   r.team_code, r.request_version, r.submitted_at, r.requested_new_end, s.display_name as submitted_by,
                   date_diff('day', r.submitted_at::date, ?) as waiting_days
            from marts.fct_requests r
            left join marts.dim_project p using (project_id)
            left join marts.dim_person s on s.person_id = r.submitted_by_id
            where r.request_status = 'pending'
            order by r.submitted_at
            """,
            [self.as_of],
        )
        monthly = self.rows(
            """
            select strftime(date_trunc('month', submitted_at), '%Y-%m') as month, request_kind, count(*) as n,
                   count(*) filter (where request_status = 'returned') as returned
            from marts.fct_requests where submitted_at >= ?::date - interval 12 month
            group by all order by all
            """,
            [self.as_of],
        )
        by_kind = self.rows(
            """
            select request_kind, count(*) as requests,
                   count(*) filter (where request_status in ('approved', 'pre_approved')) as approved,
                   count(*) filter (where request_status = 'returned') as returned,
                   count(*) filter (where request_status = 'rejected') as rejected,
                   median(decision_days) as median_days, quantile_cont(decision_days, 0.9) as p90_days
            from marts.fct_requests group by 1 order by 1
            """
        )
        recent = self.rows(
            """
            select r.request_id, r.request_kind, r.change_types, r.project_id, r.project_code, coalesce(r.requested_title, p.project_title) as title,
                   r.team_code, r.request_status, r.decided_at, r.decision_days, r.decision_comment
            from marts.fct_requests r left join marts.dim_project p using (project_id)
            where r.decided_at is not null order by r.decided_at desc limit 25
            """
        )
        return {"pending": pending, "monthly": monthly, "by_kind": by_kind, "recent": recent}

    def biweekly(self) -> dict:
        tracks = []
        for track in ("front", "middle"):
            meetings = self.rows(
                """
                select meeting_date, count(*) as updates, avg(posted_before_meeting::int) as on_time_share
                from marts.fct_status_updates where meeting_track = ? group by 1 order by 1
                """,
                [track],
            )
            upcoming = next((m for m in meetings if m["meeting_date"] >= self.as_of.isoformat()), None)
            if upcoming is None:
                upcoming = {
                    "meeting_date": self.scalar(
                        "select min(date_day) from marts.dim_date where meeting_track = ? and date_day >= ?", [track, self.as_of]
                    )
                }
            past = [m for m in meetings if m["meeting_date"] < self.as_of.isoformat()]
            target = upcoming["meeting_date"]
            projects = self.rows(
                r"""
                with posted as (
                    select u.project_id, u.posted_at, u.body, s.stated_rag, s.extracted_rag, s.stated_differs_from_content, s.extracted_blocked,
                           s.risk_count, row_number() over (partition by u.project_id order by u.posted_at desc) as rn
                    from marts.fct_status_updates u left join marts.fct_status_update_signals s using (update_id)
                    where u.meeting_date = ?
                )
                select p.project_id as id, p.project_code as code, p.project_title as title, p.team_code as team, p.owner_name as owner,
                       p.strategic_level, u.posted_at, left(regexp_replace(regexp_replace(u.body, '^\s*\d{1,2}/\d{1,2}\s*', ''), '\s+', ' ', 'g'), 220) as summary, u.stated_rag, u.extracted_rag,
                       u.stated_differs_from_content, u.extracted_blocked, u.risk_count
                from marts.dim_project p join marts.dim_team t using (team_code)
                left join posted u on u.project_id = p.project_id and u.rn = 1
                where t.meeting_track = ? and p.status in ('active', 'to_report')
                order by u.posted_at is not null, case u.extracted_rag when 'red' then 0 when 'amber' then 1 else 2 end, p.team_code, p.project_code
                """,
                [target, track],
            )
            tracks.append({"track": track, "upcoming": target, "projects": projects, "history": past[-12:]})
        return {"tracks": tracks}

    def board(self) -> dict:
        reviews = self.rows(
            """
            select b.review_id, b.request_id, b.requested_title, b.team_code, b.strategic_level, b.review_round, b.review_status,
                   b.sent_at, b.closed_at, b.days_to_outcome, b.votes_cast, b.votes_yes, b.votes_no, r.project_id, r.project_code
            from marts.fct_board_reviews b left join marts.fct_requests r using (request_id)
            order by b.sent_at desc
            """
        )
        strategic = self.rows(
            """
            select p.project_id as id, p.project_code as code, p.project_title as title, p.team_code as team, p.status, p.strategic_level,
                   p.owner_name as owner, p.start_date, p.planned_end, f.delivery_ratio, f.milestones_overdue, r.risk_level, r.finding
            from marts.dim_project p join marts.fct_projects f using (project_id)
            left join marts.mart_project_risks r on r.project_id = p.project_id and r.is_main_risk
            where p.is_strategic and p.status in ('active', 'to_report', 'on_hold', 'not_started')
            order by p.strategic_level, p.project_code
            """
        )
        voters = self.rows(
            "select display_name as name, board_role, job_title from marts.dim_person where is_board_voter order by board_role, display_name"
        )
        return {"reviews": reviews, "strategic": strategic, "voters": voters}

    def quality(self) -> dict:
        summary = self.rows(
            "select reconciliation_status as status, count(*) as n from marts.mart_tracker_reconciliation group by 1 order by 2 desc"
        )
        issues = self.rows(
            """
            select r.project_id, r.project_ref, r.team_code, r.sheet_name, r.source_row, r.match_method, r.system_status, r.tracker_status,
                   r.system_planned_end, r.tracker_planned_end, r.reconciliation_status, p.project_title
            from marts.mart_tracker_reconciliation r left join marts.dim_project p using (project_id)
            where r.reconciliation_status <> 'ok' order by r.reconciliation_status, r.team_code, r.project_ref
            """
        )
        week = self.scalar("select max(snapshot_week) from marts.mart_tracker_reconciliation")
        methods = self.rows(
            "select match_method, count(*) as n from marts.mart_tracker_reconciliation where match_method is not null group by 1 order by 2 desc"
        )
        return {"snapshot_week": week, "summary": summary, "issues": issues, "match_methods": methods}


PAGES = ("meta", "overview", "projects", "timeline", "risks", "approvals", "biweekly", "board", "quality")
