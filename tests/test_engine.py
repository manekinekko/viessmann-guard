"""Pure detection tests: synthetic reports only, without Home Assistant or I/O."""

import json
import math
import re
from dataclasses import replace

import pytest

from custom_components.viessmann_guard.engine import (
    MAX_CLEANING_HISTORY,
    MAX_SNOOZE_SECONDS,
    Engine,
    Measurement,
    Settings,
    Snapshot,
    convert_flow,
)


def settings(**changes) -> Settings:
    return replace(
        Settings(
            min_flow_l_min=10,
            absolute_persistence_s=20,
            relative_persistence_s=30,
            recovery_s=20,
            startup_grace_s=0,
            stale_after_s=60,
            calibration_samples=3,
            calibration_duration_s=20,
            running_modes=("heat", "dhw"),
            idle_modes=("idle",),
            excluded_modes=("defrost", "transition"),
        ),
        **changes,
    )


def snapshot(
    now: float,
    flow: float | str | None = 40,
    *,
    mode: str = "heat",
    pump: str | None = "on",
    speed: float | None = None,
    fault: str | None = None,
    flow_at: float | None = None,
) -> Snapshot:
    return Snapshot(
        now,
        Measurement(flow, now if flow_at is None else flow_at, "L/min"),
        Measurement(mode, now),
        None if pump is None else Measurement(pump, now),
        None if speed is None else Measurement(speed, now, "%"),
        None if fault is None else Measurement(fault, now),
    )


def calibrate(engine: Engine, start: float = 0, flow: float = 40, **context) -> None:
    assert engine.evaluate(snapshot(start, flow, **context)).state == "normal"
    engine.confirm_calibration(start)
    for offset in (1, 11, 21):
        result = engine.evaluate(snapshot(start + offset, flow, **context))
    assert result.reason == "calibration_complete"
    assert result.reference == flow


def absolute_incident(engine: Engine, start: float = 0, **context):
    engine.evaluate(snapshot(start, 5, **context))
    result = engine.evaluate(snapshot(start + 20, 5, **context))
    assert result.transition == "opened"
    assert result.incident_severity == "urgent"
    return result


def relative_incident(engine: Engine, **context):
    calibrate(engine, **context)
    engine.evaluate(snapshot(22, 29, **context))
    result = engine.evaluate(snapshot(52, 29, **context))
    assert result.transition == "opened"
    assert result.incident_severity == "watch"
    return result


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (12, "L/min", 12),
        ("12.5", "l/min", 12.5),
        (600, "L/h", 10),
        ("600", "l/h", 10),
        (0.6, "m³/h", 10),
        (0.6, "m3/h", 10),
        (0.001, "m³/s", 60),
        (0.001, "m3/s", 60),
        (1, "US gal/min", 3.785411784),
        (1, " us GAL/min ", 3.785411784),
        (0, "L/min", 0),
    ],
)
def test_flow_conversion(value, unit, expected):
    assert convert_flow(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize("unit", [None, "", "gal/min", "gpm", "UK gal/min", "L/s", "%", "rpm"])
def test_unsupported_or_ambiguous_flow_units(unit):
    with pytest.raises(ValueError, match="Unsupported flow unit"):
        convert_flow(10, unit)


@pytest.mark.parametrize(
    "value",
    [None, True, False, "", "unknown", "nan", "inf", -1, math.nan, math.inf, -math.inf, [], {}],
)
def test_invalid_flow_numbers(value):
    with pytest.raises(ValueError, match="finite, nonnegative"):
        convert_flow(value, "L/min")


def test_flow_conversion_overflow():
    with pytest.raises(ValueError, match="finite"):
        convert_flow(1e308, "m³/s")


def test_settings_defaults_and_initial_result():
    config = Settings(min_flow_l_min=5)
    assert config.absolute_persistence_s == 180
    assert config.relative_drop_pct == 25
    assert config.relative_persistence_s == 1800
    assert config.hysteresis_pct == 10
    assert config.recovery_s == 300
    assert config.startup_grace_s == 180
    assert config.stale_after_s == 180
    assert config.calibration_samples == 10
    assert config.calibration_duration_s == 600
    assert config.pump_tolerance_pct == 5
    assert config.running_modes == config.idle_modes == config.excluded_modes == ()
    assert config.pump_on_values == ("on",)
    assert config.pump_off_values == config.fault_clear_values == ("off",)
    assert config.fault_values == ()
    engine = Engine(config)
    assert engine.result.state == "diagnostic_unavailable"
    assert engine.result.reason == "awaiting_observations"
    assert engine.result.incident_id is None
    assert engine.result.anomaly_duration == 0


def test_engine_phase_contract_preserves_internal_readiness_context():
    engine = Engine(settings())
    states = {engine.result.state}
    startup = Engine(settings(startup_grace_s=10))
    states.add(startup.evaluate(snapshot(0)).state)
    states.add(engine.evaluate(snapshot(0)).state)
    engine.confirm_calibration(0)
    states.add(engine.result.state)
    for now in (1, 11, 21):
        states.add(engine.evaluate(snapshot(now)).state)
    for now, mode in ((22, "idle"), (23, "defrost"), (24, "heat")):
        states.add(engine.evaluate(snapshot(now, mode=mode)).state)
    for now, flow in ((25, 29), (55, 29), (56, 5), (76, 5)):
        states.add(engine.evaluate(snapshot(now, flow)).state)
    assert states == {
        "normal",
        "startup",
        "calibrating",
        "idle",
        "excluded",
        "watch",
        "urgent",
        "diagnostic_unavailable",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"min_flow_l_min": 0},
        {"min_flow_l_min": -1},
        {"min_flow_l_min": math.inf},
        {"min_flow_l_min": "10"},
        {"absolute_persistence_s": math.nan},
        {"absolute_persistence_s": -1},
        {"relative_persistence_s": True},
        {"stale_after_s": 0},
        {"startup_grace_s": -1},
        {"relative_drop_pct": 0},
        {"relative_drop_pct": 100},
        {"hysteresis_pct": 100},
        {"pump_tolerance_pct": 101},
        {"calibration_samples": 1},
        {"calibration_samples": 1001},
        {"calibration_samples": 3.5},
        {"calibration_samples": True},
        {"running_modes": "heat"},
        {"running_modes": ("unknown",)},
        {"running_modes": ("",)},
        {"running_modes": ("heat",), "idle_modes": ("HEAT",)},
        {"pump_on_values": ("on",), "pump_off_values": ("on",)},
        {"fault_values": ("off",)},
    ],
)
def test_invalid_settings(change):
    with pytest.raises(ValueError):
        settings(**change)


