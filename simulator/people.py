"""Staff generation and the many ways one person's name gets written."""

from __future__ import annotations

import random
import unicodedata

from faker import Faker

from .company import ARAB_FAMILY, ARAB_GIVEN, COMPANY, LOCALES_BY_REGION

_FAKERS: dict[str, Faker] = {}


def _faker(locale: str) -> Faker:
    if locale not in _FAKERS:
        _FAKERS[locale] = Faker(locale)
    return _FAKERS[locale]


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace(" ", "").replace("'", "")


def make_person(rng: random.Random, person_id: int, seed: int, region: str) -> dict:
    locales = LOCALES_BY_REGION[region]
    locale = rng.choices(list(locales), weights=list(locales.values()))[0]
    if locale == "arab":
        first, last = rng.choice(ARAB_GIVEN), rng.choice(ARAB_FAMILY)
    else:
        fk = _faker(locale)
        fk.seed_instance(seed * 100_003 + person_id)
        first, last = fk.first_name(), fk.last_name()
    # some people go by a short name at work
    nickname = first.split()[0] if " " in first and rng.random() < 0.5 else None
    return {
        "person_id": person_id,
        "display_name": f"{first} {last}",
        "first_name": first,
        "last_name": last,
        "nickname": nickname,
        "email": f"{_ascii(first)}.{_ascii(last)}@{COMPANY['email_domain']}",
        "locale": locale,
    }


def name_variant(rng: random.Random, p: dict) -> str:
    """How a human might type this person's name in a free-text field."""
    first, last = p["first_name"], p["last_name"]
    options = [p["display_name"]] * 4 + [
        f"{first[0]}. {last}",
        f"{last}, {first}",
        first,
        p["email"].split("@")[0],
        f"{first} {last}".upper(),
        f"{last.upper()} {first}",
    ]
    if p.get("nickname"):
        options += [f"{p['nickname']} {last}", p["nickname"]]
    return rng.choice(options)
