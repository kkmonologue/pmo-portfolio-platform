import datetime as dt
import json

import duckdb
import httpx
import pytest

from extractor import rules
from extractor.dates import next_milestone_date
from extractor.evaluate import load_challenge, run, score
from extractor.llm import LLMExtractor
from extractor.schema import Extraction, Risk
from extractor.warehouse import extract_new

REF = dt.date(2026, 10, 15)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Next: Go-live by 2026-11-20", (dt.date(2026, 11, 20), "day")),
        ("target 05/11/2026", (dt.date(2026, 11, 5), "day")),
        ("planned 30.06.2027", (dt.date(2027, 6, 30), "day")),
        ("next step Pilot ETA Nov 3rd", (dt.date(2026, 11, 3), "day")),
        ("Training planned 14 Jan", (dt.date(2027, 1, 14), "day")),  # no year: next January
        ("Pilot evaluated planned w/c 9 Nov", (dt.date(2026, 11, 9), "week")),
        ("Kick-off CW44", (dt.date(2026, 10, 26), "week")),
        ("pilot start was 1 oct", (dt.date(2026, 10, 1), "day")),  # recent past = overdue, not next year
        ("ETA Aug 5th", (dt.date(2027, 8, 5), "day")),  # far past would be odd for a next step
        ("nothing planned yet", None),
    ],
)
def test_dates(text, expected):
    assert next_milestone_date(text, REF) == expected


def test_rules_basic_signals():
    e = rules.extract(
        "Status: Green\nRisks:\n- CRITICAL: shipment stuck in customs in Kenya, need escalation\nNext: Go-live by 2026-11-20", REF
    )
    assert e.stated_rag == "green" and e.rag == "red"
    assert e.risks == [Risk(category="customs_logistics", severity="high")]
    assert not e.blocked  # "stuck in customs" is a shipment, not the project
    assert rules.extract("BLOCKED until legal sign-off", REF).blocked
    assert rules.extract("all on track; next step Training ETA 2026-09-25", REF).rag == "red"  # 20 days overdue


def test_challenge_labels_follow_the_rag_definition():
    """The hand-written answer key must itself obey the PMO's RAG rule."""
    for case in load_challenge():
        lab, posted = case["label"], case["posted_on"]
        overdue = (posted - dt.date.fromisoformat(lab["next_milestone_date"])).days if lab["next_milestone_date"] else 0
        sev = {r["severity"] for r in lab["risks"]}
        expected = "red" if lab["blocked"] or "high" in sev or overdue > 14 else "amber" if "medium" in sev or overdue > 0 else "green"
        assert lab["rag"] == expected, case["id"]


def test_score_math():
    items = [
        {
            "label": {
                "rag": "red",
                "risks": [{"category": "budget", "severity": "high"}],
                "blocked": True,
                "next_milestone_date": "2026-11-02",
                "next_milestone_date_precision": "week",
            }
        },
        {"label": {"rag": "green", "risks": [], "blocked": False, "next_milestone_date": None}},
    ]
    preds = [
        Extraction(
            rag="red",
            risks=[Risk(category="budget", severity="medium"), Risk(category="it_dependency")],
            blocked=True,
            next_milestone_date=dt.date(2026, 11, 6),
        ),
        Extraction(rag="amber", stated_rag="green"),
    ]
    m = score(items, preds)
    assert m["rag_accuracy"] == 0.5
    assert (m["risk_precision"], m["risk_recall"], m["severity_accuracy"]) == (0.5, 1.0, 0.0)
    assert m["blocked_recall"] == 1.0 and m["date_accuracy"] == 1.0  # 4 days off, week precision
    assert m["typed_rag_accuracy"] == 1.0


# ---------------------------------------------------------------- LLM client, against a fake API


def _reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


GOOD = json.dumps({"rag": "amber", "stated_rag": None, "risks": [{"category": "budget", "severity": "medium"}, {"category": "made_up", "severity": "low"}],
                   "blocked": False, "next_milestone_date": "2026-11-02", "next_milestone_date_precision": "day"})  # fmt: skip