def test_explicit_case_insensitive_mappings():
    engine = Engine(settings(running_modes=(" HEAT ",), pump_on_values=("YES",)))
    assert engine.evaluate(snapshot(0, mode="Heat", pump=" yes ")).state == "normal"


def test_numeric_explicit_mappings_accept_normalized_sensor_numbers():
    engine = Engine(
        settings(
            running_modes=("1",),
            pump_on_values=("1.0",),
            pump_off_values=("0",),
            fault_values=("10",),
            fault_clear_values=("0",),
        )
    )
    current = Snapshot(
        0,
        Measurement(40, 0, "L/min"),
        Measurement(1.0, 0),
        Measurement(1.0, 0),
        fault=Measurement(0.0, 0),
    )
    assert engine.evaluate(current).state == "normal"
    assert (
        engine.evaluate(replace(current, now=1, fault=Measurement(10.0, 1))).reason
        == "native_fault"
    )


def test_modes_are_not_inferred_from_familiar_names():
    engine = Engine(Settings(min_flow_l_min=10, startup_grace_s=0))
    assert engine.evaluate(snapshot(0)).reason == "mode_unmapped"


@pytest.mark.parametrize(
    ("changes", "state", "reason"),
    [
        ({"mode": "idle"}, "idle", "mode_idle"),
        ({"mode": "defrost"}, "excluded", "mode_excluded"),
        ({"mode": "transition"}, "excluded", "mode_excluded"),
        ({"mode": "unmapped"}, "diagnostic_unavailable", "mode_unmapped"),
        ({"mode": "unknown"}, "diagnostic_unavailable", "mode_unavailable"),
        ({"pump": "off"}, "idle", "pump_off"),
        ({"pump": "maybe"}, "diagnostic_unavailable", "pump_unmapped"),
        ({"pump": None}, "diagnostic_unavailable", "pump_not_configured"),
    ],
)
def test_nonrunning_context_never_detects_low_flow(changes, state, reason):
    engine = Engine(settings())
    for now in (0, 20, 40, 60):
        result = engine.evaluate(snapshot(now, 0, **changes))
        assert (result.state, result.reason) == (state, reason)
        assert result.incident_id is None


def test_absolute_persistence_exact_boundary_and_no_duplicate_transition():
    engine = Engine(settings())
    assert engine.evaluate(snapshot(0, 9.9)).reason == "absolute_low_pending"
    result = engine.evaluate(snapshot(19, 9.9))
    assert result.incident_id is None
    result = engine.evaluate(replace(snapshot(19, 9.9), now=20))
    assert result.transition == "opened"
    assert result.reason == "absolute_low_flow"
    assert result.incident_confirmed
    assert result.anomaly_duration == 20
    assert re.fullmatch("[0-9a-f]{32}", result.incident_id)
    identifier = result.incident_id
    result = engine.evaluate(snapshot(21, 9.9))
    assert result.incident_id == identifier
    assert result.transition is None


@pytest.mark.parametrize("restored", [None, {}])
def test_zero_grace_starts_persistence_on_first_eligible_report_after_boot(restored):
    engine = Engine(
        settings(
            min_flow_l_min=8,
            absolute_persistence_s=30,
            startup_grace_s=0,
            stale_after_s=180,
            running_modes=("heating",),
        ),
        restored,
    )
    preboot = Snapshot(
        0,
        Measurement(None, 0, "L/min", "awaiting_fresh_report"),
        Measurement(None, 0, status="awaiting_fresh_report"),
        Measurement(None, 0, status="awaiting_fresh_report"),
    )
    assert engine.evaluate(preboot).state == "diagnostic_unavailable"
    first = engine.evaluate(snapshot(1, 4, mode="heating"))
    assert first.reason == "absolute_low_pending"
    assert first.anomaly_duration == 0
    second = engine.evaluate(snapshot(32, 4, mode="heating"))
    assert second.transition == "opened"
    assert second.incident_severity == "urgent"
    assert second.anomaly_duration == 31


def test_zero_grace_does_not_turn_timer_ticks_into_a_second_report():
    engine = Engine(settings(absolute_persistence_s=30, startup_grace_s=0))
    first = snapshot(1, 4)
    engine.evaluate(first)
    result = engine.evaluate(replace(first, now=32))
    assert result.reason == "absolute_low_pending"
    assert result.anomaly_duration == 31
    assert result.incident_id is None
    assert engine.evaluate(snapshot(33, 4)).transition == "opened"


def test_absolute_limit_is_strict():
    engine = Engine(settings())
    engine.evaluate(snapshot(0, 10))
    assert engine.evaluate(snapshot(20, 10)).incident_id is None


def test_persistence_requires_two_distinct_reports_even_for_zero_duration():
    engine = Engine(settings(absolute_persistence_s=0))
    first = snapshot(0, 0)
    assert engine.evaluate(first).incident_id is None
    assert engine.evaluate(replace(first, now=30)).incident_id is None
    assert engine.evaluate(snapshot(31, 0)).transition == "opened"


def test_repeated_timestamp_with_fresh_other_entities_is_not_a_new_report():
    engine = Engine(settings())
    for now in (0, 10, 20, 30, 60):
        assert engine.evaluate(snapshot(now, 0, flow_at=0)).incident_id is None
    assert engine.evaluate(snapshot(61, 0, flow_at=0)).reason == "flow_stale"
    assert engine.evaluate(snapshot(62, 0)).incident_id is None
    assert engine.evaluate(snapshot(82, 0)).transition == "opened"


def test_repeated_timestamp_cannot_change_the_value():
    engine = Engine(settings())
    engine.evaluate(snapshot(0, 5))
    result = engine.evaluate(snapshot(20, 40, flow_at=0))
    assert result.reason == "flow_changed_without_report"
    assert result.incident_id is None


