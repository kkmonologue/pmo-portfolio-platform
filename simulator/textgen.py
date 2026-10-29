"""Free-text bi-weekly status updates, generated together with ground truth.

Each update is written from the project's hidden state, so the simulator
knows exactly what a perfect reader should extract from it: the true RAG
status, which risks are mentioned and how severe they are, whether the
project is blocked, and when the next milestone is due. Those labels go to a
separate file and are used to score the LLM extractor.

Updates are in English, written by people from many countries: bullets,
numbered lists, prose and one-liners, abbreviations, typos, some
non-native phrasing, and dates in every format.
"""

from __future__ import annotations

import datetime as dt
import random

RISK_TEXT = {
    "parts_shortage": [
        "parts for the {model} are on back-order",
        "VOR parts are taking 3+ weeks to arrive",
        "battery modules out of stock at the regional warehouse",
    ],
    "resource_shortage": [
        "we are short of people since {who} left",
        "no dedicated resource from {team} yet",
        "key engineer on leave until next month",
    ],
    "dealer_readiness": [
        "only {n} of {m} dealers have HV-certified technicians",
        "dealers in {country} not ready for the new process",
        "several workshops still missing the diagnostic tool",
    ],
    "it_dependency": [
        "depends on the IT release of the service portal",
        "API access from IT still not granted",
        "DMS interface with the dealers not ready",
    ],
    "budget": ["costs are running above plan", "quote came in higher than the approved budget", "budget for next year not confirmed"],
    "regulatory": [
        "local authority approval for the workshop still open",
        "need legal sign-off on the new terms",
        "type approval documents for {country} incomplete",
    ],
    "customs_logistics": [
        "shipment stuck in customs in {country}",
        "import licence for spare parts delayed",
        "sea freight slot moved by two weeks",
    ],
    "data_quality": ["warranty data from dealers is incomplete", "VIN mapping has many errors", "KPI numbers don't match between systems"],
    "stakeholder_alignment": [
        "{team} and HQ don't agree on the approach",
        "decision from management still pending",
        "local importer not aligned with the plan",
    ],
    "supplier_delay": [
        "supplier {sup} is late with delivery",
        "{sup} pushed their delivery date again",
        "still waiting {sup} for the equipment",
    ],
}
SEVERITY_WRAP = {
    "low": ["minor: {r}", "small issue, {r}", "{r} (low impact)", "FYI {r}"],
    "medium": ["{r}, could impact the timeline", "risk: {r}", "{r} - watching closely", "{r}, may delay next step"],
    "high": [
        "CRITICAL: {r}, we will miss the date if not solved",
        "{r}, need escalation",
        "major risk - {r}, milestone at risk",
        "{r} - pls escalate ASAP",
    ],
}
PROGRESS = [
    "workshop with {team} done",
    "draft concept shared with the importer",
    "{n} of {m} dealers onboarded",
    "pilot feedback collected from {country}",
    "test cases executed",
    "contract negotiation with the partner ongoing",
    "training material finalised",
    "weekly call with {country} started",
    "data for Q{q} collected and checked",
    "meeting with HQ to align on scope",
    "kick-off held with local team",
    "first draft of the process sent for review",
]
NOTHING = ["no major risks", "nothing to flag", "all on track", "no issues for now"]
BLOCKER = ["BLOCKED until {x}", "cannot proceed until {x}", "on hold waiting for {x}", "stuck - waiting {x}"]
BLOCK_ON = ["budget approval", "the IT release", "legal sign-off", "the supplier contract", "HQ decision"]
SUPPLIERS = ["Quarnell Tools", "Brisvane Logistics", "Ostrik Parts", "Telmora Systems"]  # fictional
MODELS = ["compact hatchback", "mid-size SUV", "saloon", "12m city bus", "L2 van"]  # generic, no model names
RAG_WORDS = {
    "green": ["Green", "G", "on track", "GREEN"],
    "amber": ["Amber", "A", "Yellow", "at risk"],
    "red": ["Red", "R", "off track", "RED"],
}
TYPOS = {"the": "teh", "with": "wiht", "waiting": "wating", "delivery": "delivary", "budget": "budjet", "approval": "aproval"}
ABBREV = {" with ": " w/ ", "to be confirmed": "TBC", " please ": " pls ", " and ": " & "}


