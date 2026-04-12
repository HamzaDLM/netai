from tests.evals.harness import is_grounded_when_missing_evidence


def test_grounding_eval_flags_answers_that_admit_missing_evidence() -> None:
    assert is_grounded_when_missing_evidence(
        "Evidence is insufficient to conclude root cause."
    )
    assert is_grounded_when_missing_evidence(
        "Not enough evidence to identify a failing node."
    )


def test_grounding_eval_rejects_unqualified_confident_answer_without_evidence_marker() -> (
    None
):
    assert not is_grounded_when_missing_evidence(
        "The issue is definitely BGP without any doubt."
    )
