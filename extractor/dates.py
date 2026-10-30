"""Find the next-milestone date in an update and resolve it against the posting date.

People write 2026-11-14, 14/11/2026, 14.11.2026, 14 Nov, Nov 14th, w/c 10 Nov or CW46.
Dates without a year get the year that puts them closest to the posting date, within a
window from 45 days before to a year after it: a next step written as "Aug 5th" in October
means next August, while a date a few weeks back is an overdue milestone. Week-only mentions return the Monday
of that week with precision "week".
"""

import datetime as dt
import re

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("dmy_slash", re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")),
    ("dmy_dot", re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")),
    ("wc", re.compile(r"\bw/c\s+(\d{1,2})\s+" + MON, re.I)),
    ("cw", re.compile(r"\b(?:cw|kw|wk)\s?(\d{1,2})\b", re.I)),
    ("day_mon", re.compile(r"(?<!w/c )\b(\d{1,2})\s+" + MON + r"(?!\w)", re.I)),
    ("mon_day", re.compile(r"\b" + MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)),
]
NEXT_CUES = re.compile(r"\b(next|eta|planned|target|by|due|deadline)\b", re.I)


def _with_year(month: int, day: int, ref: dt.date) -> dt.date | None:
    candidates = []
    for year in (ref.year - 1, ref.year, ref.year + 1):
        try:
            candidates.append(dt.date(year, month, day))
        except ValueError:
            continue
    in_window = [c for c in candidates if -45 <= (c - ref).days <= 365]
    pool = in_window or candidates
    return min(pool, key=lambda c: abs((c - ref).days)) if pool else None


def _iso_week_monday(week: int, ref: dt.date) -> dt.date | None:
    candidates = []
    for year in (ref.year - 1, ref.year, ref.year + 1):
        try:
            candidates.append(dt.date.fromisocalendar(year, week, 1))
        except ValueError:
            continue
    in_window = [c for c in candidates if -45 <= (c - ref).days <= 365]
    pool = in_window or candidates
    return min(pool, key=lambda c: abs((c - ref).days)) if pool else None


def find_dates(text: str, ref: dt.date) -> list[tuple[int, dt.date, str]]:
    """All date mentions as (position, date, precision)."""
    found, taken = [], []
    for kind, pat in PATTERNS:
        for m in pat.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            g = m.groups()
            try:
                if kind == "iso":
                    d, prec = dt.date(int(g[0]), int(g[1]), int(g[2])), "day"
                elif kind in ("dmy_slash", "dmy_dot"):
                    d, prec = dt.date(int(g[2]), int(g[1]), int(g[0])), "day"
                elif kind == "wc":
                    d, prec = _with_year(MONTHS[g[1][:3].lower()], int(g[0]), ref), "week"
                elif kind == "cw":
                    d, prec = _iso_week_monday(int(g[0]), ref), "week"
                elif kind == "day_mon":
                    d, prec = _with_year(MONTHS[g[1][:3].lower()], int(g[0]), ref), "day"
                else:
                    d, prec = _with_year(MONTHS[g[0][:3].lower()], int(g[1]), ref), "day"
            except ValueError:
                continue
            if d:
                found.append((m.start(), d, prec))
                taken.append((m.start(), m.end()))
    return sorted(found)


def next_milestone_date(text: str, ref: dt.date) -> tuple[dt.date, str] | None:
    """The date in the next-step clause: the first mention preceded by a cue word
    (next, ETA, planned, target, by, due), else the last mention in the text."""
    mentions = find_dates(text, ref)
    if not mentions:
        return None
    for pos, d, prec in mentions:
        window = text[max(0, pos - 60) : pos]
        if NEXT_CUES.search(window):
            return d, prec
    _, d, prec = mentions[-1]
    return d, prec
