import datetime as dt
import json
import re

import pytest
from sqlalchemy import create_engine, text

from simulator import schema as S
from simulator.engine import Simulation, meeting_date

START, MID, END = dt.date(2024, 7, 1), dt.date(2025, 4, 1), dt.date(2025, 9, 30)


def _run(eng, data_dir, until, seed=7):
    sim = Simulation(eng, seed, data_dir)
    sim.bootstrap(START)
    sim.run_until(until, None)
    sim.save()
    return sim


def _dump(eng):
    with eng.connect() as c:
        return {t.name: c.execute(text(f"select * from {t.name} order by 1")).fetchall() for t in S.SOURCE_TABLES}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp("world")
    eng = create_engine(f"sqlite:///{d / 'w.db'}")
    _run(eng, d, END)
    return eng, d


def q(eng, sql):
    with eng.connect() as c:
        return c.execute(text(sql)).fetchall()


def test_same_seed_same_data(tmp_path, world):
    eng = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    _run(eng, tmp_path, END)
    assert _dump(eng) == _dump(world[0])


def test_chunked_run_equals_one_shot(tmp_path, world):
    """Incremental runs must continue exactly where the last one stopped."""
    eng = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    _run(eng, tmp_path, MID)
    _run(eng, tmp_path, END)
    assert _dump(eng) == _dump(world[0])


def test_labels_match_updates(world):
    eng, d = world
    labels = [json.loads(line) for line in (d / "labels" / "status_updates.jsonl").open()]
    assert sorted(lab["update_id"] for lab in labels) == [r[0] for r in q(eng, "select update_id from status_updates order by 1")]
    for lab in labels:
        assert lab["rag"] in {"green", "amber", "red"}
        if lab["blocked"] or any(r["severity"] == "high" for r in lab["risks"]):
            assert lab["rag"] == "red"


def test_codes(world):
    eng, _ = world
    codes = [r[0] for r in q(eng, "select code from projects")]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"[A-Z]{3}-\d\d-(\d{3}|A\d\d)", c) for c in codes)
    strategic = q(eng, "select code from projects where strategic_level is not null")
    assert all("-A" in c for (c,) in strategic)
    assert all(re.fullmatch(r"[A-Z]{3}-\d\d-F\d\d", c) for (c,) in q(eng, "select code from follow_ups"))
    # legacy codes only for projects created before go-live
    assert q(eng, "select count(*) from projects where legacy_code is not null and created_at >= '2025-03-01'")[0][0] == 0


def test_closed_projects_went_through_close_review(world):
    eng, _ = world
    closed = [r[0] for r in q(eng, "select project_id from projects where status = 'closed'")]
    assert closed
    for pid in closed:
        assert q(eng, f"select count(*) from requests where project_id={pid} and kind='close' and status='pre_approved'")[0][0] >= 1
        assert q(eng, f"select count(*) from project_events where project_id={pid} and event_type='closed_meeting'")[0][0] == 1


def test_strategic_projects_had_unanimous_vote(world):
    eng, _ = world
    rows = q(
        eng,
        "select p.project_id, r.request_id from projects p join requests r on r.project_id = p.project_id and r.kind='new' where p.strategic_level is not null",
    )
    for _, rid in rows:
        rev = q(eng, f"select review_id from board_reviews where request_id={rid} and status='approved'")
        assert len(rev) == 1
        assert q(eng, f"select count(*) from board_votes where review_id={rev[0][0]} and vote='no'")[0][0] == 0


def test_accepted_milestones_have_accepted_evidence(world):
    eng, _ = world
    missing = q(
        eng,
        """select count(*) from milestones m where m.status='accepted' and not exists
                        (select 1 from milestone_submissions s where s.milestone_id=m.milestone_id and s.review_status='accepted')""",
    )
    assert missing[0][0] == 0


def test_updates_are_for_the_teams_meeting_track(world):
    eng, _ = world
    bad = q(
        eng,
        """select count(*) from status_updates u join projects p using(project_id) join teams t using(team_id)
                    join meetings m using(meeting_id) where m.track <> t.meeting_track""",
    )
    assert bad[0][0] == 0


def test_meetings_alternate():
    d = dt.date(2025, 1, 1)
    front, middle = meeting_date("front", d), meeting_date("middle", d)
    assert front.weekday() == middle.weekday() == 3
    assert abs((front - middle).days) == 7
