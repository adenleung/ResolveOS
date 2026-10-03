import pytest

from app.domain.case_service import CaseLifecycleService, CaseState


def test_valid_transition_from_detected_to_triaged():
    service = CaseLifecycleService()
    assert service.transition(CaseState.DETECTED, CaseState.TRIAGED) is CaseState.TRIAGED


def test_invalid_transition_raises_value_error():
    service = CaseLifecycleService()
    with pytest.raises(ValueError):
        service.transition(CaseState.RESOLVED, CaseState.TRIAGED)
