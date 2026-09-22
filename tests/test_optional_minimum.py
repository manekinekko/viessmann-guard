"""An absent manufacturer limit never becomes a guessed threshold or healthy evidence."""

import pytest
from test_engine import absolute_incident, settings, snapshot

from custom_components.viessmann_guard.engine import Engine


@pytest.mark.parametrize("flow", [0, 1, 100])
def test_no_minimum_no_absolute_incident_or_false_normal(flow):
    engine = Engine(settings(min_flow_l_min=None))
    for now in (0, 30, 60, 90):
        result = engine.evaluate(snapshot(now, flow))
        assert result.state == "diagnostic_unavailable"
        assert result.incident_id is None
        assert result.reference is None
        assert result.reason == "minimum_not_configured"
    if not flow:
        with pytest.raises(ValueError):
            engine.confirm_calibration(90)


def test_explicit_relative_reference_and_recovery_without_absolute_limit():
    engine = Engine(settings(min_flow_l_min=None))
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    for now in (1, 11, 21):
        result = engine.evaluate(snapshot(now))
    assert result.reference == 40
    assert result.state == "diagnostic_unavailable"
    engine.evaluate(snapshot(22, 29))
    result = engine.evaluate(snapshot(52, 29))
    assert result.state == "watch" and result.transition == "opened"
    engine.record_cleaning(52)
    assert engine.result.incident_id
    result = engine.evaluate(snapshot(53, 40, mode="dhw"))
    assert result.incident_id  # Different operating context is not recovery evidence.
    assert result.transition is None
    engine.evaluate(snapshot(54, 40))
    result = engine.evaluate(snapshot(74, 40))
    assert result.transition == "recovered"
    assert result.state == "diagnostic_unavailable"


def test_removing_absolute_limit_cannot_resolve_restored_incident():
    original = Engine(settings())
    incident = absolute_incident(original)
    engine = Engine(settings(min_flow_l_min=None), original.serialize())
    for now in (21, 22, 42, 62, 82):
        result = engine.evaluate(snapshot(now, 40))
        assert result.incident_id == incident.incident_id
        assert result.transition != "recovered"
        assert result.incident_confirmed is False


def test_native_mapped_fault_precedes_missing_minimum_and_excluded_mode():
    engine = Engine(
        settings(min_flow_l_min=None, fault_values=("on",), fault_clear_values=("off",))
    )
    result = engine.evaluate(snapshot(0, None, fault="on", mode="defrost", pump=None))
    assert result.state == "urgent"
    assert result.reason == "native_fault"
    assert result.transition == "opened"


@pytest.mark.parametrize("mode", ["auto", "dhw_unknown", "transition", "defrost"])
def test_unknown_excluded_modes_never_calibrate_without_minimum(mode):
    engine = Engine(settings(min_flow_l_min=None))
    engine.evaluate(snapshot(0, mode=mode))
    with pytest.raises(ValueError):
        engine.confirm_calibration(0)
