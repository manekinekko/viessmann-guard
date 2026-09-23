"""Pure, conservative detection using reported observations, never device commands."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, cast
from uuid import uuid4

SERIAL_VERSION = 2
MAX_CLEANING_HISTORY = 50
MAX_SNOOZE_SECONDS = 7 * 86400


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int, str)):
        return None
    try:
        result = float(value)
    except ValueError, OverflowError:
        return None
    return result if math.isfinite(result) else None


def _label(value: object) -> str:
    number = _number(value)
    if number is not None:
        return str(int(number)) if number.is_integer() else str(number)
    return str(value).strip().casefold()


def _timestamp(value: object) -> float | None:
    return None if isinstance(value, str) else _number(value)


def convert_flow(value: float | str | None, unit: str | None) -> float:
    """Convert an explicitly supported volumetric unit to litres per minute."""
    factors = {
        "l/min": 1.0,
        "l/h": 1 / 60,
        "m³/h": 1000 / 60,
        "m3/h": 1000 / 60,
        "m³/s": 60000.0,
        "m3/s": 60000.0,
        "us gal/min": 3.785411784,
    }
    number = _number(value)
    if number is None or number < 0:
        raise ValueError("Flow must be a finite, nonnegative number")
    if not isinstance(unit, str) or unit.strip().casefold() not in factors:
        raise ValueError("Unsupported flow unit; gallons must explicitly use US gal/min")
    converted = number * factors[unit.strip().casefold()]
    if not math.isfinite(converted):
        raise ValueError("Converted flow must be finite")
    return converted


def validate_capture(value: Any) -> dict[str, Any] | None:
    """Accept a detached, strictly bounded capture; legacy absence stays unknown."""
    if value is None:
        return None
    keys = {
        "version",
        "decided_at",
        "flow",
        "flow_reported_at",
        "unit",
        "reason",
        "duration_s",
        "observed_since",
        "minimum",
        "relative_drop_pct",
        "reference",
        "mode",
        "pump",
        "pump_speed",
        "speed_configured",
        "source_fingerprint",
        "fault",
        "fault_reported_at",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ValueError("Invalid incident evidence schema")
    if value["unit"] != "L/min" or value["reason"] not in {
        "absolute_low_flow",
        "relative_flow_decline",
        "native_fault",
    }:
        raise ValueError("Invalid incident evidence rule/unit")
    for key in ("decided_at", "duration_s", "observed_since"):
        if _timestamp(value[key]) is None or value[key] < 0:
            raise ValueError("Invalid incident evidence time")
    for key in (
        "flow",
        "flow_reported_at",
        "minimum",
        "relative_drop_pct",
        "reference",
        "pump_speed",
        "fault_reported_at",
    ):
        if value[key] is not None and (_timestamp(value[key]) is None or value[key] < 0):
            raise ValueError("Invalid incident evidence measurement")
    if (value["flow"] is None) != (value["flow_reported_at"] is None):
        raise ValueError("Incomplete incident flow evidence")
    if value["observed_since"] > value["decided_at"] or (
        value["flow_reported_at"] is not None and value["flow_reported_at"] > value["decided_at"]
    ):
        raise ValueError("Invalid incident evidence chronology")
    if type(value["speed_configured"]) is not bool or any(
        value[key] is not None and (not isinstance(value[key], str) or len(value[key]) > 128)
        for key in ("mode", "pump", "source_fingerprint", "fault")
    ):
        raise ValueError("Invalid incident evidence context")
    if value["pump_speed"] is not None and value["pump_speed"] > 100:
        raise ValueError("Invalid incident speed")
    return dict(value)


@dataclass(frozen=True, slots=True)
class Settings:
    min_flow_l_min: float | None = None
    absolute_persistence_s: float = 180
    relative_drop_pct: float = 25
    relative_persistence_s: float = 1800
    hysteresis_pct: float = 10
    recovery_s: float = 300
    startup_grace_s: float = 180
    stale_after_s: float = 180
    calibration_samples: int = 10
    calibration_duration_s: float = 600
    pump_tolerance_pct: float = 5
    running_modes: tuple[str, ...] = ()
    idle_modes: tuple[str, ...] = ()
    excluded_modes: tuple[str, ...] = ()
    pump_on_values: tuple[str, ...] = ("on",)
    pump_off_values: tuple[str, ...] = ("off",)
    fault_values: tuple[str, ...] = ()
    fault_clear_values: tuple[str, ...] = ("off",)

    def __post_init__(self) -> None:
        for name in (
            "min_flow_l_min",
            "absolute_persistence_s",
            "relative_persistence_s",
            "recovery_s",
            "startup_grace_s",
            "stale_after_s",
            "calibration_duration_s",
            "relative_drop_pct",
            "hysteresis_pct",
            "pump_tolerance_pct",
        ):
            value = getattr(self, name)
            if name == "min_flow_l_min" and value is None:
                continue
            if isinstance(value, (bool, str)) or _number(value) is None or value < 0:
                raise ValueError(f"{name} must be a finite, nonnegative number")
        if (
            self.min_flow_l_min is not None and self.min_flow_l_min <= 0
        ) or self.stale_after_s <= 0:
            raise ValueError("min_flow_l_min and stale_after_s must be greater than zero")
        if not 0 < self.relative_drop_pct < 100:
            raise ValueError("relative_drop_pct must be between zero and 100")
        if self.hysteresis_pct >= 100 or self.pump_tolerance_pct > 100:
            raise ValueError("hysteresis_pct and pump_tolerance_pct must be below 100")
        if (
            isinstance(self.calibration_samples, bool)
            or not isinstance(self.calibration_samples, int)
            or not 2 <= self.calibration_samples <= 1000
        ):
            raise ValueError("calibration_samples must be an integer between 2 and 1000")
        for names in (
            ("running_modes", "idle_modes", "excluded_modes"),
            ("pump_on_values", "pump_off_values"),
            ("fault_values", "fault_clear_values"),
        ):
            seen: set[str] = set()
            for name in names:
                values = getattr(self, name)
                if not isinstance(values, tuple) or any(
                    not isinstance(value, str)
                    or not value.strip()
                    or _label(value) in {"unknown", "unavailable", "none"}
                    for value in values
                ):
                    raise ValueError(f"{name} must be a tuple of explicit, usable values")
                normalized = tuple(_label(value) for value in values)
                if seen.intersection(normalized):
                    raise ValueError(f"{name} overlaps another value mapping")
                seen.update(normalized)
                object.__setattr__(self, name, normalized)


@dataclass(frozen=True, slots=True)
class Measurement:
    value: float | str | None
    observed_at: float | None
    unit: str | None = None
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class Snapshot:
    now: float
    flow: Measurement
    mode: Measurement
    pump: Measurement | None = None
    pump_speed: Measurement | None = None
    fault: Measurement | None = None


@dataclass(frozen=True, slots=True)
class Result:
    state: str
    reason: str
    flow: float | None
    reference: float | None
    decline_pct: float | None
    anomaly_duration: float
    incident_id: str | None
    incident_severity: str | None
    incident_confirmed: bool
    transition: str | None
    last_cleaned: float | None
    acked: bool
    snoozed_until: float | None


@dataclass(frozen=True, slots=True)
class _Context:
    mode: str
    pump_speed: float | None


@dataclass(slots=True)
class _Window:
    started_at: float
    samples: int = 1


@dataclass(slots=True)
class _Calibration:
    context: _Context
    requested_at: float
    started_at: float | None = None
    count: int = 0
    mean: float = 0

    def reset(self) -> None:
        self.started_at = None
        self.count = 0
        self.mean = 0


class Engine:
    """Evaluate immutable snapshots; persistence contains no elapsed-time credit.

    Pump speeds are percentages; tolerance is measured in percentage points.
    Calibration explicitly starts with ``confirm_calibration`` and uses only
    subsequent reports. A recovered result has no active incident ID; callers
    needing the closed ID should retain the preceding result.
    Internal phases retain startup, calibration, idle, and excluded context.
    Adapters map those phases to their public entity state enumeration.
    """

    def __init__(
        self,
        settings: Settings,
        restored: dict | None = None,
        *,
        source_fingerprint: str | None = None,
    ) -> None:
        self.settings = settings
        self._source_fingerprint = source_fingerprint
        self._baseline: dict[str, Any] | None = None
        self._incident: dict[str, Any] | None = None
        self._last_incident: dict[str, Any] | None = None
        self._acked = False
        self._snoozed_until: float | None = None
        self._cleaning_history: list[float] = []
        self._last_cleaned: float | None = None
        self._confirmed = False
        self._restart = restored is not None
        self._boot_at: float | None = None
        self._last_now: float | None = None
        self._last_flow_at: float | None = None
        self._last_flow_signature: tuple[object, ...] | None = None
        self._context: _Context | None = None
        self._context_since: float | None = None
        self._valid_until: float | None = None
        self._absolute: _Window | None = None
        self._relative: _Window | None = None
        self._recovery: _Window | None = None
        self._fault_since: float | None = None
        self._calibration: _Calibration | None = None
        self._last_healthy = False
        if isinstance(restored, dict):
            self._restore(restored)
        self.result = self._result("diagnostic_unavailable", "awaiting_observations")

    def _restore(self, data: dict) -> None:
        if not data:
            return
        if type(data.get("version")) is not int or data["version"] not in (1, SERIAL_VERSION):
            raise ValueError(f"Unsupported engine restoration version; expected {SERIAL_VERSION}")
        baseline = data.get("baseline")
        if isinstance(baseline, dict):
            value = _number(baseline.get("value"))
            mode = baseline.get("mode")
            speed = baseline.get("pump_speed")
            confirmed_at = _number(baseline.get("confirmed_at"))
            if (
                value is not None
                and value > 0
                and isinstance(mode, str)
                and mode in self.settings.running_modes
                and confirmed_at is not None
                and confirmed_at >= 0
                and (speed is None or (_number(speed) is not None and 0 <= float(speed) <= 100))
            ):
                self._baseline = {
                    "value": value,
                    "mode": mode,
                    "pump_speed": None if speed is None else float(speed),
                    "confirmed_at": confirmed_at,
                }
        incident = data.get("incident")
        if isinstance(incident, dict):
            identifier = incident.get("id")
            opened_at = _number(incident.get("opened_at"))
            if (
                isinstance(identifier, str)
                and len(identifier) == 32
                and all(char in "0123456789abcdef" for char in identifier)
                and isinstance(incident.get("severity"), str)
                and incident.get("severity") in {"watch", "urgent"}
                and isinstance(incident.get("reason"), str)
                and incident.get("reason")
                in {"absolute_low_flow", "relative_flow_decline", "native_fault"}
                and opened_at is not None
                and opened_at >= 0
            ):
                self._incident = {
                    "id": identifier,
                    "severity": incident["severity"],
                    "reason": incident["reason"],
                    "opened_at": opened_at,
                    "opening": validate_capture(incident.get("opening")),
                    "escalation": validate_capture(incident.get("escalation")),
                }
                self._acked = data.get("acked") is True
                snooze = _number(data.get("snoozed_until"))
                if snooze is not None and snooze >= 0:
                    self._snoozed_until = snooze
        history = data.get("cleaning_history")
        if isinstance(history, list):
            self._cleaning_history = [
                number
                for entry in history[-MAX_CLEANING_HISTORY:]
                if (number := _number(entry)) is not None and number >= 0
            ]
            self._cleaning_history.sort()
        last_cleaned = _number(data.get("last_cleaned"))
        if last_cleaned is not None and last_cleaned >= 0:
            self._last_cleaned = last_cleaned
        if self._cleaning_history:
            self._last_cleaned = max(self._last_cleaned or 0, self._cleaning_history[-1])
        if isinstance(data.get("last_incident"), dict):
            closed = data["last_incident"]
            restored_closed = Engine(
                self.settings, {"version": SERIAL_VERSION, "incident": closed}
            ).incident
            closed_at = _timestamp(closed.get("closed_at"))
            if (
                restored_closed is None
                or closed_at is None
                or closed_at < restored_closed["opened_at"]
            ):
                raise ValueError("Invalid closed incident time")
            self._last_incident = {**restored_closed, "closed_at": closed_at}
        elif data.get("last_incident") is not None:
            raise ValueError("Invalid closed incident")

    @property
    def incident(self) -> dict[str, Any] | None:
        return deepcopy(self._incident)

    @property
    def last_incident(self) -> dict[str, Any] | None:
        return deepcopy(self._last_incident)

    def serialize(self) -> dict:
        """Return detached, JSON-compatible durable data, excluding all timers."""
        return {
            "version": SERIAL_VERSION,
            "baseline": None if self._baseline is None else dict(self._baseline),
            "incident": self.incident,
            "last_incident": self.last_incident,
            "acked": self._acked,
            "snoozed_until": self._snoozed_until,
            "last_cleaned": self._last_cleaned,
            "cleaning_history": list(self._cleaning_history),
        }

    def _result(
        self,
        state: str,
        reason: str,
        flow: float | None = None,
        decline: float | None = None,
        duration: float = 0,
        transition: str | None = None,
    ) -> Result:
        if state == "normal" and self.settings.min_flow_l_min is None:
            state = "diagnostic_unavailable"
            if reason in ("healthy", "calibration_complete", "baseline_unconfirmed"):
                reason = "minimum_not_configured"
        return Result(
            state=state,
            reason=reason,
            flow=flow,
            reference=None if self._baseline is None else self._baseline["value"],
            decline_pct=decline,
            anomaly_duration=max(0.0, duration),
            incident_id=None if self._incident is None else self._incident["id"],
            incident_severity=None if self._incident is None else self._incident["severity"],
            incident_confirmed=self._incident is not None and self._confirmed,
            transition=transition,
            last_cleaned=self._last_cleaned,
            acked=self._acked,
            snoozed_until=self._snoozed_until,
        )

    def _reset(self) -> None:
        self._absolute = self._relative = self._recovery = None
        self._fault_since = None
        self._context = None
        self._context_since = self._valid_until = None
        self._last_healthy = False
        self._confirmed = False
        if self._calibration is not None:
            self._calibration.reset()

    def _not_ready(self, state: str, reason: str, flow: float | None = None) -> Result:
        self._reset()
        self.result = self._result(state, reason, flow)
        return self.result

    def _problem(self, measurement: Measurement | None, role: str, now: float) -> str | None:
        if measurement is not None and measurement.status == "stale":
            return f"{role}_stale"
        if (
            measurement is None
            or measurement.status != "ok"
            or measurement.value is None
            or _label(measurement.value) in {"", "unknown", "unavailable", "none"}
        ):
            return f"{role}_unavailable"
        observed = _timestamp(measurement.observed_at)
        if observed is None or observed < 0 or observed > now:
            return f"{role}_unavailable"
        if now - observed > self.settings.stale_after_s:
            return f"{role}_stale"
        return None

    def _same_context(self, first: _Context, second: _Context) -> bool:
        if first.mode != second.mode:
            return False
        if first.pump_speed is None or second.pump_speed is None:
            return first.pump_speed is second.pump_speed
        return abs(first.pump_speed - second.pump_speed) <= self.settings.pump_tolerance_pct

    def _comparable(self, context: _Context) -> bool:
        return self._baseline is not None and self._same_context(
            _Context(self._baseline["mode"], self._baseline["pump_speed"]), context
        )

    def _flow_report(self, snapshot: Snapshot) -> tuple[bool, str | None]:
        observed = _timestamp(snapshot.flow.observed_at)
        if observed is None or observed < 0 or observed > snapshot.now:
            return False, None
        signature = (snapshot.flow.value, snapshot.flow.unit, snapshot.flow.status)
        if self._last_flow_at is not None:
            if observed < self._last_flow_at:
                return False, "flow_out_of_order"
            if observed == self._last_flow_at:
                if signature != self._last_flow_signature:
                    return False, "flow_changed_without_report"
                return False, None
        self._last_flow_at = observed
        self._last_flow_signature = signature
        return True, None

    @staticmethod
    def _advance(window: _Window | None, new_report: bool, now: float) -> _Window | None:
        if new_report:
            if window is None:
                return _Window(now)
            window.samples = min(2, window.samples + 1)
        return window

    @staticmethod
    def _mature(window: _Window | None, now: float, duration: float) -> bool:
        return window is not None and window.samples >= 2 and now - window.started_at >= duration

    def _capture(self, snapshot: Snapshot, reason: str, duration: float) -> dict[str, Any]:
        def fresh(item: Measurement | None, role: str) -> bool:
            return (
                self._problem(item, role, snapshot.now) is None
                and item is not None
                and self._after_boot([item])
            )

        flow = None
        if (
            fresh(snapshot.flow, "flow")
            and self._last_flow_at == snapshot.flow.observed_at
            and self._last_flow_signature
            == (snapshot.flow.value, snapshot.flow.unit, snapshot.flow.status)
        ):
            try:
                flow = convert_flow(snapshot.flow.value, snapshot.flow.unit)
            except ValueError:
                pass  # Native faults can open without a usable flow source.
        mode = _label(snapshot.mode.value) if fresh(snapshot.mode, "mode") else None
        pump = (
            _label(snapshot.pump.value) if snapshot.pump and fresh(snapshot.pump, "pump") else None
        )
        speed = (
            _number(snapshot.pump_speed.value)
            if snapshot.pump_speed
            and fresh(snapshot.pump_speed, "pump_speed")
            and snapshot.pump_speed.unit == "%"
            else None
        )
        if speed is not None and not 0 <= speed <= 100:
            speed = None
        comparable = mode is not None and self._comparable(_Context(mode, speed))
        return {
            "version": 1,
            "decided_at": snapshot.now,
            "flow": flow,
            "flow_reported_at": snapshot.flow.observed_at if flow is not None else None,
            "unit": "L/min",
            "reason": reason,
            "duration_s": duration,
            "observed_since": snapshot.now - duration,
            "minimum": self.settings.min_flow_l_min,
            "relative_drop_pct": self.settings.relative_drop_pct
            if reason == "relative_flow_decline"
            else None,
            "reference": self._baseline["value"] if comparable and self._baseline else None,
            "mode": mode,
            "pump": pump,
            "pump_speed": speed,
            "speed_configured": snapshot.pump_speed is not None,
            "source_fingerprint": self._source_fingerprint,
            "fault": str(snapshot.fault.value)[:128]
            if snapshot.fault and fresh(snapshot.fault, "fault")
            else None,
            "fault_reported_at": snapshot.fault.observed_at
            if snapshot.fault and fresh(snapshot.fault, "fault")
            else None,
        }

    def _open(self, severity: str, reason: str, snapshot: Snapshot, duration: float) -> str | None:
        self._confirmed = True
        self._calibration = None
        if self._incident is None:
            self._incident = {
                "id": uuid4().hex,
                "severity": severity,
                "reason": reason,
                "opened_at": snapshot.now,
                "opening": self._capture(snapshot, reason, duration),
                "escalation": None,
            }
            self._acked = False
            self._snoozed_until = None
            return "opened"
        if self._incident["severity"] == "watch" and severity == "urgent":
            self._incident["severity"] = severity
            self._incident["reason"] = reason
            self._incident["escalation"] = self._capture(snapshot, reason, duration)
            self._acked = False
            return "escalated"
        if self._incident["severity"] == severity:
            self._incident["reason"] = reason
        return None

    def _after_boot(self, measurements: list[Measurement]) -> bool:
        return not self._restart or all(
            measurement.observed_at is not None
            and self._boot_at is not None
            and measurement.observed_at > self._boot_at
            for measurement in measurements
        )

    def evaluate(self, snapshot: Snapshot) -> Result:
        now = _timestamp(snapshot.now)
        if now is None or now < 0:
            raise ValueError("Snapshot time must be finite and nonnegative")
        if self._boot_at is None:
            self._boot_at = now
            if self._snoozed_until is not None:
                self._snoozed_until = min(self._snoozed_until, now + MAX_SNOOZE_SECONDS)
        if self._snoozed_until is not None and now >= self._snoozed_until:
            self._snoozed_until = None
        if self._last_now is not None and now < self._last_now:
            return self._not_ready("diagnostic_unavailable", "clock_moved_backwards")
        self._last_now = now
        new_report, report_problem = self._flow_report(snapshot)
        if self._valid_until is not None and now > self._valid_until:
            self._reset()

        needed: list[Measurement] = []
        if snapshot.fault is not None or self.settings.fault_values:
            problem = self._problem(snapshot.fault, "fault", now)
            if problem:
                return self._not_ready("diagnostic_unavailable", problem)
            assert snapshot.fault is not None
            fault = _label(snapshot.fault.value)
            if fault in self.settings.fault_values:
                self._absolute = self._relative = self._recovery = None
                self._context = None
                self._context_since = None
                self._last_healthy = False
                self._calibration = None
                self._valid_until = (
                    cast(float, snapshot.fault.observed_at) + self.settings.stale_after_s
                )
                if self._fault_since is None:
                    self._fault_since = now
                transition = None
                if self._after_boot([snapshot.fault]):
                    transition = self._open(
                        "urgent", "native_fault", snapshot, now - self._fault_since
                    )
                else:
                    self._confirmed = False
                self.result = self._result(
                    "urgent",
                    "native_fault",
                    duration=now - self._fault_since,
                    transition=transition,
                )
                return self.result
            if fault not in self.settings.fault_clear_values:
                return self._not_ready("diagnostic_unavailable", "fault_unmapped")
            needed.append(snapshot.fault)
        self._fault_since = None
        if snapshot.pump is None:
            return self._not_ready("diagnostic_unavailable", "pump_not_configured")
        problem = self._problem(snapshot.mode, "mode", now)
        if problem:
            return self._not_ready("diagnostic_unavailable", problem)
        mode = _label(snapshot.mode.value)
        if mode in self.settings.idle_modes:
            return self._not_ready("idle", "mode_idle")
        if mode in self.settings.excluded_modes:
            return self._not_ready("excluded", "mode_excluded")
        if mode not in self.settings.running_modes:
            return self._not_ready("diagnostic_unavailable", "mode_unmapped")
        problem = self._problem(snapshot.pump, "pump", now)
        if problem:
            return self._not_ready("diagnostic_unavailable", problem)
        pump = _label(snapshot.pump.value)
        if pump in self.settings.pump_off_values:
            return self._not_ready("idle", "pump_off")
        if pump not in self.settings.pump_on_values:
            return self._not_ready("diagnostic_unavailable", "pump_unmapped")
        needed.extend((snapshot.mode, snapshot.pump))
        speed: float | None = None
        if snapshot.pump_speed is not None:
            problem = self._problem(snapshot.pump_speed, "pump_speed", now)
            if problem:
                return self._not_ready("diagnostic_unavailable", problem)
            speed = _number(snapshot.pump_speed.value)
            if (
                speed is None
                or not 0 <= speed <= 100
                or snapshot.pump_speed.unit not in (None, "%")
            ):
                return self._not_ready("diagnostic_unavailable", "pump_speed_invalid")
            needed.append(snapshot.pump_speed)
        problem = self._problem(snapshot.flow, "flow", now)
        if problem:
            return self._not_ready("diagnostic_unavailable", problem)
        if report_problem:
            return self._not_ready("diagnostic_unavailable", report_problem)
        try:
            flow = convert_flow(snapshot.flow.value, snapshot.flow.unit)
        except ValueError:
            return self._not_ready("diagnostic_unavailable", "flow_invalid")
        needed.append(snapshot.flow)
        if not self._after_boot(needed):
            return self._not_ready("diagnostic_unavailable", "awaiting_post_restart_reports", flow)
        self._valid_until = (
            min(cast(float, item.observed_at) for item in needed) + self.settings.stale_after_s
        )
        context = _Context(mode, speed)
        if self._context is None or not self._same_context(self._context, context):
            self._absolute = self._relative = self._recovery = None
            self._confirmed = False
            self._last_healthy = False
            self._context = context
            self._context_since = now
            if self._calibration is not None:
                if self._same_context(self._calibration.context, context):
                    self._calibration.reset()
                else:
                    self._calibration = None
        assert self._context_since is not None
        if now - self._context_since < self.settings.startup_grace_s:
            self.result = self._result("startup", "startup_grace", flow)
            return self.result

        comparable = self._comparable(context)
        decline = (
            max(0.0, (self._baseline["value"] - flow) / self._baseline["value"] * 100)
            if comparable and self._baseline is not None
            else None
        )
        minimum = self.settings.min_flow_l_min
        absolute_low = minimum is not None and flow < minimum
        relative_low = decline is not None and decline >= self.settings.relative_drop_pct
        self._absolute = self._advance(self._absolute, new_report, now) if absolute_low else None
        self._relative = self._advance(self._relative, new_report, now) if relative_low else None
        healthy = (
            flow >= minimum * (1 + self.settings.hysteresis_pct / 100)
            if minimum is not None
            else flow > 0
        )
        if decline is not None:
            healthy = healthy and decline <= max(
                0.0, self.settings.relative_drop_pct - self.settings.hysteresis_pct
            )
        self._last_healthy = healthy
        duration = max(
            (now - window.started_at for window in (self._absolute, self._relative) if window),
            default=0.0,
        )
        transition = None
        if self._mature(self._absolute, now, self.settings.absolute_persistence_s):
            assert self._absolute is not None
            transition = self._open(
                "urgent", "absolute_low_flow", snapshot, now - self._absolute.started_at
            )
        elif self._mature(self._relative, now, self.settings.relative_persistence_s) and (
            self._incident is None or self._incident["severity"] == "watch"
        ):
            assert self._relative is not None
            transition = self._open(
                "watch", "relative_flow_decline", snapshot, now - self._relative.started_at
            )

        if self._incident is not None:
            if minimum is None and self._incident["reason"] != "relative_flow_decline":
                self._recovery = None
                self._confirmed = False
                self.result = self._result("diagnostic_unavailable", "minimum_not_configured", flow)
                return self.result
            if self._incident["reason"] == "relative_flow_decline" and not comparable:
                self._recovery = None
                self._confirmed = False
                reason = "baseline_context_mismatch"
            elif healthy:
                self._recovery = self._advance(self._recovery, new_report, now)
                reason = "recovery_pending"
                if self._mature(self._recovery, now, self.settings.recovery_s):
                    self._last_incident = {**deepcopy(self._incident), "closed_at": now}
                    self._incident = None
                    self._acked = False
                    self._snoozed_until = None
                    self._confirmed = False
                    self._recovery = None
                    self.result = self._result(
                        "normal", "healthy", flow, decline, transition="recovered"
                    )
                    return self.result
            else:
                self._recovery = None
                if absolute_low or relative_low:
                    reason = (
                        self._incident["reason"]
                        if self._confirmed
                        else "incident_pending_revalidation"
                    )
                else:
                    reason = "recovery_hysteresis"
            self.result = self._result(
                self._incident["severity"], reason, flow, decline, duration, transition
            )
            return self.result

        if self._calibration is not None:
            calibration = self._calibration
            if not healthy:
                calibration.reset()
            elif new_report and cast(float, snapshot.flow.observed_at) > calibration.requested_at:
                observed_at = cast(float, snapshot.flow.observed_at)
                if calibration.started_at is None:
                    calibration.started_at = observed_at
                calibration.count += 1
                calibration.mean += (flow - calibration.mean) / calibration.count
                if (
                    calibration.count >= self.settings.calibration_samples
                    and observed_at - calibration.started_at >= self.settings.calibration_duration_s
                    and self._same_context(calibration.context, context)
                ):
                    self._baseline = {
                        "value": calibration.mean,
                        "mode": calibration.context.mode,
                        "pump_speed": calibration.context.pump_speed,
                        "confirmed_at": calibration.requested_at,
                    }
                    self._calibration = None
                    self.result = self._result(
                        "normal",
                        "calibration_complete",
                        flow,
                        max(0.0, (calibration.mean - flow) / calibration.mean * 100),
                    )
                    return self.result
            self.result = self._result(
                "calibrating", "calibration_sampling", flow, decline, duration
            )
            return self.result
        reason = (
            "absolute_low_pending"
            if absolute_low
            else "relative_decline_pending"
            if relative_low
            else "baseline_unconfirmed"
            if self._baseline is None
            else "baseline_context_mismatch"
            if not comparable
            else "healthy"
        )
        self.result = self._result("normal", reason, flow, decline, duration)
        return self.result

    def _action_time(self, now: float) -> float:
        value = _timestamp(now)
        if value is None or value < 0 or (self._last_now is not None and value < self._last_now):
            raise ValueError("Action time must be finite, nonnegative, and not precede evaluation")
        return value

    def acknowledge(self, now: float) -> None:
        self._action_time(now)
        if self._incident is None:
            raise ValueError("There is no active incident to acknowledge")
        self._acked = True
        self.result = replace(self.result, acked=True, transition=None)

    def snooze(self, now: float, seconds: float) -> None:
        now = self._action_time(now)
        duration = _number(seconds)
        if duration is None or not 0 < duration <= MAX_SNOOZE_SECONDS:
            raise ValueError(f"Snooze must be between zero and {MAX_SNOOZE_SECONDS} seconds")
        if self._incident is None:
            raise ValueError("There is no active incident to snooze")
        self._snoozed_until = now + duration
        if not math.isfinite(self._snoozed_until):
            raise ValueError("Snooze expiry must be finite")
        self.result = replace(self.result, snoozed_until=self._snoozed_until, transition=None)

    def record_cleaning(self, now: float) -> None:
        now = self._action_time(now)
        if self._last_cleaned is not None and now < self._last_cleaned:
            raise ValueError("Cleaning time must not precede the previous cleaning")
        self._last_cleaned = now
        self._cleaning_history.append(now)
        del self._cleaning_history[:-MAX_CLEANING_HISTORY]
        self.result = replace(self.result, last_cleaned=now, transition=None)
        if self._calibration is not None:
            self._calibration = None
            self.result = replace(
                self.result, state="normal", reason="calibration_cancelled_by_cleaning"
            )

    def confirm_calibration(self, now: float) -> None:
        now = self._action_time(now)
        if self._incident is not None:
            raise ValueError("Calibration is not allowed while an incident is active")
        if self._calibration is not None:
            raise ValueError("Calibration is already in progress")
        if (
            self._context is None
            or self._valid_until is None
            or now > self._valid_until
            or not self._last_healthy
            or (
                self.result.state != "normal"
                and not (
                    self.settings.min_flow_l_min is None
                    and self.result.reason
                    in ("minimum_not_configured", "baseline_context_mismatch")
                )
            )
        ):
            raise ValueError("Calibration requires fresh, healthy, running telemetry after startup")
        self._calibration = _Calibration(self._context, now)
        self.result = replace(
            self.result, state="calibrating", reason="calibration_sampling", transition=None
        )