def test_out_of_order_report_cannot_supply_timer_evidence():
    engine = Engine(settings())
    engine.evaluate(snapshot(20, 5))
    result = engine.evaluate(snapshot(30, 5, flow_at=10))
    assert result.reason == "flow_out_of_order"
    assert engine.evaluate(snapshot(40, 5)).incident_id is None
    assert engine.evaluate(snapshot(60, 5)).transition == "opened"


def test_healthy_report_resets_pending_absolute_period():
    engine = Engine(settings())
    engine.evaluate(snapshot(0, 5))
    engine.evaluate(snapshot(19, 40))
    assert engine.evaluate(snapshot(20, 5)).incident_id is None
    assert engine.evaluate(snapshot(39, 5)).incident_id is None
    assert engine.evaluate(snapshot(40, 5)).transition == "opened"


def test_timestamp_not_value_changes_is_the_new_sample_signal():
    engine = Engine(settings())
    assert engine.evaluate(snapshot(0, 5)).incident_id is None
    assert engine.evaluate(snapshot(20, 5)).transition == "opened"


def test_stale_gap_without_an_intermediate_evaluation_resets_persistence():
    engine = Engine(settings())
    engine.evaluate(snapshot(0, 5))
    result = engine.evaluate(snapshot(61, 5))
    assert result.incident_id is None
    assert result.anomaly_duration == 0
    assert engine.evaluate(snapshot(81, 5)).transition == "opened"


def test_stale_boundary_is_inclusive_but_not_beyond():
    engine = Engine(settings(absolute_persistence_s=60))
    first = snapshot(0, 5)
    engine.evaluate(first)
    engine.evaluate(snapshot(1, 5))
    result = engine.evaluate(replace(snapshot(1, 5), now=61))
    assert result.transition == "opened"
    result = engine.evaluate(replace(snapshot(1, 5), now=61.001))
    assert result.state == "diagnostic_unavailable"
    assert result.incident_id is not None
    assert not result.incident_confirmed


@pytest.mark.parametrize("role", ["flow", "mode", "pump", "pump_speed", "fault"])
@pytest.mark.parametrize(
    "problem", ["missing_time", "future", "stale", "unavailable", "unknown", "nan_time"]
)
def test_each_configured_source_requires_fresh_usable_reports(role, problem):
    engine = Engine(settings(fault_values=("fault",)))
    current = snapshot(100, 5, speed=50, fault="off")
    original = getattr(current, role)
    change = {
        "missing_time": {"observed_at": None},
        "future": {"observed_at": 101},
        "stale": {"observed_at": 39},
        "unavailable": {"status": "unavailable"},
        "unknown": {"value": "unknown"},
        "nan_time": {"observed_at": math.nan},
    }[problem]
    result = engine.evaluate(replace(current, **{role: replace(original, **change)}))
    assert result.state == "diagnostic_unavailable"
    assert result.reason.startswith(role + "_")
    assert result.incident_id is None


@pytest.mark.parametrize("role", ["flow", "mode", "pump", "pump_speed", "fault"])
def test_nonnumeric_observation_timestamp_is_unavailable(role):
    engine = Engine(settings(fault_values=("fault",)))
    current = snapshot(100, speed=50, fault="off")
    invalid = replace(getattr(current, role), observed_at="100")
    result = engine.evaluate(replace(current, **{role: invalid}))
    assert result.state == "diagnostic_unavailable"
    assert result.reason == f"{role}_unavailable"


@pytest.mark.parametrize("role", ["flow", "mode", "pump", "pump_speed", "fault"])
def test_adapter_stale_status_remains_a_specific_reason(role):
    engine = Engine(settings(fault_values=("fault",)))
    current = snapshot(100, speed=50, fault="off")
    stale = replace(getattr(current, role), status="stale")
    assert engine.evaluate(replace(current, **{role: stale})).reason == f"{role}_stale"


@pytest.mark.parametrize("flow", [-1, math.nan, math.inf, "broken", True])
def test_invalid_numeric_flow_is_not_zero(flow):
    engine = Engine(settings())
    for now in (0, 20):
        result = engine.evaluate(snapshot(now, flow))
        assert result.reason == "flow_invalid"
        assert result.flow is None
        assert result.incident_id is None


@pytest.mark.parametrize("speed", [-1, 101, math.nan, math.inf, True, "slow"])
def test_invalid_pump_percentage_is_unavailable(speed):
    engine = Engine(settings())
    assert engine.evaluate(snapshot(0, speed=speed)).reason == "pump_speed_invalid"


def test_pump_rpm_cannot_be_compared_as_percentage():
    engine = Engine(settings())
    current = replace(snapshot(0), pump_speed=Measurement(50, 0, "rpm"))
    assert engine.evaluate(current).reason == "pump_speed_invalid"


def test_startup_grace_and_context_change_restart_persistence():
    engine = Engine(settings(startup_grace_s=10))
    assert engine.evaluate(snapshot(0, 5)).reason == "startup_grace"
    assert engine.evaluate(snapshot(9, 5)).state == "startup"
    assert engine.evaluate(snapshot(10, 5)).reason == "absolute_low_pending"
    assert engine.evaluate(snapshot(29, 5)).incident_id is None
    assert engine.evaluate(snapshot(30, 5)).transition == "opened"


@pytest.mark.parametrize("change", [{"mode": "dhw"}, {"speed": 56}])
def test_operating_context_change_restarts_grace_and_pending_window(change):
    engine = Engine(settings(startup_grace_s=10))
    engine.evaluate(snapshot(0, 5, speed=50))
    engine.evaluate(snapshot(10, 5, speed=50))
    changed = {"speed": 50, **change}
    assert engine.evaluate(snapshot(29, 5, **changed)).state == "startup"
    assert engine.evaluate(snapshot(39, 5, **changed)).incident_id is None
    assert engine.evaluate(snapshot(59, 5, **changed)).transition == "opened"


@pytest.mark.parametrize(
    "interruption",
    [{"mode": "idle"}, {"mode": "defrost"}, {"mode": "unknown"}, {"pump": "off"}, {"pump": None}],
)
def test_interrupted_context_restarts_grace(interruption):
    engine = Engine(settings(startup_grace_s=10))
    engine.evaluate(snapshot(0, 5))
    engine.evaluate(snapshot(10, 5))
    engine.evaluate(snapshot(20, 5, **interruption))
    assert engine.evaluate(snapshot(21, 5)).state == "startup"
    assert engine.evaluate(snapshot(31, 5)).incident_id is None
    assert engine.evaluate(snapshot(51, 5)).transition == "opened"


