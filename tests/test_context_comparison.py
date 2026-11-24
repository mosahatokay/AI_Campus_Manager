"""Local, deterministic full-versus-compact context tests; zero external calls."""
from src.context_comparison import EVENT_NAME, QUESTION, run_comparison


def test_same_question_and_truth_in_both_modes():
    experiment = run_comparison(save=False)
    full, compact = experiment["results"]
    assert full["question"] == compact["question"] == QUESTION
    assert full["expected"] == compact["expected"] == EVENT_NAME
    assert full["answer_correct"] is True
    assert compact["answer_correct"] is False


def test_reduced_context_is_measurably_smaller():
    full, compact = run_comparison(save=False)["results"]
    assert full["characters"] > compact["characters"]
    assert full["messages"] > compact["messages"]


def test_compact_context_does_not_hallucinate_missing_title():
    full, compact = run_comparison(save=False)["results"]
    assert full["answer"] == EVENT_NAME
    assert EVENT_NAME not in compact["answer"]
    assert "אין לי" in compact["answer"]


def test_same_results_on_repeated_run():
    first = run_comparison(save=False)
    second = run_comparison(save=False)
    assert first == second
