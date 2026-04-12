from pathlib import Path

from tests.evals.harness import QACase, load_jsonl, score_answer_quality


def test_quality_eval_average_score_threshold() -> None:
    dataset = Path(__file__).resolve().parent / "datasets" / "network_qa.jsonl"
    rows = load_jsonl(dataset)
    cases = [
        QACase(
            question=row["question"],
            answer=row["answer"],
            required_terms=row["required_terms"],
            evidence_required=row["evidence_required"],
        )
        for row in rows
    ]

    scores = [score_answer_quality(case) for case in cases]
    average = sum(scores) / len(scores)

    assert len(scores) >= 3
    assert average >= 0.85