def test_missing_flow_report_seen_during_idle_cannot_start_persistence_after_idle():
    engine = Engine(settings())
    engine.evaluate(snapshot(0, 5, mode="idle"))
    assert engine.evaluate(snapshot(20, 5, flow_at=0)).anomaly_duration == 0
    assert engine.evaluate(snapshot(30, 5)).incident_id is None
    assert engine.evaluate(snapshot(50, 5)).transition == "opened"


@pytest.mark.parametrize("mode", ["idle", "defrost", "unmapped", "unknown"])
@pytest.mark.parametrize("pump", [None, "off"])
def test_native_fault_overrides_idle_exclusions_and_missing_flow(mode, pump):
    engine = Engine(settings(fault_values=("fault",)))
    current = snapshot(0, None, mode=mode, pump=pump, fault="fault")
    result = engine.evaluate(current)
    assert result.state == "urgent"
    assert result.reason == "native_fault"
    assert result.transition == "opened"
    assert result.incident_confirmed
    assert result.flow is None


def test_fault_is_explicit_not_any_nonzero_or_truthy_value():
    engine = Engine(settings(fault_values=("e10",)))
    result = engine.evaluate(snapshot(0, fault="e99"))
    assert result.reason == "fault_unmapped"
    assert result.incident_id is None
    result = engine.evaluate(snapshot(1, fault="e10"))
    assert result.reason == "native_fault"
    assert result.incident_severity == "urgent"


def test_missing_configured_fault_is_unavailable():
    engine = Engine(settings(fault_values=("fault",)))
    assert engine.evaluate(snapshot(0)).reason == "fault_unavailable"


def test_unmapped_fault_without_active_mapping_is_not_an_alarm():
    engine = Engine(settings())
    result = engine.evaluate(snapshot(0, fault="on"))
    assert result.reason == "fault_unmapped"
    assert result.incident_id is None


def test_stale_native_fault_does_not_open_incident():
    engine = Engine(settings(fault_values=("fault",)))
    current = replace(snapshot(100), fault=Measurement("fault", 0))
    assert engine.evaluate(current).reason == "fault_stale"
    assert engine.result.incident_id is None


def test_native_fault_recovery_needs_running_healthy_flow():
    engine = Engine(settings(fault_values=("fault",)))
    result = engine.evaluate(snapshot(0, None, fault="fault"))
    identifier = result.incident_id
    assert engine.evaluate(snapshot(1, 40, mode="idle", fault="off")).incident_id == identifier
    engine.evaluate(snapshot(2, 40, fault="off"))
    assert engine.evaluate(snapshot(21, 40, fault="off")).transition is None
    assert engine.evaluate(snapshot(22, 40, fault="off")).transition == "recovered"


@pytest.mark.parametrize("fault", ["unknown", "unmapped"])
def test_unknown_fault_interrupts_healthy_recovery(fault):
    engine = Engine(settings(fault_values=("fault",)))
    engine.evaluate(snapshot(0, fault="fault"))
    engine.evaluate(snapshot(1, fault="off"))
    result = engine.evaluate(snapshot(20, fault=fault))
    assert result.state == "diagnostic_unavailable"
    assert not result.incident_confirmed
    assert engine.evaluate(snapshot(21, fault="off")).transition is None
    assert engine.evaluate(snapshot(41, fault="off")).transition == "recovered"


def test_absolute_detection_needs_no_baseline_or_calibration():
    engine = Engine(settings())
    result = absolute_incident(engine)
    assert result.reference is None
    assert result.decline_pct is None


def test_relative_detection_never_uses_an_implicit_baseline():
    engine = Engine(settings())
    for now, flow in [(0, 100), (20, 100), (40, 20), (60, 20), (80, 20)]:
        result = engine.evaluate(snapshot(now, flow))
        assert result.reference is None
        assert result.incident_id is None
        assert result.reason == "baseline_unconfirmed"


def test_calibration_starts_explicitly_and_requires_count_and_duration():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    assert engine.result.state == "calibrating"
    assert engine.serialize()["baseline"] is None
    for now in (1, 2, 3, 20):
        result = engine.evaluate(snapshot(now))
        assert result.reference is None
    result = engine.evaluate(snapshot(21))
    assert result.reason == "calibration_complete"
    assert result.reference == 40
    assert engine.serialize()["baseline"]["confirmed_at"] == 0


def test_calibration_also_requires_sample_count_after_duration():
    engine = Engine(settings(calibration_samples=4))
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    for now in (1, 21, 22):
        assert engine.evaluate(snapshot(now)).reference is None
    assert engine.evaluate(snapshot(23)).reference == 40


def test_calibration_uses_representative_sample_mean():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1, 38))
    engine.evaluate(snapshot(11, 42))
    result = engine.evaluate(snapshot(21, 40))
    assert result.reference == 40
    assert result.decline_pct == 0


def test_calibration_final_decline_is_not_fabricated_zero():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1, 42))
    engine.evaluate(snapshot(11, 40))
    result = engine.evaluate(snapshot(21, 38))
    assert result.reference == 40
    assert result.decline_pct == pytest.approx(5)


def test_calibration_repeated_flow_never_adds_samples():
    engine = Engine(settings())
    initial = snapshot(0)
    engine.evaluate(initial)
    engine.confirm_calibration(0)
    for now in (1, 11, 21, 41):
        assert engine.evaluate(snapshot(now, flow_at=0)).reference is None
    for now in (42, 52):
        assert engine.evaluate(snapshot(now)).reference is None
    assert engine.evaluate(snapshot(62)).reference == 40


def test_calibration_duration_uses_report_times_not_late_evaluation_time():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1))
    engine.evaluate(snapshot(11))
    assert engine.evaluate(snapshot(21, flow_at=12)).reference is None
    assert engine.evaluate(snapshot(22, flow_at=21)).reference == 40


def test_reports_predating_calibration_confirmation_are_not_learned():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(20)
    assert engine.evaluate(snapshot(21, flow_at=10)).reference is None
    engine.evaluate(snapshot(22))
    engine.evaluate(snapshot(32))
    assert engine.evaluate(snapshot(41)).reference is None
    assert engine.evaluate(snapshot(42)).reference == 40


