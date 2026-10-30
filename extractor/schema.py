"""What the extractor returns for one status update."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Rag = Literal["green", "amber", "red"]
Severity = Literal["low", "medium", "high"]
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


class Risk(BaseModel):
    category: str
    severity: Severity = "medium"


class Extraction(BaseModel):
    rag: Rag | None = Field(None, description="Actual status judged from the content, not the colour the author typed")
    stated_rag: Rag | None = Field(None, description="Colour the author wrote, if any")
    risks: list[Risk] = Field(default_factory=list)
    blocked: bool = False
    next_milestone_date: date | None = None
    next_milestone_date_precision: Literal["day", "week"] | None = None

    def normalised(self, categories: list[str]) -> "Extraction":
        """Unknown categories become 'other'; one entry per category, keeping the highest severity."""
        best: dict[str, Risk] = {}
        for r in self.risks:
            cat = r.category if r.category in categories else "other"
            if cat not in best or SEVERITY_ORDER[r.severity] > SEVERITY_ORDER[best[cat].severity]:
                best[cat] = Risk(category=cat, severity=r.severity)
        return self.model_copy(update={"risks": sorted(best.values(), key=lambda r: r.category)})