def _client(tmp_path, responses, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        status, body = responses.pop(0)
        return httpx.Response(status, json=body, headers={"retry-after": "0"} if status == 429 else {})

    return LLMExtractor(
        provider="groq", api_key="test-key", rpm=100000, cache_path=tmp_path / "cache.sqlite", transport=httpx.MockTransport(handler)
    )


def test_llm_parses_validates_and_caches(tmp_path):
    seen = []
    llm = _client(tmp_path, [(200, _reply("```json\n" + GOOD + "\n```"))], seen)
    e = llm.extract("quote above budget", REF)
    assert e.rag == "amber" and e.next_milestone_date == dt.date(2026, 11, 2)
    assert {r.category for r in e.risks} == {"budget", "other"}  # unknown category mapped to "other"
    assert seen[0]["temperature"] == 0 and seen[0]["response_format"] == {"type": "json_object"}
    assert "Posting date: 2026-10-15" in seen[0]["messages"][1]["content"]
    assert llm.extract("quote above budget", REF) == e  # second call served from cache
    assert len(seen) == 1 and llm.stats["cache_hits"] == 1


def test_llm_retries_rate_limits_and_repairs_bad_json(tmp_path):
    seen = []
    llm = _client(tmp_path, [(429, {"error": "slow down"}), (200, _reply("sorry, here it is: not json")), (200, _reply(GOOD))], seen)
    e = llm.extract("some update", REF)
    assert e.rag == "amber"
    assert llm.stats["retries"] == 1 and llm.stats["repairs"] == 1
    assert "not valid" in seen[-1]["messages"][-1]["content"]


def test_llm_needs_a_key(monkeypatch):
    for var in ("GEMINI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        LLMExtractor(provider="gemini", cache_path=None)


# ---------------------------------------------------------------- warehouse integration


def test_warehouse_extraction_is_incremental(tmp_path):
    wh = tmp_path / "wh.duckdb"
    with duckdb.connect(str(wh)) as con:
        con.execute("create schema raw; create table raw.status_updates (update_id bigint, body varchar, posted_at timestamp)")
        con.execute(
            "insert into raw.status_updates values (1, 'BLOCKED until budget approval', '2026-10-15 10:00'), (2, 'all on track', '2026-10-15 11:00')"
        )
    assert extract_new(wh, "rules", rules.extract, max_new=1) == {"extracted": 1, "remaining": 1}
    assert extract_new(wh, "rules", rules.extract) == {"extracted": 1, "remaining": 0}
    assert extract_new(wh, "rules", rules.extract) == {"extracted": 0, "remaining": 0}
    with duckdb.connect(str(wh), read_only=True) as con:
        assert con.execute("select update_id, rag, blocked from extract.status_update_signals order by 1").fetchall() == [
            (1, "red", True),
            (2, "green", False),
        ]


def test_rules_floor_on_challenge_set():
    """A tripwire, not a target: the baseline should stay roughly where it is."""
    items = load_challenge()
    m = score(items, run(items, rules.extract))
    assert m["date_accuracy"] >= 0.8
    assert m["rag_accuracy"] >= 0.5


def test_llm_falls_back_when_json_mode_is_not_supported(tmp_path):
    seen = []
    llm = _client(tmp_path, [(400, {"error": {"message": "Invalid value for response_format"}}), (200, _reply(GOOD))], seen)
    assert llm.extract("some update", REF).rag == "amber"
    assert "response_format" in seen[0] and "response_format" not in seen[1]


def test_llm_explains_bad_key_and_unknown_model(tmp_path):
    with pytest.raises(RuntimeError, match="API key"):
        _client(tmp_path, [(401, {"error": "bad key"})], []).extract("x", REF)
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        _client(tmp_path / "b", [(404, {"error": "no such model"})], []).extract("x", REF)
