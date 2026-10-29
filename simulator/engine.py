"""Day-by-day simulation of the fictional after-sales PMO.

The engine loads the current state of the source database, advances the
organisation one day at a time and writes back only the rows that changed, so
each run continues where the last one stopped.

Delayed decisions (PMO approvals, board votes, evidence reviews,
resubmissions, owner hand-overs, hold reviews) go on an agenda and fire on
their date. Daily checks move projects through milestones, bi-weekly
updates, extensions, closure and the reminder rules R1-R8.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path

from sqlalchemy import Engine, delete, insert, select

from . import calibration as C
from . import schema as S
from .company import (
    CENTRAL_THEMES,
    EVIDENCE_FORMS,
    FINAL_MILESTONE,
    FOLLOW_UP_TYPES,
    MILESTONE_POOL,
    REGIONAL_THEMES,
    RISK_CATEGORIES,
    SECTIONS,
    TEAMS,
)
from .people import make_person, name_variant
from .textgen import write_update

TABLES = {t.name: t for t in S.SOURCE_TABLES}
PK = {t.name: next(iter(t.primary_key.columns)).name for t in S.SOURCE_TABLES}
TEAM_SPEC = {t["code"]: t for t in TEAMS}
IN_FLIGHT = ("not_started", "active", "on_hold", "to_report")
GO_LIVE = dt.date.fromisoformat(C.SYSTEM_GO_LIVE)


def _ts(rng: random.Random, d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(rng.randint(7, 18), rng.randint(0, 59), rng.randint(0, 59)))


def _weighted(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _days(rng: random.Random, span: tuple[int, int]) -> int:
    return rng.randint(*span)


def meeting_date(track: str, on_or_after: dt.date) -> dt.date:
    """Project meetings are on Thursdays; the front-office meeting in even ISO weeks, the middle-office one in odd weeks."""
    d = on_or_after + dt.timedelta(days=(3 - on_or_after.weekday()) % 7)
    while (d.isocalendar().week % 2 == 0) != (track == "front"):
        d += dt.timedelta(days=7)
    return d


class Simulation:
    def __init__(self, engine: Engine, seed: int, data_dir: Path):
        self.engine, self.seed, self.data_dir = engine, seed, data_dir
        S.metadata.create_all(engine)
        self.rows: dict[str, dict[int, dict]] = {}
        self.dirty: dict[str, set[int]] = defaultdict(set)
        self.new_labels: list[dict] = []
        self.weekly_snapshots: list[tuple[dt.date, dict]] = []
        with engine.connect() as c:
            for name, t in TABLES.items():
                self.rows[name] = {r[PK[name]]: dict(r) for r in c.execute(select(t)).mappings()}
            raw = c.execute(select(S.sim_state.c.value).where(S.sim_state.c.key == "state")).scalar()
        self.state = json.loads(raw) if raw else None
        self._index()

    # ------------------------------------------------------------------ plumbing
    def _index(self) -> None:
        self.ms_by_project: dict[int, list[dict]] = defaultdict(list)
        for m in self.rows["milestones"].values():
            self.ms_by_project[m["project_id"]].append(m)
        for lst in self.ms_by_project.values():
            lst.sort(key=lambda m: m["seq"])
        self.meeting_ids = {(m["meeting_date"], m["track"]): m["meeting_id"] for m in self.rows["meetings"].values()}
        self.updates_for = {(u["project_id"], u["meeting_id"]) for u in self.rows["status_updates"].values()}
        self.exec_by_project: dict[int, list[dict]] = defaultdict(list)
        for e in self.rows["project_executors"].values():
            self.exec_by_project[e["project_id"]].append(e)
        self.pending_requests: dict[int, set[int]] = defaultdict(set)
        for r in self.rows["requests"].values():
            if r["status"] == "pending" and r["project_id"]:
                self.pending_requests[r["project_id"]].add(r["request_id"])

    def _ts(self, rng: random.Random, d: dt.date) -> dt.datetime:
        """A time on day d. For the day being simulated, never earlier than the previous
        timestamp handed out, so one day's events are ordered the way they happened."""
        t = _ts(rng, d)
        if d != getattr(self, "_today", None):
            return t
        if self._last_ts and t <= self._last_ts:
            t = min(self._last_ts + dt.timedelta(minutes=rng.randint(1, 20)), dt.datetime.combine(d, dt.time(23, 59, 59)))
        self._last_ts = t
        return t

    def _id(self, table: str) -> int:
        self.state["next_ids"][table] = self.state["next_ids"].get(table, 0) + 1
        return self.state["next_ids"][table]

    def _new(self, table: str, when: dt.datetime, **fields) -> dict:
        row = {PK[table]: self._id(table), **fields, "created_at": when, "updated_at": when}
        self.rows[table][row[PK[table]]] = row
        self.dirty[table].add(row[PK[table]])
        if table == "milestones":
            self.ms_by_project[row["project_id"]].append(row)
        elif table == "project_executors":
            self.exec_by_project[row["project_id"]].append(row)
        return row

    def _touch(self, table: str, row: dict, when: dt.datetime, **changes) -> None:
        row.update(changes, updated_at=when)
        self.dirty[table].add(row[PK[table]])

    def _sched(self, d: dt.date, action: str, **args) -> None:
        self.state["agenda_seq"] = self.state.get("agenda_seq", 0) + 1
        self.state["agenda"].append([d.isoformat(), self.state["agenda_seq"], action, args])

    def _person(self, pid: int | None) -> dict | None:
        return self.rows["people"].get(pid) if pid else None

    def _name(self, rng: random.Random, pid: int) -> str:
        return name_variant(rng, self.state["names"][str(pid)])

    def _pmo_ids(self) -> list[int]:
        return [p["person_id"] for p in self.rows["people"].values() if p["role"] == "pmo" and p["status"] == "active"]

    def _team(self, team_id: int) -> dict:
        return self.rows["teams"][team_id]

    def _staff(self, team_id: int) -> list[dict]:
        return [
            p
            for p in self.rows["people"].values()
            if p["home_team_id"] == team_id and p["status"] == "active" and p["role"] in ("manager", "member")
        ]

    def _manager(self, team_id: int) -> int | None:
        rows = [
            m for m in self.rows["team_managers"].values() if m["team_id"] == team_id and m["valid_to"] is None and m["section"] is None
        ]
        return rows[0]["person_id"] if rows else None

    def _milestones(self, project_id: int) -> list[dict]:
        return self.ms_by_project[project_id]

    def _event(self, p: dict, when, actor, etype, old=None, new=None, note=None) -> None:
        self._new(
            "project_events",
            when,
            project_id=p["project_id"],
            event_at=when,
            actor_id=actor,
            event_type=etype,
            old_value=None if old is None else str(old),
            new_value=None if new is None else str(new),
            note=note,
        )

    def _mail(self, rule: str, when: dt.datetime, to: list, cc: list | None, subject: str, body: str = "", project_id=None) -> None:
        def ids(xs):
            return ",".join(str(x) for x in dict.fromkeys(x for x in xs if x)) or None

        self._new(
            "emails", when, rule=rule, project_id=project_id, to_ids=ids(to), cc_ids=ids(cc or []), subject=subject, body=body, sent_at=when
        )

    def _once(self, key: str) -> bool:
        if key in self.state["sent"]:
            return False
        self.state["sent"][key] = 1
        return True

    def _meeting(self, track: str, d: dt.date) -> int:
        key = (d, track)
        if key not in self.meeting_ids:
            row = self._new("meetings", dt.datetime.combine(d - dt.timedelta(days=14), dt.time(9)), meeting_date=d, track=track)
            self.meeting_ids[key] = row["meeting_id"]
        return self.meeting_ids[key]

    # ------------------------------------------------------------------ setup
    def bootstrap(self, start: dt.date) -> None:
        if self.state:
            return
        self.state = {
            "seed": self.seed,
            "last_date": (start - dt.timedelta(days=1)).isoformat(),
            "next_ids": {},
            "names": {},
            "latent": {},
            "agenda": [],
            "sent": {},
            "codes": {},
        }
        rng = random.Random(f"{self.seed}|bootstrap")
        when = dt.datetime.combine(start, dt.time(9))
        specs = [*TEAMS, {"code": "PMO", "en": "Project Management Office", "group": "P", "region": "HQ"}]
        managers = []
        for spec in specs:
            t = self._new(
                "teams",
                when,
                code=spec["code"],
                name_en=spec["en"],
                team_group=spec["group"],
                region=spec["region"],
                meeting_track="front" if spec["group"] == "R" else "middle",
            )
            if spec["code"] == "PMO":
                for i in range(3):
                    self._hire(rng, t, "pmo", when, "PMO Lead" if i == 0 else "PMO Analyst")
                continue
            mgr = self._hire(rng, t, "manager", when, "After-sales Manager" if spec["group"] == "R" else "Department Manager")
            self._new(
                "team_managers", when, team_id=t["team_id"], person_id=mgr["person_id"], section=None, valid_from=start, valid_to=None
            )
            managers.append(mgr)
            for _ in range(rng.randint(3, 6) if spec["group"] == "R" else rng.randint(4, 8)):
                self._hire(
                    rng, t, "member", when, rng.choice(["Project Manager", "Specialist", "Senior Specialist", "Engineer", "Coordinator"])
                )
            for sec_en in SECTIONS.get(spec["code"], [])[:2]:
                sm = self._hire(rng, t, "manager", when, "Section Manager")
                self._new(
                    "team_managers", when, team_id=t["team_id"], person_id=sm["person_id"], section=sec_en, valid_from=start, valid_to=None
                )
        # review board: steering and execution members vote, an advisor and the secretariat are copied
        board = rng.sample(managers, 10)
        for i, m in enumerate(board):
            role = "steering" if i < 4 else "execution" if i < 9 else "advisor"
            self._touch("people", m, when, board_role=role)
        pmo = [p for p in self.rows["people"].values() if p["role"] == "pmo"]
        self._touch("people", pmo[-1], when, board_role="secretariat")

    def _hire(self, rng: random.Random, team: dict, role: str, when: dt.datetime, title: str) -> dict:
        pid = self._id("people")
        info = make_person(rng, pid, self.seed, team["region"])
        self.state["names"][str(pid)] = info
        row = {
            "person_id": pid,
            "display_name": info["display_name"],
            "email": info["email"],
            "home_team_id": team["team_id"],
            "role": role,
            "job_title": title,
            "board_role": None,
            "status": "active",
            "departed_on": None,
            "created_at": when,
            "updated_at": when,
        }
        self.rows["people"][pid] = row
        self.dirty["people"].add(pid)
        return row

    # ------------------------------------------------------------------ main loop
    def run_until(self, end: dt.date, excel_from: dt.date | None) -> int:
        d = dt.date.fromisoformat(self.state["last_date"]) + dt.timedelta(days=1)
        days = 0
        while d <= end:
            self._step(d)
            if excel_from and d >= excel_from and d.weekday() == 0:
                self.weekly_snapshots.append((d, self._tracker_snapshot(d)))
            self.state["last_date"] = d.isoformat()
            d += dt.timedelta(days=1)
            days += 1
        return days

    def _step(self, d: dt.date) -> None:
        rng = random.Random(f"{self.seed}|{d.isoformat()}")
        self._today, self._last_ts = d, None
        weekday = d.weekday() < 5
        today = d.isoformat()
        due = sorted((a for a in self.state["agenda"] if a[0] <= today), key=lambda a: (a[0], a[1]))
        self.state["agenda"] = [a for a in self.state["agenda"] if a[0] > today]
        for _, _, action, args in due:
            getattr(self, f"_do_{action}")(rng, d, **args)
        if weekday:
            if rng.random() < C.PROPOSALS_PER_WEEKDAY:
                self._propose(rng, d)
            if rng.random() < C.FOLLOW_UPS_PER_WEEKDAY:
                self._pmo_follow_up(rng, d)
            if rng.random() < C.DEPARTURE_PER_DAY * 7 / 5:
                self._departure(rng, d)
        for pid in sorted(int(k) for k in self.state["latent"]):
            p = self.rows["projects"][pid]
            if p["status"] in IN_FLIGHT:
                self._advance(rng, d, p, self.state["latent"][str(pid)])
        if d.weekday() == 3:
            for track in ("front", "middle"):
                if meeting_date(track, d) == d:
                    self._meeting(track, d)
                    self._close_reviews(rng, d, track)
        self._request_reminders(rng, d)

    # ------------------------------------------------------------------ requests
    def _plan_payload(self, rng: random.Random, d: dt.date, team: dict, owner_id: int, applicant_id: int, level=None) -> dict:
        spec = TEAM_SPEC[team["code"]]
        if spec["group"] == "R":
            country = rng.choice(spec["countries"])
            title = rng.choice(REGIONAL_THEMES).format(c=country)
        else:
            country = None
            title = rng.choice(CENTRAL_THEMES[team["code"]])
            if rng.random() < 0.3:
                title += rng.choice([" – Europe", " – Middle East", " – LATAM", " – Africa", " (global)"])
        if rng.random() < 0.12:
            title += f" phase {rng.randint(2, 3)}"
        section = rng.choice(SECTIONS[team["code"]]) if team["code"] in SECTIONS else None
        staff = [p for p in self._staff(team["team_id"]) if p["person_id"] != owner_id]
        others = [
            p
            for p in self.rows["people"].values()
            if p["status"] == "active" and p["role"] == "member" and p["home_team_id"] != team["team_id"]
        ]
        executors = []
        for _ in range(_weighted(rng, C.EXECUTOR_COUNT_WEIGHTS)):
            x = rng.random()
            if x < C.EXTERNAL_EXECUTOR_SHARE:
                label = rng.choice(["Agency partner", "External consultant", "Importer contact", "IT vendor"])
                executors.append({"person_id": None, "name": f"{label} {rng.randint(1, 9)}"})
                continue
            cross = x < C.EXTERNAL_EXECUTOR_SHARE + C.CROSS_TEAM_EXECUTOR_SHARE
            pool = others if (cross and others) or not staff else staff
            if not pool:
                continue
            pick = rng.choice(pool)
            if all(e["person_id"] != pick["person_id"] for e in executors):
                executors.append({"person_id": pick["person_id"], "name": self._name(rng, pick["person_id"])})
        start = d + dt.timedelta(days=rng.randint(-10, 40))
        seg = rng.randrange(len(C.DURATION_DECILES) - 1)
        duration = rng.randint(C.DURATION_DECILES[seg], C.DURATION_DECILES[seg + 1])
        n = _weighted(rng, C.MILESTONE_COUNT_WEIGHTS) + (2 if level else 0)
        picks = sorted(rng.sample(range(len(MILESTONE_POOL)), min(n - 1, len(MILESTONE_POOL))))
        names = [MILESTONE_POOL[i] for i in picks] + [FINAL_MILESTONE]
        ms = []
        for i, name in enumerate(names, 1):
            due = start + dt.timedelta(days=round(duration * i / len(names)))
            ms.append({"name": name, "due": due.isoformat(), "forms": ",".join(rng.sample(EVIDENCE_FORMS, rng.choice([1, 2, 2])))})
        scope = rng.choice(
            [
                f"Deliver {title.lower()} with the {team['name_en']} team.",
                f"{title}. Target: improve service KPIs{' in ' + country if country else ''}.",
                f"Objective: {title.lower()}; owner team {team['name_en']}.",
            ]
        )
        return {
            "title": title,
            "scope": scope,
            "section": section,
            "owner_id": owner_id,
            "owner_name": self._name(rng, owner_id),
            "executors": executors,
            "start": start.isoformat(),
            "end": ms[-1]["due"],
            "milestones": ms,
            "level": level,
            "applicant_id": applicant_id,
            "planning_pending": rng.random() < C.PLANNING_PENDING_SHARE,
        }

    def _propose(self, rng: random.Random, d: dt.date) -> None:
        teams = [t for t in self.rows["teams"].values() if t["team_group"] != "P"]
        team = rng.choices(teams, weights=[TEAM_SPEC[t["code"]]["weight"] for t in teams])[0]
        staff = self._staff(team["team_id"])
        if not staff:
            return
        applicant = rng.choice(staff)
        owner = applicant if rng.random() < 0.7 else rng.choice(staff)
        when = self._ts(rng, d)
        if rng.random() < C.PMO_DIRECT_SHARE:
            payload = self._plan_payload(rng, d, team, owner["person_id"], rng.choice(self._pmo_ids()))
            self._create_project(rng, d, when, team, payload, request=None)
            return
        level = _weighted(rng, C.STRATEGIC_LEVEL_WEIGHTS) if rng.random() < C.STRATEGIC_SHARE else None
        payload = self._plan_payload(rng, d, team, owner["person_id"], applicant["person_id"], level)
        self._submit(rng, d, "new", team["team_id"], None, payload, applicant["person_id"], None, 1, "New project request")

    def _submit(self, rng, d, kind, team_id, project_id, payload, by, change_types, version, reason) -> dict:
        when = self._ts(rng, d)
        r = self._new(
            "requests",
            when,
            kind=kind,
            project_id=project_id,
            team_id=team_id,
            change_types=change_types,
            payload=json.dumps(payload, ensure_ascii=False),
            reason=reason,
            submitted_by=by,
            submitted_at=when,
            version=version,
            status="pending",
            decided_by=None,
            decided_at=None,
            decision_comment=None,
        )
        if project_id:
            self.pending_requests[project_id].add(r["request_id"])
        label = {"new": "New project request", "change": "Change request", "close": "Close request"}[kind]
        title = payload.get("title") or (self.rows["projects"][project_id]["code"] if project_id else "")
        self._mail("event", when, self._pmo_ids()[:1], [], f"[{label}] {title}", f"Submitted by person {by}.", project_id)
        self._sched(d + dt.timedelta(days=_days(rng, C.PMO_DECISION_DAYS)), "pmo_decide", request_id=r["request_id"])
        return r

    def _decide(self, rng, d, r, status, comment=None) -> dt.datetime:
        when = self._ts(rng, d)
        self._touch("requests", r, when, status=status, decided_by=rng.choice(self._pmo_ids()), decided_at=when, decision_comment=comment)
        if r["project_id"]:
            self.pending_requests[r["project_id"]].discard(r["request_id"])
        subj = {"approved": "Approved", "returned": "Returned", "rejected": "Rejected", "pre_approved": "Close pre-approved"}[status]
        self._mail("event", when, [r["submitted_by"]], [], f"[{subj}] request {r['request_id']}", comment or "", r["project_id"])
        return when

    def _do_pmo_decide(self, rng, d, request_id) -> None:
        r = self.rows["requests"][request_id]
        if r["status"] != "pending":
            return
        if r["project_id"] and self.rows["projects"][r["project_id"]]["status"] not in IN_FLIGHT:
            self._decide(rng, d, r, "rejected", "Project is no longer in flight.")
            return
        payload = json.loads(r["payload"])
        odds = {"new": C.NEW_REQUEST_DECISION, "change": C.CHANGE_REQUEST_DECISION, "close": C.CLOSE_REQUEST_DECISION}[r["kind"]]
        outcome = rng.choices(["approve", "return", "reject"], weights=odds)[0]
        if outcome == "return":
            comment = rng.choice(
                [
                    "Please add measurable targets.",
                    "Milestones are not clear.",
                    "Please add budget and resource details.",
                    "Evidence incomplete.",
                ]
            )
            self._decide(rng, d, r, "returned", comment)
            if rng.random() < C.RESUBMIT_AFTER_RETURN:
                self._sched(d + dt.timedelta(days=rng.randint(3, 14)), "resubmit", request_id=request_id)
            elif r["kind"] == "close" and r["project_id"]:
                self.state["latent"].get(str(r["project_id"]), {})["close_filed"] = False
            return
        if outcome == "reject":
            self._decide(
                rng,
                d,
                r,
                "rejected",
                rng.choice(
                    [
                        "Overlaps with an existing project.",
                        "Not a priority this year.",
                        "Does not meet the project criteria; suggest a follow-up item.",
                    ]
                ),
            )
            return
        if r["kind"] == "new":
            if payload.get("level"):
                when = self._decide(rng, d, r, "approved", "Pre-check passed; sent to the review board.")
                self._start_board_review(rng, d, when, r, payload, round_=1)
            else:
                when = self._decide(rng, d, r, "approved")
                self._create_project(rng, d, when, self._team(r["team_id"]), payload, request=r)
        elif r["kind"] == "change":
            when = self._decide(rng, d, r, "approved")
            self._apply_change(rng, d, when, self.rows["projects"][r["project_id"]], payload)
        else:  # close
            when = self._decide(rng, d, r, "pre_approved", "Please present the close at the next project meeting.")
            p = self.rows["projects"][r["project_id"]]
            if p["status"] in ("active", "not_started"):
                self._set_status(p, when, "to_report", r["decided_by"])

    def _do_resubmit(self, rng, d, request_id) -> None:
        r = self.rows["requests"][request_id]
        if r["project_id"] and self.rows["projects"][r["project_id"]]["status"] not in IN_FLIGHT:
            return
        payload = json.loads(r["payload"])
        self._submit(
            rng, d, r["kind"], r["team_id"], r["project_id"], payload, r["submitted_by"], r["change_types"], r["version"] + 1, r["reason"]
        )

    # ------------------------------------------------------------------ review board
    def _voters(self) -> list[int]:
        return sorted(
            p["person_id"] for p in self.rows["people"].values() if p["board_role"] in ("steering", "execution") and p["status"] == "active"
        )

    def _start_board_review(self, rng, d, when, r, payload, round_) -> None:
        rev = self._new(
            "board_reviews",
            when,
            request_id=r["request_id"],
            level=payload["level"],
            round=round_,
            sent_at=when,
            status="voting",
            closed_at=None,
        )
        voters = self._voters()
        cc = [p["person_id"] for p in self.rows["people"].values() if p["board_role"] in ("advisor", "secretariat")]
        self._mail("event", when, voters, cc, f"[Board approval] {payload['level']} · {payload['title']}", "Please vote in the system.")
        for v in voters:
            self._sched(d + dt.timedelta(days=_days(rng, C.BOARD_VOTE_DAYS)), "board_vote", review_id=rev["review_id"], person_id=v)

    def _do_board_vote(self, rng, d, review_id, person_id) -> None:
        rev = self.rows["board_reviews"][review_id]
        if rev["status"] != "voting" or self.rows["people"][person_id]["status"] != "active":
            return
        when = self._ts(rng, d)
        yes = rng.random() < C.BOARD_YES
        comment = (
            None if yes else rng.choice(["Business case too thin.", "Overlaps with another market's project.", "Resourcing is unclear."])
        )
        self._new(
            "board_votes", when, review_id=review_id, person_id=person_id, vote="yes" if yes else "no", comment=comment, voted_at=when
        )
        r = self.rows["requests"][rev["request_id"]]
        payload = json.loads(r["payload"])
        if not yes:
            self._touch("board_reviews", rev, when, status="revise", closed_at=when)
            self._mail("event", when, self._pmo_ids()[:1] + [r["submitted_by"]], [], f"[Board sent back] {payload['title']}")
            self._sched(d + dt.timedelta(days=_days(rng, C.BOARD_RESUBMIT_DAYS)), "board_resubmit", review_id=review_id)
            return
        votes = {v["person_id"] for v in self.rows["board_votes"].values() if v["review_id"] == review_id and v["vote"] == "yes"}
        if set(self._voters()) <= votes:
            self._touch("board_reviews", rev, when, status="approved", closed_at=when)
            self._create_project(rng, d, when, self._team(r["team_id"]), payload, request=r)

    def _do_board_resubmit(self, rng, d, review_id) -> None:
        rev = self.rows["board_reviews"][review_id]
        r = self.rows["requests"][rev["request_id"]]
        self._start_board_review(rng, d, self._ts(rng, d), r, json.loads(r["payload"]), rev["round"] + 1)

    # ------------------------------------------------------------------ projects
    def _code(self, team: dict, d: dt.date, prefix: str = "") -> str:
        key = f"{team['code']}-{d:%y}-{prefix}"
        self.state["codes"][key] = self.state["codes"].get(key, 0) + 1
        n = self.state["codes"][key]
        return f"{team['code']}-{d:%y}-{prefix}{n:02d}" if prefix else f"{team['code']}-{d:%y}-{n:03d}"

    def _create_project(self, rng, d, when, team, payload, request) -> dict:
        level = payload.get("level")
        pending = payload.get("planning_pending")
        legacy = None
        if d < GO_LIVE:
            self.state["codes"]["TRK"] = self.state["codes"].get("TRK", 0) + 1
            legacy = f"TRK{d.year}-{self.state['codes']['TRK']:03d}"
        start = None if pending else dt.date.fromisoformat(payload["start"])
        end = None if pending else dt.date.fromisoformat(payload["end"])
        p = self._new(
            "projects",
            when,
            code=self._code(team, d, "A" if level else ""),
            legacy_code=legacy,
            team_id=team["team_id"],
            section=payload.get("section"),
            title=payload["title"],
            scope=payload["scope"],
            owner_id=payload["owner_id"],
            owner_name=payload["owner_name"],
            status="not_started" if pending or start > d else "active",
            strategic_level=level,
            start_date=start,
            planned_end=end,
            original_end=end,
            actual_end=None,
            extension_count=0,
            is_deleted=False,
        )
        actor = request["decided_by"] if request else payload["applicant_id"]
        self._event(p, when, actor, "created", None, p["status"], f"request {request['request_id']}" if request else "set up by PMO")
        if request:
            self._touch("requests", request, when, project_id=p["project_id"])
        for e in payload["executors"]:
            self._new(
                "project_executors", when, project_id=p["project_id"], person_id=e["person_id"], executor_name=e["name"], removed=False
            )
        if not pending:
            self._add_milestones(when, p, payload["milestones"])
        to = [payload["owner_id"], *(e["person_id"] for e in payload["executors"])]
        self._mail("event", when, to, [self._manager(team["team_id"])], f"[Project set up] {p['code']} {p['title']}", "", p["project_id"])
        self.state["latent"][str(p["project_id"])] = {
            "owner": payload["owner_id"],
            "diligence": round(rng.betavariate(5, 2), 3),
            "propensity": round(rng.betavariate(2, 4), 3),
            "risks": [],
            "blocked_until": None,
            "close_filed": False,
            "track": team["meeting_track"],
        }
        if pending:
            self._sched(d + dt.timedelta(days=rng.randint(20, 90)), "plan_project", project_id=p["project_id"], payload=payload)
        return p

    def _add_milestones(self, when, p, ms) -> None:
        for i, m in enumerate(ms, 1):
            due = dt.date.fromisoformat(m["due"])
            self._new(
                "milestones",
                when,
                project_id=p["project_id"],
                seq=i,
                name=m["name"],
                evidence_forms=m["forms"],
                original_due_date=due,
                due_date=due,
                status="open",
                accepted_on=None,
            )

    def _do_plan_project(self, rng, d, project_id, payload) -> None:
        p = self.rows["projects"][project_id]
        if p["status"] != "not_started":
            return
        when = self._ts(rng, d)
        shift = (d - dt.date.fromisoformat(payload["start"])).days + rng.randint(0, 20)
        ms = [{**m, "due": (dt.date.fromisoformat(m["due"]) + dt.timedelta(days=shift)).isoformat()} for m in payload["milestones"]]
        start = dt.date.fromisoformat(payload["start"]) + dt.timedelta(days=shift)
        end = dt.date.fromisoformat(ms[-1]["due"])
        self._touch("projects", p, when, start_date=start, planned_end=end, original_end=end)
        self._add_milestones(when, p, ms)
        self._event(p, when, None, "end_date", None, end.isoformat(), "plan completed")

    def _set_status(self, p, when, new, actor=None, note=None) -> None:
        old = p["status"]
        changes = {"status": new}
        if new in ("closed", "canceled"):
            changes["actual_end"] = when.date()
            if new == "canceled":
                for m in self._milestones(p["project_id"]):
                    if m["status"] in ("open", "returned", "submitted"):
                        self._touch("milestones", m, when, status="dropped")
            self.state["latent"].pop(str(p["project_id"]), None)
        self._touch("projects", p, when, **changes)
        self._event(p, when, actor, "status", old, new, note)

    def _apply_change(self, rng, d, when, p, payload) -> None:
        lat = self.state["latent"].get(str(p["project_id"]), {})
        if "new_end" in payload and p["planned_end"]:
            new_end = dt.date.fromisoformat(payload["new_end"])
            shift = (new_end - p["planned_end"]).days
            ms = self._milestones(p["project_id"])
            for m in ms[:-1]:
                if m["status"] in ("open", "returned"):
                    self._touch("milestones", m, when, due_date=max(m["due_date"] + dt.timedelta(days=shift), d + dt.timedelta(days=7)))
            if ms and ms[-1]["status"] in ("open", "returned"):
                self._touch("milestones", ms[-1], when, due_date=new_end)
            self._event(p, when, None, "end_date", p["planned_end"], new_end, payload.get("reason"))
            self._touch("projects", p, when, planned_end=new_end, extension_count=p["extension_count"] + 1)
        if "new_owner_id" in payload:
            self._event(p, when, None, "owner", p["owner_id"], payload["new_owner_id"])
            self._touch("projects", p, when, owner_id=payload["new_owner_id"], owner_name=payload["new_owner_name"])
            lat["owner"] = payload["new_owner_id"]
        if "add_executor" in payload:
            e = payload["add_executor"]
            self._new(
                "project_executors", when, project_id=p["project_id"], person_id=e["person_id"], executor_name=e["name"], removed=False
            )
            self._event(p, when, None, "executors", None, e["name"])

    def _request_change(self, rng, d, p, lat, change_types: str, payload: dict, reason: str) -> None:
        if self.pending_requests[p["project_id"]]:
            return
        by = lat.get("owner") or p["owner_id"]
        if not self._person(by) or self._person(by)["status"] != "active":
            by = self._manager(p["team_id"]) or by
        self._submit(rng, d, "change", p["team_id"], p["project_id"], payload, by, change_types, 1, reason)

    # ------------------------------------------------------------------ daily project logic
    def _advance(self, rng: random.Random, d: dt.date, p: dict, lat: dict) -> None:
        when = self._ts(rng, d)
        if p["status"] == "not_started":
            if p["start_date"] and p["start_date"] <= d:
                self._set_status(p, when, "active")
            return
        if p["status"] == "on_hold":
            return
        self._evolve_risks(rng, d, lat)
        ms = self._milestones(p["project_id"])
        open_ms = [m for m in ms if m["status"] in ("open", "returned", "submitted")]
        owner = lat["owner"]
        team = self._team(p["team_id"])
        mgr = self._manager(p["team_id"])
        execs = [e["person_id"] for e in self.exec_by_project[p["project_id"]] if not e["removed"] and e["person_id"]]
        blocked = lat["blocked_until"] is not None
        if p["status"] == "active":
            if self._milestone_work(rng, d, when, p, lat, ms, open_ms, owner, mgr, execs, blocked):
                return
        self._biweekly(rng, d, when, p, lat, team, mgr, open_ms, blocked)

    def _milestone_work(self, rng, d, when, p, lat, ms, open_ms, owner, mgr, execs, blocked) -> bool:
        """Evidence, overdue rules, extensions, closing, holds. Returns True if the project left 'active'."""
        nxt = next((m for m in open_ms if m["status"] in ("open", "returned")), None)
        slow = 0.3 if blocked else 1.0
        if nxt:
            days_to = (nxt["due_date"] - d).days
            if 0 < days_to <= C.REMINDER_LEAD_DAYS and nxt is not ms[-1] and self._once(f"R1|{nxt['milestone_id']}|{nxt['due_date']}"):
                self._mail(
                    "R1",
                    when,
                    [owner, *execs],
                    [],
                    f"[Milestone ahead] {p['code']} · due in {days_to} days: {nxt['name']}",
                    f"Evidence expected: {nxt['evidence_forms']}",
                    p["project_id"],
                )
            if days_to <= 4:
                # most evidence comes in during the last few days; once overdue, it trickles in
                chance = (0.2 if days_to >= 0 else 0.06) * lat["diligence"] * slow
                if rng.random() < chance:
                    self._submit_evidence(rng, d, when, nxt, owner)
                    nxt = None
            if nxt and days_to < 0:
                od = -days_to
                if od == 1 and self._once(f"R3|{nxt['milestone_id']}|{nxt['due_date']}"):
                    self._mail(
                        "R3",
                        when,
                        self._pmo_ids()[:1],
                        [owner],
                        f"[Not submitted] {p['code']} · overdue: {nxt['name']}",
                        "",
                        p["project_id"],
                    )
                if od >= 7 and self._once(f"R4|{nxt['milestone_id']}|{nxt['due_date']}"):
                    self._mail(
                        "R4",
                        when,
                        [owner, mgr],
                        self._pmo_ids()[:1],
                        f"[Escalation] {p['code']} milestone overdue {od} days",
                        "",
                        p["project_id"],
                    )
                if od > 3 and rng.random() < 0.04 + 0.05 * lat["propensity"]:
                    new_end = max(p["planned_end"] or d, d) + dt.timedelta(days=rng.randint(30, 120))
                    reason = rng.choice(
                        [
                            "Supplier delay",
                            "Waiting for HQ decision",
                            "Resource constraints",
                            "Dealer readiness",
                            "Not enough resources",
                            "IT release not live yet",
                        ]
                    )
                    self._request_change(rng, d, p, lat, "end", {"new_end": new_end.isoformat(), "reason": reason}, reason)
        elif not open_ms and ms and not lat["close_filed"]:
            lat["close_filed"] = True
            self._sched(d + dt.timedelta(days=rng.randint(0, 6)), "file_close", project_id=p["project_id"])
        if p["planned_end"]:
            de = (p["planned_end"] - d).days
            if 0 < de <= C.REMINDER_LEAD_DAYS and self._once(f"R2|{p['project_id']}|{p['planned_end']}"):
                self._mail(
                    "R2",
                    when,
                    [owner, *execs],
                    self._pmo_ids()[:1],
                    f"[Prepare close report] {p['code']} ends in {de} days",
                    "",
                    p["project_id"],
                )
            if de < 0 and not self.pending_requests[p["project_id"]] and not lat["close_filed"]:
                if self._once(f"R5|{p['project_id']}|{p['planned_end']}"):
                    self._mail("R5", when, self._pmo_ids()[:1], [], f"[Past end] {p['code']} is past its end date", "", p["project_id"])
                if -de > C.STALE_CANCEL_AFTER_DAYS and rng.random() < C.STALE_CANCEL_PER_DAY:
                    self._set_status(p, when, "canceled", rng.choice(self._pmo_ids()), "Past end date, no plan to continue")
                    return True
                if rng.random() < 0.05:
                    new_end = d + dt.timedelta(days=rng.randint(30, 120))
                    self._request_change(
                        rng, d, p, lat, "end", {"new_end": new_end.isoformat(), "reason": "Plan re-baselined"}, "Plan re-baselined"
                    )
        if rng.random() < C.HOLD_PER_DAY:
            reason = rng.choice(["Waiting for budget", "Priorities changed", "Owner unavailable", "Waiting for HQ decision"])
            self._set_status(p, when, "on_hold", rng.choice(self._pmo_ids()), reason)
            self._sched(d + dt.timedelta(days=_days(rng, C.HOLD_REVIEW_DAYS)), "hold_review", project_id=p["project_id"])
            return True
        if rng.random() < 0.0015 and not self.pending_requests[p["project_id"]]:
            staff = [s for s in self._staff(p["team_id"]) if s["person_id"] not in execs and s["person_id"] != owner]
            if staff:
                s = rng.choice(staff)
                self._request_change(
                    rng,
                    d,
                    p,
                    lat,
                    "exec",
                    {"add_executor": {"person_id": s["person_id"], "name": self._name(rng, s["person_id"])}},
                    "More hands needed",
                )
        return False

    def _do_file_close(self, rng, d, project_id) -> None:
        p = self.rows["projects"][project_id]
        lat = self.state["latent"].get(str(project_id))
        if not lat or p["status"] != "active":
            return
        if self.pending_requests[project_id]:
            self._sched(d + dt.timedelta(days=5), "file_close", project_id=project_id)
            return
        by = lat["owner"] if self._person(lat["owner"])["status"] == "active" else (self._manager(p["team_id"]) or lat["owner"])
        self._submit(rng, d, "close", p["team_id"], project_id, {"summary": "All deliverables accepted."}, by, None, 1, "Request to close")

    def _evolve_risks(self, rng, d, lat) -> None:
        prop = lat["propensity"]
        lat["risks"] = [r for r in lat["risks"] if dt.date.fromisoformat(r["until"]) > d]
        if rng.random() < 0.012 + 0.035 * prop and len(lat["risks"]) < 3:
            used = {r["category"] for r in lat["risks"]}
            cat = rng.choice([c for c in RISK_CATEGORIES if c not in used])
            sev = rng.choices(["low", "medium", "high"], weights=[4 - 2 * prop, 3, 0.5 + 3 * prop])[0]
            lat["risks"].append({"category": cat, "severity": sev, "until": (d + dt.timedelta(days=rng.randint(14, 60))).isoformat()})
        for r in lat["risks"]:
            if r["severity"] != "high" and rng.random() < 0.006:
                r["severity"] = "medium" if r["severity"] == "low" else "high"
        if lat["blocked_until"] and dt.date.fromisoformat(lat["blocked_until"]) <= d:
            lat["blocked_until"] = None
        if not lat["blocked_until"] and any(r["severity"] == "high" for r in lat["risks"]) and rng.random() < 0.02:
            lat["blocked_until"] = (d + dt.timedelta(days=rng.randint(7, 30))).isoformat()

    def _submit_evidence(self, rng, d, when, m, by) -> None:
        form = rng.choice(m["evidence_forms"].split(","))
        note = rng.choice(
            [
                "Deliverable attached.",
                "See email from the importer.",
                "Screenshot of the dashboard.",
                "Results in the attached file.",
                "Training attendance list attached.",
            ]
        )
        att = {
            "screenshot": "screenshot.png",
            "email": "confirmation.msg",
            "file": rng.choice(["report.pdf", "plan.xlsx", "slides.pptx"]),
        }.get(form)
        s = self._new(
            "milestone_submissions",
            when,
            milestone_id=m["milestone_id"],
            submitted_by=by,
            submitted_at=when,
            form=form,
            note=note,
            attachment_name=att,
            review_status="pending",
            reviewed_by=None,
            reviewed_at=None,
            review_comment=None,
        )
        self._touch("milestones", m, when, status="submitted")
        self._sched(d + dt.timedelta(days=_days(rng, C.EVIDENCE_REVIEW_DAYS)), "review_evidence", submission_id=s["submission_id"])

    def _do_review_evidence(self, rng, d, submission_id) -> None:
        s = self.rows["milestone_submissions"][submission_id]
        m = self.rows["milestones"][s["milestone_id"]]
        if m["status"] != "submitted":
            return
        when = self._ts(rng, d)
        if rng.random() < C.EVIDENCE_ACCEPT:
            self._touch(
                "milestone_submissions", s, when, review_status="accepted", reviewed_by=rng.choice(self._pmo_ids()), reviewed_at=when
            )
            self._touch("milestones", m, when, status="accepted", accepted_on=d)
        else:
            comment = rng.choice(
                ["Incomplete; please add the results.", "Results incomplete, please complete and resubmit.", "Attachment missing."]
            )
            self._touch(
                "milestone_submissions",
                s,
                when,
                review_status="returned",
                reviewed_by=rng.choice(self._pmo_ids()),
                reviewed_at=when,
                review_comment=comment,
            )
            self._touch(
                "milestones",
                m,
                when,
                status="returned",
                due_date=max(m["due_date"], d + dt.timedelta(days=_days(rng, C.EVIDENCE_RESUBMIT_DAYS))),
            )
            p = self.rows["projects"][m["project_id"]]
            self._mail("event", when, [s["submitted_by"]], [], f"[Evidence returned] {p['code']} {m['name']}", comment, p["project_id"])

    def _biweekly(self, rng, d, when, p, lat, team, mgr, open_ms, blocked) -> None:
        meet = meeting_date(lat["track"], d)
        days_before = (meet - d).days
        if days_before > 10:
            return
        mid = self._meeting(lat["track"], meet)
        if (p["project_id"], mid) in self.updates_for:
            return
        if days_before == C.BIWEEKLY_REMINDER_DAYS_BEFORE and self._once(f"R6|{p['project_id']}|{meet}"):
            track = "Front-office" if lat["track"] == "front" else "Middle-office"
            self._mail(
                "R6", when, [lat["owner"]], [mgr], f"[Two-week progress] {p['code']} · {track} meeting {meet:%d/%m}", "", p["project_id"]
            )
        chance = 0.11 if days_before > C.BIWEEKLY_REMINDER_DAYS_BEFORE else 0.3 if days_before > 0 else 0.15
        if rng.random() >= chance * lat["diligence"]:
            return
        nxt = next((m for m in open_ms if m["status"] in ("open", "returned")), None)
        staff = self._staff(team["team_id"])
        spec = TEAM_SPEC.get(team["code"], {})
        ctx = {
            "team": team["name_en"],
            "country": rng.choice(spec.get("countries") or ["Spain", "Brazil", "UAE", "Morocco", "Germany", "Mexico"]),
            "colleague": self._name(rng, rng.choice(staff)["person_id"]) if staff else "a colleague",
            "track": lat["track"],
            "risks": [{"category": r["category"], "severity": r["severity"]} for r in lat["risks"]],
            "blocked": blocked,
            "overdue_days": max(0, (d - nxt["due_date"]).days) if nxt else 0,
            "next_milestone": (nxt["name"], nxt["due_date"]) if nxt else None,
            "as_of": d,
        }
        body, label = write_update(rng, ctx)
        author = lat["owner"] if rng.random() < 0.85 or not staff else rng.choice(staff)["person_id"]
        u = self._new("status_updates", when, project_id=p["project_id"], meeting_id=mid, author_id=author, posted_at=when, body=body)
        self.updates_for.add((p["project_id"], mid))
        self.new_labels.append({"update_id": u["update_id"], "project_id": p["project_id"], "as_of": d.isoformat(), **label})

    def _close_reviews(self, rng, d, track) -> None:
        queue = [
            p
            for p in sorted(self.rows["projects"].values(), key=lambda x: x["updated_at"])
            if p["status"] == "to_report" and self._team(p["team_id"])["meeting_track"] == track
        ]
        presented = [p for p in queue if rng.random() < C.OWNER_READY_TO_PRESENT][: C.CLOSE_REVIEWS_PER_MEETING]
        for p in presented:
            when = self._ts(rng, d)
            team = self._team(p["team_id"])
            if rng.random() < C.CLOSE_AT_MEETING:
                self._event(p, when, None, "closed_meeting", None, None, f"{track} meeting {d}")
                self._mail(
                    "event",
                    when,
                    [p["owner_id"]],
                    [self._manager(team["team_id"])],
                    f"[Closed] {p['code']} {p['title']}",
                    "",
                    p["project_id"],
                )
                self._set_status(p, when, "closed")
                if rng.random() < C.POSTCLOSE_FOLLOW_UP_SHARE:
                    self._new_follow_up(rng, d, team, "postclose", f"Post-close monitoring: {p['title']}", p["owner_id"], p["project_id"])
            else:
                self._set_status(p, when, "active", None, "Not approved at the meeting; back to in progress")
                lat = self.state["latent"].get(str(p["project_id"]))
                ms = self._milestones(p["project_id"])
                if lat and ms:
                    lat["close_filed"] = False
                    self._touch(
                        "milestones", ms[-1], when, status="open", accepted_on=None, due_date=d + dt.timedelta(days=rng.randint(14, 40))
                    )

    def _do_hold_review(self, rng, d, project_id) -> None:
        p = self.rows["projects"][project_id]
        if p["status"] != "on_hold":
            return
        when = self._ts(rng, d)
        outcome = _weighted(rng, C.HOLD_OUTCOME)
        pmo = rng.choice(self._pmo_ids())
        if outcome == "resume":
            ms = self._milestones(project_id)
            for m in ms:
                if m["status"] in ("open", "returned"):
                    self._touch("milestones", m, when, due_date=max(m["due_date"], d) + dt.timedelta(days=rng.randint(14, 45)))
            if ms and p["planned_end"] and ms[-1]["due_date"] > p["planned_end"]:
                self._event(p, when, pmo, "end_date", p["planned_end"], ms[-1]["due_date"], "re-planned after hold")
                self._touch("projects", p, when, planned_end=ms[-1]["due_date"])
            self._set_status(p, when, "active", pmo, "Resumed after hold review")
        elif outcome == "cancel":
            self._set_status(p, when, "canceled", pmo, "Canceled after hold review")
        else:
            self._set_status(p, when, "canceled", pmo, "Converted to a follow-up item")
            self._new_follow_up(rng, d, self._team(p["team_id"]), "monitor", p["title"], p["owner_id"], project_id)

    # ------------------------------------------------------------------ follow-ups, people, reminders
    def _new_follow_up(self, rng, d, team, ftype, title, owner_id, source_project_id=None) -> None:
        when = self._ts(rng, d)
        f = self._new(
            "follow_ups",
            when,
            code=self._code(team, d, "F"),
            team_id=team["team_id"],
            follow_up_type=ftype,
            title=title,
            owner_id=owner_id,
            source_project_id=source_project_id,
            converted_project_id=None,
            status="open",
            closed_on=None,
        )
        self._mail(
            "event", when, [owner_id], [self._manager(team["team_id"])], f"[New follow-up] {f['code']} {title}", FOLLOW_UP_TYPES[ftype]
        )
        self._sched(d + dt.timedelta(days=rng.randint(30, 150)), "close_follow_up", follow_up_id=f["follow_up_id"])

    def _pmo_follow_up(self, rng, d) -> None:
        teams = [t for t in self.rows["teams"].values() if t["team_group"] != "P"]
        team = rng.choice(teams)
        staff = self._staff(team["team_id"])
        if not staff:
            return
        spec = TEAM_SPEC[team["code"]]
        title = (
            rng.choice(REGIONAL_THEMES).format(c=rng.choice(spec["countries"]))
            if spec["group"] == "R"
            else rng.choice(CENTRAL_THEMES[team["code"]])
        )
        self._new_follow_up(rng, d, team, rng.choice(["incubate", "monitor", "monitor"]), title, rng.choice(staff)["person_id"])

    def _do_close_follow_up(self, rng, d, follow_up_id) -> None:
        f = self.rows["follow_ups"][follow_up_id]
        if f["status"] != "open":
            return
        when = self._ts(rng, d)
        converted = None
        owner = self._person(f["owner_id"])
        if f["follow_up_type"] == "incubate" and rng.random() < 0.3 and owner and owner["status"] == "active":
            team = self._team(f["team_id"])
            payload = self._plan_payload(rng, d, team, f["owner_id"], rng.choice(self._pmo_ids()))
            payload["title"] = f["title"]
            converted = self._create_project(rng, d, when, team, payload, request=None)["project_id"]
        self._touch("follow_ups", f, when, status="closed", closed_on=d, converted_project_id=converted)

    def _departure(self, rng, d) -> None:
        when = self._ts(rng, d)
        staff = sorted(
            (p for p in self.rows["people"].values() if p["status"] == "active" and p["role"] in ("manager", "member")),
            key=lambda p: p["person_id"],
        )
        if not staff:
            return
        leaver = rng.choice(staff)
        self._touch("people", leaver, when, status="departed", departed_on=d)
        team = self._team(leaver["home_team_id"])
        repl = None
        if leaver["role"] == "manager" or rng.random() < C.REPLACE_MEMBER:
            repl = self._hire(rng, team, leaver["role"], when, leaver["job_title"])
            if leaver["board_role"]:
                self._touch("people", repl, when, board_role=leaver["board_role"])
                self._touch("people", leaver, when, board_role=None)
                # the replacement takes over the leaver's seat in open board votes
                for rev in self.rows["board_reviews"].values():
                    if rev["status"] == "voting" and leaver["board_role"] in ("steering", "execution"):
                        self._sched(
                            d + dt.timedelta(days=_days(rng, C.BOARD_VOTE_DAYS)),
                            "board_vote",
                            review_id=rev["review_id"],
                            person_id=repl["person_id"],
                        )
        for tm in [m for m in self.rows["team_managers"].values() if m["person_id"] == leaver["person_id"] and m["valid_to"] is None]:
            self._touch("team_managers", tm, when, valid_to=d)
            if repl:
                self._new(
                    "team_managers",
                    when,
                    team_id=tm["team_id"],
                    person_id=repl["person_id"],
                    section=tm["section"],
                    valid_from=d,
                    valid_to=None,
                )
        for pid, lat in sorted(self.state["latent"].items(), key=lambda kv: int(kv[0])):
            if lat["owner"] == leaver["person_id"]:
                self._sched(d + dt.timedelta(days=_days(rng, C.OWNER_REASSIGN_DAYS)), "reassign_owner", project_id=int(pid))

    def _do_reassign_owner(self, rng, d, project_id) -> None:
        p = self.rows["projects"][project_id]
        lat = self.state["latent"].get(str(project_id))
        if not lat or p["status"] not in IN_FLIGHT or self._person(lat["owner"])["status"] == "active":
            return
        staff = self._staff(p["team_id"])
        if not staff:
            return
        if self.pending_requests[project_id]:
            self._sched(d + dt.timedelta(days=7), "reassign_owner", project_id=project_id)
            return
        new = rng.choice(staff)
        payload = {"new_owner_id": new["person_id"], "new_owner_name": self._name(rng, new["person_id"])}
        self._request_change(rng, d, p, lat, "owner", payload, "Previous owner left the company")

    def _request_reminders(self, rng, d) -> None:
        when = self._ts(rng, d)
        for rid in sorted({r for s in self.pending_requests.values() for r in s}):
            r = self.rows["requests"][rid]
            if (d - r["submitted_at"].date()).days >= 3 and self._once(f"R7|{rid}"):
                self._mail("R7", when, self._pmo_ids()[:1], [], f"[Approval waiting] request {rid} ({r['kind']})", "", r["project_id"])
        for rev in sorted(self.rows["board_reviews"].values(), key=lambda x: x["review_id"]):
            if rev["status"] == "voting" and (d - rev["sent_at"].date()).days >= 3:
                voted = {v["person_id"] for v in self.rows["board_votes"].values() if v["review_id"] == rev["review_id"]}
                pending = [v for v in self._voters() if v not in voted]
                if pending and self._once(f"R8|{rev['review_id']}"):
                    self._mail("R8", when, pending, self._pmo_ids()[:1], f"[Board vote reminder] review {rev['review_id']}")

    # ------------------------------------------------------------------ legacy tracker snapshot
    def _status_at(self, p: dict, d: dt.date) -> str:
        """Project status as of date d, rebuilt from the event log (the tracker is often behind)."""
        status = None
        for e in self.events_by_project.get(p["project_id"], []):
            if e["event_type"] in ("created", "status") and e["event_at"].date() <= d:
                status = e["new_value"]
        return status or p["status"]

    def _tracker_snapshot(self, d: dt.date) -> dict:
        """What each team's sheet in the old Excel tracker shows that Monday; some rows lag behind."""
        self.events_by_project = defaultdict(list)
        for e in sorted(self.rows["project_events"].values(), key=lambda e: e["event_id"]):
            self.events_by_project[e["project_id"]].append(e)
        latest = {}
        for u in self.rows["status_updates"].values():
            if u["posted_at"].date() <= d and (u["project_id"] not in latest or u["posted_at"] > latest[u["project_id"]]["posted_at"]):
                latest[u["project_id"]] = u
        rng = random.Random(f"{self.seed}|tracker|{d}")
        out = defaultdict(list)
        for p in sorted(self.rows["projects"].values(), key=lambda x: x["project_id"]):
            if p["is_deleted"] or p["created_at"].date() > d:
                continue
            # per-project habits, stable from week to week: some new projects reach the sheet
            # weeks late, and a few references are typed wrong every time
            habit = random.Random(f"{self.seed}|tracker-habit|{p['project_id']}")
            added_after = habit.randint(7, 42) if habit.random() < 0.3 else 0
            typo = habit.random() < 0.04
            if (d - p["created_at"].date()).days < added_after:
                continue
            lag = rng.random() < 0.2
            status = self._status_at(p, d - dt.timedelta(days=rng.randint(14, 35)) if lag else d)
            if status in ("closed", "canceled") and p["actual_end"] and (d - p["actual_end"]).days > 120:
                continue  # old finished projects get archived off the sheet
            u = latest.get(p["project_id"])
            code = p["code"]
            if typo:
                head, _, num = code.rpartition("-")
                code = f"{head}-{num.lstrip('0') or num}" if num.startswith("0") else f"{head}-{num[::-1]}"
            out[self._team(p["team_id"])["code"]].append(
                {
                    "code": code,
                    "legacy_code": None if typo else p["legacy_code"],
                    "title": p["title"],
                    "owner": p["owner_name"],
                    "status": status,
                    "start": p["start_date"],
                    "end": p["planned_end"],
                    "update": (u["body"] if u and not lag else ""),
                    "ext": p["extension_count"],
                }
            )
        return dict(out)

    # ------------------------------------------------------------------ persistence
    def save(self) -> dict[str, int]:
        counts = {}
        with self.engine.begin() as c:
            for name, ids in self.dirty.items():
                if not ids:
                    continue
                t = TABLES[name]
                ids = sorted(ids)
                for i in range(0, len(ids), 500):
                    chunk = ids[i : i + 500]
                    c.execute(delete(t).where(t.c[PK[name]].in_(chunk)))
                    c.execute(insert(t), [self.rows[name][k] for k in chunk])
                counts[name] = len(ids)
            c.execute(delete(S.sim_state).where(S.sim_state.c.key == "state"))
            c.execute(insert(S.sim_state).values(key="state", value=json.dumps(self.state, ensure_ascii=False)))
        if self.new_labels:
            path = self.data_dir / "labels" / "status_updates.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                for lab in self.new_labels:
                    f.write(json.dumps(lab, ensure_ascii=False) + "\n")
        return counts
