"""Score extractors against labelled updates.

Two evaluation sets:
- "simulated": a stratified sample of simulator updates, labelled automatically from the
  project's hidden state at the time of writing (data/labels/status_updates.jsonl);
- "challenge": hand-written, hand-labelled updates in extractor/challenge_set.jsonl with
  phrasing the rules were not written for (negations, implicit severity, solved problems,
  odd date formats).

Metrics: RAG accuracy and macro-F1 with a confusion matrix; risk category precision, recall
and F1 (micro, over sets of categories per update); severity accuracy on correctly found
categories; blocked precision/recall; next-milestone date accuracy (exact day, or within
6 days when the text only gives a week). Plus a reference line: how accurate the RAG
colour the author typed is, which shows why reading the content matters.
"""

import datetime as dt
import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, text

from .schema import Extraction

CHALLENGE_SET = Path(__file__).with_name("challenge_set.jsonl")
RAGS = ["green", "amber", "red"]


def load_simulated(db_url: str, labels_path: Path) -> list[dict]:
    with create_engine(db_url).connect() as c:
        rows = {r[0]: (r[1], r[2]) for r in c.execute(text("select update_id, body, posted_at from status_updates"))}
    items = []
    for line in labels_path.open(encoding="utf-8"):
        lab = json.loads(line)
        if lab["update_id"] in rows:
            body, posted = rows[lab["update_id"]]
            posted = posted if isinstance(posted, dt.datetime) else dt.datetime.fromisoformat(str(posted))
            items.append({"id": lab["update_id"], "text": body, "posted_on": posted.date(), "label": lab})
    return items


def load_challenge(path: Path = CHALLENGE_SET) -> list[dict]:
    items = []
    for i, line in enumerate(path.open(encoding="utf-8"), 1):
        if line.strip():
            case = json.loads(line)
            items.append(
                {
                    "id": case.get("id", i),
                    "text": case["text"],
                    "posted_on": dt.date.fromisoformat(case["posted_on"]),
                    "label": case["label"],
                    "why": case.get("why"),
                }
            )
    return items


def stratified_sample(items: list[dict], n: int, seed: int = 7) -> list[dict]:
    """Sample keeping the mix of RAG colours and risk/no-risk updates."""
    if n >= len(items):
        return items
    rng = random.Random(seed)
    strata = defaultdict(list)
    for it in items:
        strata[(it["label"]["rag"], bool(it["label"]["risks"]), it["label"]["blocked"])].append(it)
    out = []
    for key in sorted(strata, key=str):
        group = strata[key]
        k = max(1, round(n * len(group) / len(items)))
        out += rng.sample(group, min(k, len(group)))
    rng.shuffle(out)
    return out[:n]


def _f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0


def score(items: list[dict], preds: list[Extraction]) -> dict:
    confusion = {t: Counter() for t in RAGS}
    tp = fp = fn = sev_ok = sev_n = 0
    blk = Counter()
    date_ok = date_n = date_missing = 0
    stated_ok = stated_n = 0
    per_cat = defaultdict(Counter)
    for it, pred in zip(items, preds, strict=True):
        lab = it["label"]
        confusion[lab["rag"]][pred.rag or "none"] += 1
        truth = {r["category"]: r["severity"] for r in lab["risks"]}
        got = {r.category: r.severity for r in pred.risks}
        for cat in set(truth) | set(got):
            if cat in truth and cat in got:
                tp += 1
                per_cat[cat]["tp"] += 1
                sev_n += 1
                sev_ok += truth[cat] == got[cat]
            elif cat in got:
                fp += 1
                per_cat[cat]["fp"] += 1
            else:
                fn += 1
                per_cat[cat]["fn"] += 1
        blk[(lab["blocked"], pred.blocked)] += 1
        if lab.get("next_milestone_date"):
            date_n += 1
            if pred.next_milestone_date is None:
                date_missing += 1
            else:
                diff = abs((pred.next_milestone_date - dt.date.fromisoformat(lab["next_milestone_date"])).days)
                date_ok += diff == 0 if lab.get("next_milestone_date_precision") == "day" else diff <= 6
        if pred.stated_rag:
            stated_n += 1
            stated_ok += pred.stated_rag == lab["rag"]
    n = len(items)
    rag_acc = sum(confusion[t][t] for t in RAGS) / n if n else 0
    f1s = []
    for t in RAGS:
        p_den = sum(confusion[x][t] for x in RAGS)
        r_den = sum(confusion[t].values())
        p = confusion[t][t] / p_den if p_den else 0
        r = confusion[t][t] / r_den if r_den else 0
        f1s.append(_f1(p, r))
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    b_tp, b_fp, b_fn = blk[(True, True)], blk[(False, True)], blk[(True, False)]
    return {
        "n": n,
        "rag_accuracy": round(rag_acc, 3),
        "rag_macro_f1": round(sum(f1s) / 3, 3),
        "rag_confusion": {t: dict(confusion[t]) for t in RAGS},
        "risk_precision": round(prec, 3),
        "risk_recall": round(rec, 3),
        "risk_f1": round(_f1(prec, rec), 3),
        "severity_accuracy": round(sev_ok / sev_n, 3) if sev_n else None,
        "blocked_precision": round(b_tp / (b_tp + b_fp), 3) if b_tp + b_fp else None,
        "blocked_recall": round(b_tp / (b_tp + b_fn), 3) if b_tp + b_fn else None,
        "date_accuracy": round(date_ok / date_n, 3) if date_n else None,
        "date_missing_rate": round(date_missing / date_n, 3) if date_n else None,
        "typed_rag_accuracy": round(stated_ok / stated_n, 3) if stated_n else None,
        "typed_rag_coverage": round(stated_n / n, 3) if n else None,
        "per_category": {
            c: {
                "precision": round(v["tp"] / (v["tp"] + v["fp"]), 3) if v["tp"] + v["fp"] else None,
                "recall": round(v["tp"] / (v["tp"] + v["fn"]), 3) if v["tp"] + v["fn"] else None,
            }
            for c, v in sorted(per_cat.items())
        },  # fmt: skip
    }


