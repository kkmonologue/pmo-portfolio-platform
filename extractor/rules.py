"""Rule-based baseline: keywords and regular expressions, no model, no API.

Deliberately generic: it uses the kind of keyword lists a PMO analyst would write
(severity words, topic words, a date parser), not the simulator's sentence templates.
It is the bar the LLM has to beat, and the fallback when no API is configured.

How it decides:
- risks: only in sentences that sound like a risk (a severity word such as "critical",
  "risk:", "could impact", "minor") or that sit under a Risks / Issues heading; the
  category is the one with most keyword hits in that sentence;
- severity: from the severity words in the same sentence, medium if none;
- blocked: "blocked", "cannot proceed", "on hold waiting", "stuck";
- RAG: the PMO definition - red if blocked, a high-severity risk or the next milestone
  more than 14 days overdue; amber if a medium risk or overdue; else green.
"""

import datetime as dt
import re

from .categories import DEFAULT_CATEGORIES
from .dates import next_milestone_date
from .schema import Extraction, Risk

HIGH = re.compile(r"critical|escalat|major risk|will miss|showstopper|urgent|asap", re.I)
MEDIUM = re.compile(r"\brisk\b|could impact|may delay|watching|concern|might|at risk", re.I)
LOW = re.compile(r"\bminor\b|small issue|low impact|\bfyi\b", re.I)
NOTHING = re.compile(r"no (major )?risks?|nothing to flag|all on track|no issues", re.I)
# "stuck in customs" describes a shipment, not the project; "no longer blocked" is not blocked
BLOCKED = re.compile(r"(?<!no longer )(?<!not )\bblocked\b|cannot proceed|can't proceed|on hold waiting|\bstuck\b(?!\s+in\b)", re.I)
RISK_HEADER = re.compile(r"^\s*(risks?|issues|risks/issues|concerns)\s*:?\s*$", re.I)
OTHER_HEADER = re.compile(r"^\s*(progress|done|achievements|next( steps)?|plan)\s*:?\s*$", re.I)
STATED = re.compile(
    r"(?:status\s*:|overall\s*:|\brag\b|^\s*\[)\s*\[?\s*(green|amber|yellow|red|on track|at risk|off track|g|a|r)\b",
    re.I | re.M,
)
STATED_MAP = {"green": "green", "g": "green", "on track": "green", "amber": "amber", "yellow": "amber", "a": "amber",
              "at risk": "amber", "red": "red", "r": "red", "off track": "red"}  # fmt: skip
SPLIT = re.compile(r"\n|(?<=[.;])\s+|^\s*\d+\.\s+", re.M)


def _segments(text: str) -> list[tuple[str, bool]]:
    """(segment, under_risk_heading) pairs."""
    out, in_risks = [], False
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        if not line:
            continue
        if RISK_HEADER.match(line):
            in_risks = True
            continue
        if OTHER_HEADER.match(line):
            in_risks = False
            continue
        for seg in SPLIT.split(line):
            seg = re.sub(r"^\d+\.\s*", "", seg.strip())
            if seg:
                out.append((seg, in_risks))
    return out


def _category(segment: str, categories: dict[str, dict]) -> str | None:
    s = f" {segment.lower()} "
    scores = {name: sum(s.count(k) for k in spec.get("keywords", [])) for name, spec in categories.items()}
    best = max(scores, key=scores.get) if scores else None
    return best if best and scores[best] > 0 else None


def extract(text: str, posted_on: dt.date, categories: dict[str, dict] | None = None) -> Extraction:
    categories = categories or DEFAULT_CATEGORIES
    risks: dict[str, Risk] = {}
    for seg, under_heading in _segments(text):
        if NOTHING.search(seg) and not (HIGH.search(seg) or MEDIUM.search(seg)):
            continue
        sev = "high" if HIGH.search(seg) else "medium" if MEDIUM.search(seg) else "low" if LOW.search(seg) else None
        if sev is None and not under_heading:
            continue
        cat = _category(seg, categories)
        if not cat:
            continue
        sev = sev or "medium"
        order = {"low": 0, "medium": 1, "high": 2}
        if cat not in risks or order[sev] > order[risks[cat].severity]:
            risks[cat] = Risk(category=cat, severity=sev)

    blocked = bool(BLOCKED.search(text))
    nxt = next_milestone_date(text, posted_on)
    overdue = (posted_on - nxt[0]).days if nxt else 0
    if blocked or overdue > 14 or any(r.severity == "high" for r in risks.values()):
        rag = "red"
    elif overdue > 0 or any(r.severity == "medium" for r in risks.values()):
        rag = "amber"
    else:
        rag = "green"
    m = STATED.search(text)
    return Extraction(
        rag=rag,
        stated_rag=STATED_MAP.get(m.group(1).lower()) if m else None,
        risks=sorted(risks.values(), key=lambda r: r.category),
        blocked=blocked,
        next_milestone_date=nxt[0] if nxt else None,
        next_milestone_date_precision=nxt[1] if nxt else None,
    )
