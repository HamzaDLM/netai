from pathlib import Path

from tests.evals.harness import load_jsonl, predict_specialist


def test_routing_eval_accuracy_threshold() -> None:
    dataset = Path(__file__).resolve().parent / "datasets" / "routing_cases.jsonl"
    rows = load_jsonl(dataset)

    total = len(rows)
    correct = sum(
        1
        for row in rows
        if predict_specialist(row["question"]) == row["expected_specialist"]
    )
    accuracy = correct / total if total else 0.0

    assert total >= 5
    assert accuracy >= 0.80