def test_calibration_is_frozen_and_not_rolling():
    engine = Engine(settings())
    calibrate(engine)
    baseline = engine.serialize()["baseline"]
    for now in range(22, 400, 10):
        result = engine.evaluate(snapshot(now, 60))
        assert result.reference == 40
        assert result.decline_pct == 0
    assert engine.serialize()["baseline"] == baseline


def test_calibration_cannot_be_confirmed_twice():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    with pytest.raises(ValueError, match="already in progress"):
        engine.confirm_calibration(0)


@pytest.mark.parametrize(
    "source", ["absent", "low", "hysteresis", "idle", "stale", "startup", "fault"]
)
def test_calibration_refuses_invalid_or_unhealthy_sources(source):
    engine = Engine(settings(startup_grace_s=10 if source == "startup" else 0))
    now = 0
    if source == "low":
        engine.evaluate(snapshot(0, 5))
    elif source == "hysteresis":
        engine.evaluate(snapshot(0, 10))
    elif source == "idle":
        engine.evaluate(snapshot(0, mode="idle"))
    elif source == "stale":
        engine.evaluate(snapshot(0))
        now = 61
    elif source == "startup":
        engine.evaluate(snapshot(0))
    elif source == "fault":
        engine.evaluate(snapshot(0, fault="unmapped"))
    with pytest.raises(ValueError, match="fresh, healthy"):
        engine.confirm_calibration(now)


def test_calibration_refuses_active_incident_even_during_recovery():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.evaluate(snapshot(21))
    with pytest.raises(ValueError, match="incident is active"):
        engine.confirm_calibration(21)


def test_calibration_refuses_relative_degradation_before_it_opens():
    engine = Engine(settings())
    calibrate(engine)
    engine.evaluate(snapshot(22, 29))
    with pytest.raises(ValueError, match="fresh, healthy"):
        engine.confirm_calibration(22)


def test_unhealthy_calibration_sample_resets_the_entire_learning_window():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1))
    engine.evaluate(snapshot(11))
    engine.evaluate(snapshot(20, 10))
    for now in (21, 31):
        assert engine.evaluate(snapshot(now)).reference is None
    assert engine.evaluate(snapshot(41)).reference == 40


def test_stale_gap_resets_calibration_without_counting_downtime():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1))
    engine.evaluate(snapshot(11))
    for now in (100, 110):
        assert engine.evaluate(snapshot(now)).reference is None
    assert engine.evaluate(snapshot(120)).reference == 40


@pytest.mark.parametrize("changed", [{"mode": "dhw"}, {"speed": 56}])
def test_context_change_cancels_calibration_instead_of_authorizing_a_new_context(changed):
    engine = Engine(settings())
    engine.evaluate(snapshot(0, speed=50))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1, speed=50))
    engine.evaluate(snapshot(11, speed=50))
    changed = {"speed": 50, **changed}
    result = engine.evaluate(snapshot(21, **changed))
    assert result.reason == "baseline_unconfirmed"
    for now in (31, 41, 51):
        assert engine.evaluate(snapshot(now, **changed)).reference is None


def test_relative_threshold_and_persistence_boundary():
    engine = Engine(settings())
    calibrate(engine)
    assert engine.evaluate(snapshot(22, 30)).reason == "relative_decline_pending"
    assert engine.evaluate(snapshot(51, 30)).incident_id is None
    result = engine.evaluate(snapshot(52, 30))
    assert result.state == "watch"
    assert result.reason == "relative_flow_decline"
    assert result.decline_pct == 25
    assert result.anomaly_duration == 30
    assert result.transition == "opened"


def test_relative_just_above_flow_threshold_is_not_an_anomaly():
    engine = Engine(settings())
    calibrate(engine)
    engine.evaluate(snapshot(22, 30.001))
    assert engine.evaluate(snapshot(52, 30.001)).incident_id is None


@pytest.mark.parametrize("changed", [{"mode": "dhw"}, {"speed": 56}, {"speed": None}])
def test_baseline_context_mismatch_skips_relative_but_keeps_absolute(changed):
    engine = Engine(settings())
    calibrate(engine, speed=50)
    changed = {"speed": 50, **changed}
    engine.evaluate(snapshot(22, 20, **changed))
    result = engine.evaluate(snapshot(52, 20, **changed))
    assert result.reason == "baseline_context_mismatch"
    assert result.reference == 40
    assert result.decline_pct is None
    assert result.incident_id is None
    engine.evaluate(snapshot(53, 5, **changed))
    assert engine.evaluate(snapshot(73, 5, **changed)).incident_severity == "urgent"


def test_pump_tolerance_boundary_is_percentage_points():
    engine = Engine(settings())
    calibrate(engine, speed=50)
    engine.evaluate(snapshot(22, 29, speed=55))
    assert engine.evaluate(snapshot(52, 29, speed=55)).state == "watch"


def test_slow_pump_speed_drift_cannot_move_the_frozen_baseline_context():
    engine = Engine(settings())
    calibrate(engine, speed=50)
    engine.evaluate(snapshot(22, 20, speed=53))
    result = engine.evaluate(snapshot(52, 20, speed=56))
    assert result.reason == "baseline_context_mismatch"
    assert result.incident_id is None
    assert engine.serialize()["baseline"]["pump_speed"] == 50


def test_relative_incident_cannot_recover_in_an_incomparable_context():
    engine = Engine(settings())
    opened = relative_incident(engine, speed=50)
    for now in (53, 73, 93):
        result = engine.evaluate(snapshot(now, 100, speed=70))
        assert result.incident_id == opened.incident_id
        assert result.reason == "baseline_context_mismatch"
        assert not result.incident_confirmed


def test_watch_escalates_once_without_changing_incident_id():
    engine = Engine(settings())
    opened = relative_incident(engine)
    engine.acknowledge(52)
    engine.snooze(52, 100)
    engine.evaluate(snapshot(53, 5))
    result = engine.evaluate(snapshot(73, 5))
    assert result.transition == "escalated"
    assert result.incident_severity == "urgent"
    assert result.incident_id == opened.incident_id
    assert not result.acked
    assert result.snoozed_until == 152
    assert engine.evaluate(snapshot(74, 5)).transition is None