def run(
    items: list[dict], extract: Callable[[str, dt.date], Extraction], progress: Callable[[int, int], None] | None = None
) -> list[Extraction]:
    preds = []
    for i, it in enumerate(items, 1):
        preds.append(extract(it["text"], it["posted_on"]))
        if progress:
            progress(i, len(items))
    return preds


def errors(items: list[dict], preds: list[Extraction], limit: int = 8) -> list[dict]:
    """Updates where the RAG or the risk set was wrong, for the report."""
    out = []
    for it, p in zip(items, preds, strict=True):
        truth = sorted(r["category"] for r in it["label"]["risks"])
        got = sorted(r.category for r in p.risks)
        if p.rag != it["label"]["rag"] or truth != got:
            out.append(
                {
                    "id": it["id"],
                    "text": it["text"],
                    "expected_rag": it["label"]["rag"],
                    "got_rag": p.rag,
                    "expected_risks": truth,
                    "got_risks": got,
                    "why": it.get("why"),
                }
            )
        if len(out) >= limit:
            break
    return out


def markdown_report(results: dict[str, dict[str, dict]], meta: dict) -> str:
    """results[set_name][extractor_name] = metrics"""
    lines = ["# Status update extraction: evaluation", "", f"Generated {meta['generated']}. " + meta.get("note", ""), ""]
    rows = [
        ("RAG accuracy", "rag_accuracy"),
        ("RAG macro-F1", "rag_macro_f1"),
        ("Risk precision", "risk_precision"),
        ("Risk recall", "risk_recall"),
        ("Risk F1", "risk_f1"),
        ("Severity accuracy (found risks)", "severity_accuracy"),
        ("Blocked precision", "blocked_precision"),
        ("Blocked recall", "blocked_recall"),
        ("Next-milestone date accuracy", "date_accuracy"),
        ("Date missing rate", "date_missing_rate"),
        ("Typed RAG colour accuracy (reference)", "typed_rag_accuracy"),
    ]
    for set_name, by_extractor in results.items():
        names = list(by_extractor)
        n = next(iter(by_extractor.values()))["n"]
        lines += [f"## {set_name} set (n = {n})", "", "| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for label, key in rows:
            vals = [by_extractor[x].get(key) for x in names]
            lines.append(f"| {label} | " + " | ".join("–" if v is None else f"{v:.2f}" for v in vals) + " |")
        lines.append("")
        for x in names:
            cm = by_extractor[x]["rag_confusion"]
            lines += [
                f"RAG confusion, {x} (rows = truth, columns = extracted):",
                "",
                "| | green | amber | red | none |",
                "|---|---|---|---|---|",
            ]
            lines += [f"| {t} | " + " | ".join(str(cm[t].get(c, 0)) for c in ["green", "amber", "red", "none"]) + " |" for t in RAGS]
            lines.append("")
    return "\n".join(lines)
