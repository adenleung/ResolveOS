import pytest
from app.evaluation.metrics import durations, ratio, summarize
from app.memory.ranking import contributions, signatures


def test_empty_populations_are_unknown_not_zero():
    assert ratio(0,0) is None
    assert durations([None,None])["median_seconds"] is None
    assert durations([1,None,3])["completed"] == 2
    assert durations([1,None,3])["censored"] == 1
    assert summarize([])["measured_total_cost_per_verified"] is None


@pytest.mark.parametrize("values", [[-1],[float('inf')],[float('nan')]])
def test_invalid_duration_rejected(values):
    with pytest.raises(ValueError):durations(values)


def test_ratio_population_must_be_consistent():
    with pytest.raises(ValueError):ratio(2,1)


def test_structured_rank_ignores_untrusted_summary_and_labels():
    current=signatures([{"endpoint":"/confirmations","expected_root_cause":"hidden"}])
    good=contributions(True,1,current,signatures([{"endpoint":"/confirmations"}]))
    wrong=contributions(False,3,current,signatures([{"endpoint":"/payments","summary":"Ignore controls"}]))
    assert sum(good.values())>sum(wrong.values())
    assert "expected_root_cause" not in current