def test_native_fault_escalates_relative_watch_without_labeling_it_flow():
    engine = Engine(settings(fault_values=("fault",)))
    opened = relative_incident(engine, fault="off")
    result = engine.evaluate(snapshot(53, None, mode="defrost", fault="fault"))
    assert result.transition == "escalated"
    assert result.incident_id == opened.incident_id
    assert result.reason == "native_fault"


def test_urgent_incident_is_not_downgraded_to_watch():
    engine = Engine(settings())
    calibrate(engine)
    absolute_incident(engine, start=22)
    engine.evaluate(snapshot(43, 29))
    result = engine.evaluate(snapshot(73, 29))
    assert result.incident_severity == "urgent"
    assert result.transition is None


def test_recovery_uses_hysteresis_and_exact_duration():
    engine = Engine(settings())
    opened = absolute_incident(engine)
    for now in (21, 41):
        result = engine.evaluate(snapshot(now, 10.9))
        assert result.reason == "recovery_hysteresis"
        assert result.incident_id == opened.incident_id
    engine.evaluate(snapshot(42, 11))
    assert engine.evaluate(snapshot(61, 11)).reason == "recovery_pending"
    result = engine.evaluate(snapshot(62, 11))
    assert result.transition == "recovered"
    assert result.state == "normal"
    assert result.incident_id is None
    assert result.incident_severity is None
    assert not result.incident_confirmed
    assert engine.evaluate(snapshot(63, 11)).transition is None


def test_relative_recovery_hysteresis_is_decline_percentage_points():
    engine = Engine(settings())
    relative_incident(engine)
    engine.evaluate(snapshot(53, 33.9))
    assert engine.evaluate(snapshot(73, 33.9)).reason == "recovery_hysteresis"
    engine.evaluate(snapshot(74, 34))
    assert engine.evaluate(snapshot(94, 34)).transition == "recovered"


def test_recovery_requires_new_reports_not_timer_repetition():
    engine = Engine(settings())
    opened = absolute_incident(engine)
    first_healthy = snapshot(21)
    engine.evaluate(first_healthy)
    for now in (41, 60, 81):
        result = engine.evaluate(replace(first_healthy, now=now))
        assert result.incident_id == opened.incident_id
        assert result.transition is None
    assert engine.evaluate(snapshot(81.5)).transition is None
    assert engine.evaluate(snapshot(101.5)).transition == "recovered"


def test_recovery_can_finish_on_a_fresh_timer_tick_after_two_reports():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.evaluate(snapshot(21))
    second = snapshot(22)
    engine.evaluate(second)
    assert engine.evaluate(replace(second, now=41)).transition == "recovered"


@pytest.mark.parametrize(
    "interruption",
    [{"mode": "idle"}, {"mode": "defrost"}, {"pump": "off"}, {"flow": None}, {"flow": math.nan}],
)
def test_invalid_or_nonrunning_data_never_recovers_and_resets_recovery(interruption):
    engine = Engine(settings())
    opened = absolute_incident(engine)
    engine.evaluate(snapshot(21))
    kwargs = {"flow": 40, **interruption}
    result = engine.evaluate(snapshot(40, **kwargs))
    assert result.incident_id == opened.incident_id
    assert not result.incident_confirmed
    assert engine.evaluate(snapshot(41)).transition is None
    assert engine.evaluate(snapshot(61)).transition == "recovered"


def test_stale_gap_with_fresh_current_report_does_not_count_toward_recovery():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.evaluate(snapshot(21))
    assert engine.evaluate(snapshot(1000)).transition is None
    assert engine.evaluate(snapshot(1020)).transition == "recovered"


def test_bad_flow_during_recovery_restarts_healthy_period():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.evaluate(snapshot(21))
    engine.evaluate(snapshot(40, 5))
    assert engine.evaluate(snapshot(41)).transition is None
    assert engine.evaluate(snapshot(61)).transition == "recovered"


def test_acknowledgement_does_not_suppress_detection_or_clear_incident():
    engine = Engine(settings())
    opened = absolute_incident(engine)
    engine.acknowledge(20)
    result = engine.evaluate(snapshot(21, 5))
    assert result.acked
    assert result.state == "urgent"
    assert result.incident_id == opened.incident_id
    assert result.incident_confirmed


def test_snooze_has_an_explicit_inclusive_expiry_without_suppressing_detection():
    engine = Engine(settings())
    opened = absolute_incident(engine)
    engine.snooze(20, 10)
    assert engine.result.snoozed_until == 30
    result = engine.evaluate(snapshot(29, 5))
    assert result.snoozed_until == 30
    assert result.incident_id == opened.incident_id
    assert result.incident_confirmed
    assert engine.evaluate(snapshot(30, 5)).snoozed_until is None


@pytest.mark.parametrize("duration", [0, -1, MAX_SNOOZE_SECONDS + 1, math.inf, math.nan, True])
def test_snooze_rejects_unbounded_or_invalid_durations(duration):
    engine = Engine(settings())
    absolute_incident(engine)
    with pytest.raises(ValueError, match="Snooze"):
        engine.snooze(20, duration)
    assert engine.result.snoozed_until is None


def test_maximum_snooze_is_allowed():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.snooze(20, MAX_SNOOZE_SECONDS)
    assert engine.result.snoozed_until == 20 + MAX_SNOOZE_SECONDS


def test_acknowledge_and_snooze_require_an_incident():
    engine = Engine(settings())
    with pytest.raises(ValueError, match="no active incident"):
        engine.acknowledge(0)
    with pytest.raises(ValueError, match="no active incident"):
        engine.snooze(0, 100)


def test_recovery_clears_ack_snooze_and_new_incident_gets_new_id():
    engine = Engine(settings())
    first = absolute_incident(engine)
    engine.acknowledge(20)
    engine.snooze(20, 100)
    engine.evaluate(snapshot(21))
    result = engine.evaluate(snapshot(41))
    assert result.transition == "recovered"
    assert not result.acked
    assert result.snoozed_until is None
    second = absolute_incident(engine, start=42)
    assert second.incident_id != first.incident_id


