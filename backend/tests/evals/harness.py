from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class QACase:
    question: str
    answer: str
    required_terms: list[str]
    evidence_required: bool


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def score_answer_quality(case: QACase) -> float:
    answer_lower = case.answer.lower()
    matched_terms = sum(
        1 for term in case.required_terms if term.lower() in answer_lower
    )
    if not case.required_terms:
        term_score = 1.0
    else:
        term_score = matched_terms / len(case.required_terms)

    if case.evidence_required:
        evidence_markers = ["evidence", "based on", "from tool output", "source"]
        evidence_score = (
            1.0 if any(marker in answer_lower for marker in evidence_markers) else 0.0
        )
    else:
        evidence_score = 1.0

    return round((0.7 * term_score) + (0.3 * evidence_score), 3)


def is_grounded_when_missing_evidence(answer: str) -> bool:
    lowered = answer.lower()
    return (
        "insufficient" in lowered
        or "missing" in lowered
        or "not enough evidence" in lowered
    )
