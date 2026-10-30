"""Risk categories: a short definition each (used in the LLM prompt) and generic keywords
(used by the rule-based baseline). Replace the dict or pass a JSON file to use your own."""

import json
from pathlib import Path

DEFAULT_CATEGORIES: dict[str, dict] = {
    "parts_shortage": {
        "definition": "spare parts or components unavailable, back-ordered or slow to arrive",
        "keywords": ["parts", "back-order", "backorder", "out of stock", "vor", "spare", "component"],
    },
    "resource_shortage": {
        "definition": "not enough people, key person absent or left, no dedicated resource",
        "keywords": ["short of people", "resource", "staff", "on leave", "headcount", "left", "capacity"],
    },
    "dealer_readiness": {
        "definition": "dealers, workshops or technicians not ready (skills, tools, certification, process)",
        "keywords": ["dealer", "workshop", "technician", "repairer", "certified", "diagnostic tool"],
    },
    "it_dependency": {
        "definition": "waiting for an IT system, release, interface or access",
        "keywords": [" it ", "api", "portal", "dms", "interface", "system", "release", "firewall", "access"],
    },
    "budget": {
        "definition": "costs above plan, quotes over budget, budget not confirmed",
        "keywords": ["budget", "cost", "quote", "price", "spend", "overrun"],
    },
    "regulatory": {
        "definition": "legal, authority or certification approval missing or open",
        "keywords": ["legal", "authority", "approval", "regulat", "homologation", "type approval", "terms", "compliance"],
    },
    "customs_logistics": {
        "definition": "shipments, customs, import licences or freight delayed",
        "keywords": ["customs", "import", "freight", "shipment", "shipping", "logistic", "sea "],
    },
    "data_quality": {
        "definition": "source data incomplete, wrong or inconsistent between systems",
        "keywords": ["data", "vin", "kpi", "mismatch", "don't match", "inconsistent", "errors"],
    },
    "stakeholder_alignment": {
        "definition": "disagreement or pending decision between teams, HQ, management or partners",
        "keywords": ["agree", "decision", "aligned", "alignment", "management", "importer", "hq"],
    },
    "supplier_delay": {
        "definition": "a supplier or vendor late with delivery of goods or equipment",
        "keywords": ["supplier", "vendor", "delivery date", "late with delivery", "equipment"],
    },
}


def load_categories(path: str | Path | None = None) -> dict[str, dict]:
    """Default categories, or a JSON file {"name": {"definition": "...", "keywords": [...]}}."""
    if not path:
        return DEFAULT_CATEGORIES
    return json.loads(Path(path).read_text(encoding="utf-8"))