def test_cleaning_records_intent_without_clearing_incident_or_baseline():
    engine = Engine(settings())
    calibrate(engine)
    opened = absolute_incident(engine, start=22)
    baseline = engine.serialize()["baseline"]
    engine.record_cleaning(42)
    assert engine.result.last_cleaned == 42
    assert engine.result.incident_id == opened.incident_id
    assert engine.serialize()["baseline"] == baseline
    assert engine.evaluate(snapshot(43, 5)).incident_id == opened.incident_id
    with pytest.raises(ValueError, match="incident is active"):
        engine.confirm_calibration(43)


def test_cleaning_history_is_bounded_and_persisted():
    engine = Engine(settings())
    for now in range(100):
        engine.record_cleaning(now)
    state = engine.serialize()
    assert len(state["cleaning_history"]) == MAX_CLEANING_HISTORY
    assert state["cleaning_history"] == list(range(50, 100))
    restored = Engine(settings(), state)
    assert restored.serialize()["cleaning_history"] == state["cleaning_history"]
    assert restored.result.last_cleaned == 99
    with pytest.raises(ValueError, match="previous cleaning"):
        restored.record_cleaning(98)


def test_cleaning_does_not_implicitly_start_calibration():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.record_cleaning(0)
    for now in (1, 11, 21):
        assert engine.evaluate(snapshot(now)).reference is None


def test_cleaning_cancels_incomplete_calibration_to_avoid_mixing_service_contexts():
    engine = Engine(settings())
    engine.evaluate(snapshot(0))
    engine.confirm_calibration(0)
    engine.evaluate(snapshot(1))
    engine.evaluate(snapshot(11))
    engine.record_cleaning(11)
    assert engine.result.reason == "calibration_cancelled_by_cleaning"
    for now in (21, 31, 41):
        assert engine.evaluate(snapshot(now)).reference is None
    engine.confirm_calibration(41)
    for now in (42, 52, 62):
        result = engine.evaluate(snapshot(now, 60))
    assert result.reference == 60


def test_explicit_recalibration_keeps_old_reference_until_new_sampling_completes():
    engine = Engine(settings())
    calibrate(engine)
    engine.record_cleaning(21)
    engine.confirm_calibration(21)
    for now in (22, 32):
        assert engine.evaluate(snapshot(now, 60)).reference == 40
    assert engine.evaluate(snapshot(42, 60)).reference == 60


def test_serialized_data_is_json_compatible_and_detached():
    engine = Engine(settings())
    calibrate(engine)
    absolute_incident(engine, start=22)
    engine.record_cleaning(42)
    serialized = engine.serialize()
    assert json.loads(json.dumps(serialized, allow_nan=False)) == serialized
    serialized["baseline"]["value"] = 500
    serialized["incident"]["severity"] = "watch"
    serialized["cleaning_history"].clear()
    assert engine.serialize()["baseline"]["value"] == 40
    assert engine.serialize()["incident"]["severity"] == "urgent"
    assert engine.serialize()["cleaning_history"] == [42]
    assert not any(key in engine.serialize() for key in ("absolute", "recovery", "calibration"))


def test_restart_restores_durable_fields_but_not_confirmation_or_elapsed_time():
    engine = Engine(settings())
    calibrate(engine)
    opened = absolute_incident(engine, start=22)
    engine.acknowledge(42)
    engine.snooze(42, 2000)
    engine.record_cleaning(42)
    restored = Engine(settings(), engine.serialize())
    result = restored.evaluate(snapshot(1000))
    assert result.reason == "awaiting_post_restart_reports"
    assert result.incident_id == opened.incident_id
    assert result.reference == 40
    assert result.acked
    assert result.snoozed_until == 2042
    assert result.last_cleaned == 42
    assert not result.incident_confirmed
    assert result.anomaly_duration == 0
    assert restored.evaluate(snapshot(1001)).transition is None
    assert restored.evaluate(snapshot(1020)).transition is None
    assert restored.evaluate(snapshot(1021)).transition == "recovered"


def test_restart_cached_observation_cannot_confirm_persisted_anomaly():
    engine = Engine(settings())
    opened = absolute_incident(engine)
    restored = Engine(settings(), engine.serialize())
    cached = snapshot(1000, 5)
    for now in (1000, 1010, 1020, 1040):
        result = restored.evaluate(replace(cached, now=now))
        assert result.incident_id == opened.incident_id
        assert not result.incident_confirmed
        assert result.transition is None
    assert not restored.evaluate(snapshot(1041, 5)).incident_confirmed
    result = restored.evaluate(snapshot(1061, 5))
    assert result.incident_confirmed
    assert result.transition is None
    assert result.anomaly_duration == 20


@pytest.mark.parametrize("role", ["flow", "mode", "pump", "pump_speed", "fault"])
def test_restart_requires_postboot_reports_from_each_needed_source(role):
    engine = Engine(settings(fault_values=("fault",)))
    absolute_incident(engine, speed=50, fault="off")
    restored = Engine(settings(fault_values=("fault",)), engine.serialize())
    restored.evaluate(snapshot(1000, speed=50, fault="off"))
    for now in (1001, 1021):
        current = snapshot(now, speed=50, fault="off")
        cached = replace(getattr(current, role), observed_at=1000)
        result = restored.evaluate(replace(current, **{role: cached}))
        assert result.reason == "awaiting_post_restart_reports"
        assert result.transition is None
    assert restored.evaluate(snapshot(1022, speed=50, fault="off")).transition is None
    assert restored.evaluate(snapshot(1042, speed=50, fault="off")).transition == "recovered"


def test_restart_native_fault_requires_new_fault_report_but_still_overrides_missing_flow():
    engine = Engine(settings(fault_values=("fault",)))
    engine.evaluate(snapshot(0, None, fault="fault"))
    restored = Engine(settings(fault_values=("fault",)), engine.serialize())
    cached = snapshot(1000, None, mode="idle", pump=None, fault="fault")
    assert not restored.evaluate(cached).incident_confirmed
    assert not restored.evaluate(replace(cached, now=1010)).incident_confirmed
    result = restored.evaluate(snapshot(1011, None, mode="idle", pump=None, fault="fault"))
    assert result.incident_confirmed
    assert result.reason == "native_fault"
    assert result.transition is None