def _ordinal(n: int) -> str:
    return "th" if 10 < n % 100 < 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def fmt_date(rng: random.Random, d: dt.date) -> tuple[str, str]:
    """Return (text, precision). People write dates every possible way."""
    x = rng.random()
    if x < 0.18:
        return d.isoformat(), "day"
    if x < 0.36:
        return d.strftime("%d/%m/%Y"), "day"
    if x < 0.46:
        return d.strftime("%d.%m.%Y"), "day"
    if x < 0.58:
        return f"{d.day} {d:%b}", "day"
    if x < 0.7:
        return f"{d:%b} {d.day}{_ordinal(d.day)}", "day"
    if x < 0.85:
        monday = d - dt.timedelta(days=d.weekday())
        return f"w/c {monday.day} {monday:%b}", "week"
    return f"CW{d.isocalendar().week}", "week"


def true_rag(risks: list[dict], overdue_days: int, blocked: bool) -> str:
    if blocked or overdue_days > 14 or any(r["severity"] == "high" for r in risks):
        return "red"
    if overdue_days > 0 or any(r["severity"] == "medium" for r in risks):
        return "amber"
    return "green"


def write_update(rng: random.Random, ctx: dict) -> tuple[str, dict]:
    """ctx: team, country, risks[{category,severity}], blocked, overdue_days,
    next_milestone (name, date) or None, colleague (name string), as_of (date)."""
    fill = {
        "team": ctx["team"],
        "country": ctx["country"],
        "who": ctx["colleague"],
        "sup": rng.choice(SUPPLIERS),
        "model": rng.choice(MODELS),
        "n": rng.randint(2, 9),
        "m": rng.randint(10, 30),
        "q": rng.randint(1, 4),
    }
    progress = list(dict.fromkeys(rng.choice(PROGRESS).format(**fill) for _ in range(rng.randint(1, 3))))
    risk_lines = [
        rng.choice(SEVERITY_WRAP[r["severity"]]).format(r=rng.choice(RISK_TEXT[r["category"]]).format(**fill)) for r in ctx["risks"]
    ]
    if not risk_lines:
        risk_lines = [rng.choice(NOTHING)]
    blocker_line = rng.choice(BLOCKER).format(x=rng.choice(BLOCK_ON)) if ctx["blocked"] else None

    next_text = precision = next_iso = None
    if ctx["next_milestone"]:
        name, due = ctx["next_milestone"]
        dtext, precision = fmt_date(rng, due)
        next_iso = due.isoformat()
        next_text = rng.choice(
            [f"Next: {name} by {dtext}", f"next step {name} ETA {dtext}", f"{name} planned {dtext}", f"{name} - target {dtext}"]
        )

    rag = true_rag(ctx["risks"], ctx["overdue_days"], ctx["blocked"])
    order = ["green", "amber", "red"]
    stated = rag if rng.random() > 0.33 else order[max(0, order.index(rag) - 1)]  # optimistic a third of the time
    extras = [x for x in [blocker_line, next_text] if x]
    style = rng.choice(["bullets", "prose", "terse", "dated"])
    if style == "bullets":
        h = rng.choice(
            [
                ("Progress", "Risks", "Next steps"),
                ("Done", "Issues", "Next"),
                ("PROGRESS", "RISKS/ISSUES", "NEXT"),
                ("Achievements", "Concerns", "Plan"),
            ]
        )
        b = rng.choice(["- ", "* ", "• ", ""])
        parts = [f"{h[0]}:"] + [b + p for p in progress] + [f"{h[1]}:"] + [b + r for r in risk_lines]
        if blocker_line:
            parts.append(b + blocker_line)
        if next_text:
            parts += [f"{h[2]}:", b + next_text]
        body = "\n".join(parts)
    elif style == "dated":
        lines = [*progress, *risk_lines, *extras]
        body = f"{ctx['as_of']:%d/%m}\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(lines, 1))
    elif style == "prose":
        body = ". ".join([*progress, *risk_lines, *extras]) + "."
        body = body[0].upper() + body[1:]
    else:
        body = "; ".join([*progress[:1], *risk_lines, *extras])
    if rng.random() < 0.45:
        word = rng.choice(RAG_WORDS[stated])
        body = rng.choice([f"Status: {word}\n", f"[{word}] ", f"RAG {word} - ", f"Overall: {word}\n"]) + body
    if rng.random() < 0.2:
        for a, b in ABBREV.items():
            body = body.replace(a, b)
    if rng.random() < 0.15:
        for a, b in TYPOS.items():
            if rng.random() < 0.5:
                body = body.replace(f" {a} ", f" {b} ", 1)
    if rng.random() < 0.08:
        body = body.lower()

    label = {
        "rag": rag,
        "stated_rag": stated,
        "risks": ctx["risks"],
        "blocked": ctx["blocked"],
        "next_milestone_date": next_iso,
        "next_milestone_date_precision": precision,
    }
    return body, label