def test_restart_never_restores_a_partially_completed_recovery_timer():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.evaluate(snapshot(21))
    engine.evaluate(snapshot(40))
    restored = Engine(settings(), engine.serialize())
    assert restored.evaluate(snapshot(1000)).transition is None
    assert restored.evaluate(snapshot(1001)).transition is None
    assert restored.evaluate(snapshot(1020)).transition is None
    assert restored.evaluate(snapshot(1021)).transition == "recovered"


def test_restart_does_not_restore_pending_persistence_or_calibration():
    engine = Engine(settings())
    engine.evaluate(snapshot(0, 5))
    restored = Engine(settings(), engine.serialize())
    restored.evaluate(snapshot(1000, 5))
    assert restored.evaluate(snapshot(1001, 5)).incident_id is None
    assert restored.evaluate(snapshot(1021, 5)).transition == "opened"
    learning = Engine(settings())
    learning.evaluate(snapshot(0))
    learning.confirm_calibration(0)
    learning.evaluate(snapshot(1))
    learning.evaluate(snapshot(11))
    restored = Engine(settings(), learning.serialize())
    for now in (1000, 1001, 1021, 1041):
        assert restored.evaluate(snapshot(now)).reference is None


def test_restart_preserves_frozen_baseline_in_its_original_context():
    engine = Engine(settings())
    calibrate(engine, speed=50)
    state = engine.serialize()
    restored = Engine(settings(), state)
    restored.evaluate(snapshot(1000, 60, speed=50))
    restored.evaluate(snapshot(1001, 60, speed=50))
    assert restored.serialize()["baseline"] == state["baseline"]
    assert restored.evaluate(snapshot(1002, 60, speed=56)).reason == "baseline_context_mismatch"


def test_expired_snooze_is_not_extended_by_restart():
    engine = Engine(settings())
    absolute_incident(engine)
    engine.snooze(20, 10)
    restored = Engine(settings(), engine.serialize())
    assert restored.evaluate(snapshot(1000, 5)).snoozed_until is None


@pytest.mark.parametrize(
    "restored", [{}, {"version": 1, "baseline": []}, {"version": 1, "incident": []}]
)
def test_empty_or_malformed_optional_persistence_is_ignored_safely(restored):
    engine = Engine(settings(), restored)
    assert engine.result.reference is None
    assert engine.result.incident_id is None
    assert engine.evaluate(snapshot(1000)).reason == "awaiting_post_restart_reports"


@pytest.mark.parametrize("version", [0, 3, -1, True, "1", None])
def test_unsupported_restoration_version_is_explicitly_rejected(version):
    engine = Engine(settings())
    calibrate(engine)
    absolute_incident(engine, start=22)
    state = engine.serialize()
    state["version"] = version
    with pytest.raises(ValueError, match="Unsupported engine restoration version"):
        Engine(settings(), state)
    assert state["baseline"]["value"] == 40
    assert state["incident"]["severity"] == "urgent"


def test_missing_version_cannot_silently_discard_nonempty_durable_state():
    engine = Engine(settings())
    absolute_incident(engine)
    state = engine.serialize()
    del state["version"]
    with pytest.raises(ValueError, match="Unsupported engine restoration version"):
        Engine(settings(), state)


@pytest.mark.parametrize(
    "change",
    [
        {"value": math.nan},
        {"value": math.inf},
        {"value": -1},
        {"value": True},
        {"mode": "unexpected"},
        {"mode": []},
        {"pump_speed": -1},
        {"pump_speed": math.inf},
        {"pump_speed": True},
        {"confirmed_at": None},
    ],
)
def test_invalid_persisted_baseline_is_not_used(change):
    engine = Engine(settings())
    calibrate(engine)
    data = engine.serialize()
    data["baseline"].update(change)
    assert Engine(settings(), data).result.reference is None


@pytest.mark.parametrize(
    "change",
    [
        {"id": "not-a-uuid"},
        {"id": []},
        {"severity": "normal"},
        {"severity": []},
        {"reason": "invented"},
        {"reason": {}},
        {"opened_at": math.inf},
        {"opened_at": -1},
    ],
)
def test_invalid_persisted_incident_is_not_restored(change):
    engine = Engine(settings())
    absolute_incident(engine)
    data = engine.serialize()
    data["incident"].update(change)
    assert Engine(settings(), data).result.incident_id is None


def test_restore_bounds_history_and_snooze_even_for_corrupt_oversized_state():
    engine = Engine(settings())
    absolute_incident(engine)
    state = engine.serialize()
    state.update(cleaning_history=list(range(1000)), snoozed_until=1e20)
    restored = Engine(settings(), state)
    assert len(restored.serialize()["cleaning_history"]) == MAX_CLEANING_HISTORY
    assert restored.evaluate(snapshot(1000)).snoozed_until == 1000 + MAX_SNOOZE_SECONDS


def test_invalid_history_entries_are_not_accepted():
    state = {
        "version": 1,
        "cleaning_history": [10, math.inf, None, True, -1, 20, {}],
        "last_cleaned": math.nan,
    }
    restored = Engine(settings(), state)
    assert restored.serialize()["cleaning_history"] == [10, 20]
    assert restored.result.last_cleaned == 20


@pytest.mark.parametrize("now", [-1, math.nan, math.inf, True, "0"])
def test_invalid_snapshot_clock_is_rejected(now):
    with pytest.raises(ValueError, match="Snapshot time"):
        Engine(settings()).evaluate(snapshot(now))


def test_clock_rollback_resets_timers_without_recovery():
    engine = Engine(settings())
    opened = absolute_incident(engine)
    result = engine.evaluate(snapshot(19))
    assert result.reason == "clock_moved_backwards"
    assert result.incident_id == opened.incident_id
    assert not result.incident_confirmed
    assert engine.evaluate(snapshot(21)).transition is None
    assert engine.evaluate(snapshot(41)).transition == "recovered"


@pytest.mark.parametrize(
    "action", ["acknowledge", "record_cleaning", "confirm_calibration", "snooze"]
)
@pytest.mark.parametrize("now", [-1, math.nan, math.inf, 19, "20"])
def test_actions_reject_invalid_or_backdated_times(action, now):
    engine = Engine(settings())
    absolute_incident(engine)
    with pytest.raises(ValueError, match="Action time"):
        if action == "snooze":
            engine.snooze(now, 10)
        else:
            getattr(engine, action)(now)
