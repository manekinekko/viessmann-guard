"""Observe local Home Assistant states and manage incident notifications."""

import asyncio
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EMAIL_DEFAULTS, LIST_SETTINGS, NUMERIC_RULES, SOURCE_ROLES, public_state
from .delivery import Delivery, DeliveryError
from .engine import Engine, Settings, Snapshot
from .report import render_report
from .storage import GuardStore, validate_storage
from .telemetry import (
    iso,
    measurement,
    report_telemetry,
    scoped_entity,
    temperature_celsius,
)
from .validation import smtp_identity, validate_recipients

_LOGGER = logging.getLogger(__name__)


def configuration(entry: ConfigEntry) -> dict[str, Any]:
    return {
        **EMAIL_DEFAULTS,
        **{key: default for key, (default, _, _) in NUMERIC_RULES.items()},
        **entry.data,
        **entry.options,
    }


def settings(config: dict[str, Any]) -> Settings:
    values = {field.name: config[field.name] for field in fields(Settings) if field.name in config}
    for key in LIST_SETTINGS:
        if key in values:
            values[key] = tuple(values[key])
    return Settings(**values)


def fingerprint(config: dict[str, Any]) -> str:
    relevant = {
        key: value
        for key, value in config.items()
        if key.endswith("_entity")
        or key in LIST_SETTINGS
        or key in NUMERIC_RULES
        or key in ("min_flow_l_min", "device_ids")
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()


class GuardRuntime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = configuration(entry)
        self.started_at = dt_util.utcnow().timestamp()
        self.store = GuardStore(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.engine = Engine(settings(self.config))
        self.delivery = Delivery(self._send, self._render, self.save, self.changed)
        self.test_delivery = Delivery(self._send, self._render, self.save, self.changed)
        self.listeners: list[Callable[[], None]] = []
        self.unsubscribers: list[Callable[[], None]] = []
        self._evaluate_task: asyncio.Task | None = None
        self._delivery_task: asyncio.Task | None = None
        self._action_tasks: set[asyncio.Task[Any]] = set()
        self._lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()
        self.stopped = False
        self.trends: list[dict[str, Any]] = []
        self._last_trend: float | None = None
        self._notice: str | None = None
        self.mail_epoch = 0
        self.mail_key: str | None = None
        self.mail_kind: str | None = None
        self.mail_incident: str | None = None
        self.mail_severity: str | None = None
        self.next_reminder: float | None = None
        self.storage_error: str | None = None
        self.last_telemetry: float | None = None
        self._evaluated_evidence: tuple | None = None
        self._dispatch_kind: ContextVar[str | None] = ContextVar(
            "viessmann_guard_send_kind", default=None
        )

    async def start(self) -> None:
        restored = validate_storage(await self.store.async_load())
        engine_data = restored.get("engine")
        if restored and restored.get("fingerprint") != fingerprint(self.config):
            # Preserve unresolved incident/history, but never reuse an incompatible reference.
            engine_data = dict(engine_data or {})
            engine_data.pop("baseline", None)
        self.engine = Engine(settings(self.config), engine_data)
        self.delivery = Delivery(
            self._send, self._render, self.save, self.changed, restored.get("delivery")
        )
        self.test_delivery = Delivery(
            self._send, self._render, self.save, self.changed, restored.get("test_delivery")
        )
        self.delivery.configure(self.config["emails_enabled"], self.config["recipients"])
        self.test_delivery.configure(self.config["emails_enabled"], self.config["recipients"])
        self.mail_epoch = int(restored.get("mail_epoch", 0))
        self.mail_key = restored.get("mail_key")
        self.mail_kind = restored.get("mail_kind")
        self.mail_incident = restored.get("mail_incident")
        self.mail_severity = restored.get("mail_severity")
        if restored:
            self.test_delivery.cancel_pending()
            if self.mail_kind == "recovery":
                self.delivery.cancel_pending()
        self._notice = restored.get("notice")
        self.trends = restored.get("trends", [])[-120:]
        # A reminder is not overdue merely because Home Assistant was offline.
        self.next_reminder = self.started_at + self.config["reminder_hours"] * 3600
        ids = [self.config[f"{r}_entity"] for r in SOURCE_ROLES if self.config.get(f"{r}_entity")]
        self.unsubscribers = [
            async_track_state_change_event(self.hass, ids, self._source_event),
            async_track_state_report_event(self.hass, ids, self._source_event),
            async_track_time_interval(self.hass, self._timer, timedelta(seconds=15)),
        ]
        await self.evaluate()

    @callback
    def changed(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    @callback
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    @callback
    def _source_event(self, event: Event[Any]) -> None:
        self.schedule()

    @callback
    def _timer(self, now: datetime) -> None:
        self.schedule()

    @callback
    def schedule(self) -> None:
        if not self.stopped and (self._evaluate_task is None or self._evaluate_task.done()):
            self._evaluate_task = self.entry.async_create_background_task(
                self.hass, self.evaluate(), "Viessmann Guard evaluation", eager_start=False
            )

    def snapshot(self, now: float) -> Snapshot:
        items = {}
        for role in ("flow", "mode", "pump", "pump_speed", "fault"):
            entity_id = self.config.get(f"{role}_entity")
            state = (
                self.hass.states.get(entity_id)
                if entity_id and scoped_entity(self.hass, entity_id, self.config["device_ids"])
                else None
            )
            items[role] = (
                measurement(state, now, self.config["stale_after_s"], self.started_at)
                if entity_id or role in ("flow", "mode")
                else None
            )
            if role == "pump_speed" and (speed := items[role]) is not None and speed.unit != "%":
                items[role] = replace(speed, value=None, status="unsupported_unit")
        flow = items["flow"]
        mode = items["mode"]
        assert flow is not None and mode is not None
        return Snapshot(
            now=now,
            flow=flow,
            mode=mode,
            pump=items["pump"],
            pump_speed=items["pump_speed"],
            fault=items["fault"],
        )

    async def evaluate(self, now: float | None = None) -> None:
        async with self._lock:
            if self.stopped:
                return
            now = now if now is not None else dt_util.utcnow().timestamp()
            sample = self.snapshot(now)
            self._evaluated_evidence = self._evidence(sample)
            previous_engine = self.engine.serialize()
            result = self.engine.evaluate(sample)
            self.last_telemetry = sample.flow.observed_at
            if sample.flow.observed_at != self._last_trend and result.flow is not None:
                self._last_trend = sample.flow.observed_at
                self.trends.append(
                    {"observed_at": iso(sample.flow.observed_at), "flow": result.flow}
                )
                self.trends = self.trends[-120:]
            self._persistent_notice()
            eligible = self._mail_eligible()
            if self.config["emails_enabled"]:
                if eligible and result.incident_id:
                    if (
                        self.mail_incident != result.incident_id
                        or self.mail_severity != result.incident_severity
                        or self.mail_key is None
                    ):
                        self.mail_incident = result.incident_id
                        self.mail_severity = result.incident_severity
                        self.mail_kind = result.incident_severity or "urgent"
                        self.mail_key = f"{result.incident_id}:{self.mail_kind}:{self.mail_epoch}"
                        self.next_reminder = now + self.config["reminder_hours"] * 3600
                    elif (
                        self.next_reminder is not None
                        and now >= self.next_reminder
                        and not self._snoozed()
                    ):
                        self.mail_kind = "reminder"
                        self.mail_key = f"{result.incident_id}:reminder:{uuid.uuid4().hex}"
                        self.next_reminder = now + self.config["reminder_hours"] * 3600
                    if self.mail_kind != "reminder" or not self._snoozed():
                        self.delivery.queue(self.mail_key, self.mail_kind or "urgent", now)
                elif result.transition == "recovered":
                    self.delivery.cancel_pending()
                    self.mail_kind = "recovery"
                    self.mail_key = f"{self.mail_incident}:recovery:{self.mail_epoch}"
                    self.delivery.queue(self.mail_key, "recovery", now)
                    self.mail_incident = None
                    self.mail_severity = None
                self._schedule_delivery(now)
            if self.engine.serialize() != previous_engine:
                await self.save()
            else:
                self.store.async_delay_save(self.export, 5)
            self.changed()

    @staticmethod
    def _evidence(sample: Snapshot) -> tuple:
        return (sample.flow, sample.mode, sample.pump, sample.pump_speed, sample.fault)

    def _mail_eligible(self) -> bool:
        result = self.engine.result
        return bool(
            result.incident_id
            and result.incident_confirmed
            and result.state in ("urgent", "watch")
            and (result.incident_severity == "urgent" or self.config["watch_email"])
        )

    def _snoozed(self) -> bool:
        until = self.engine.result.snoozed_until
        return until is not None and until > dt_util.utcnow().timestamp()

    def _recovery_eligible(self) -> bool:
        result = self.engine.result
        return bool(
            result.incident_id is None
            and result.state == "normal"
            and result.reason in ("healthy", "baseline_unconfirmed", "calibration_complete")
            and result.flow is not None
            and result.flow
            >= self.config["min_flow_l_min"] * (1 + self.config["hysteresis_pct"] / 100)
        )

    def _schedule_delivery(self, now: float) -> None:
        if self._delivery_task is None or self._delivery_task.done():
            self._delivery_task = self.entry.async_create_background_task(
                self.hass, self._dispatch_pending(now), "Viessmann Guard email delivery"
            )

    async def _dispatch_pending(self, now: float) -> None:
        if (self._mail_eligible() and (self.mail_kind != "reminder" or not self._snoozed())) or (
            self.mail_kind == "recovery" and self._recovery_eligible()
        ):
            await self.delivery.dispatch(now)
        await self.test_delivery.dispatch(now)

    @property
    def recipient_statuses(self) -> dict[str, Any]:
        result = {}
        for index, target in enumerate(self.config["recipients"], start=1):
            incident = self.delivery.status_for(target)
            test = self.test_delivery.status_for(target)
            state = self.hass.states.get(target)
            name = state.name if state else ""
            if not re.fullmatch(r"[A-Za-z0-9À-ÿ ._-]{1,60}", name):
                name = f"SMTP recipient {index}"
            result[target] = {
                **(incident or test or {"status": "ready"}),
                "name": name,
                **({"test": test} if test else {}),
            }
        return result

    def _persistent_notice(self) -> None:
        result = self.engine.result
        signature = f"{result.incident_id}:{result.incident_severity}:{result.state}"
        if signature == self._notice:
            return
        if result.incident_id or result.transition == "recovered":
            from .reasons import describe_reason

            persistent_notification.async_create(
                self.hass,
                f"{result.state}: {describe_reason(result.reason, self.config['language'])}\n\n"
                + (
                    "Filtre encrassé possible, sans certitude. Faire contrôler le circuit, "
                    "les filtres, le circulateur, les vannes et les capteurs. Ceci n'est pas un dispositif de sécurité."
                    if self.config["language"] == "fr"
                    else "A dirty filter is one possible cause, not a diagnosis. Have the circuit, "
                    "filters, circulator, valves and sensors inspected. This is not a safety device."
                ),
                title=self.config["name"],
                notification_id=f"{DOMAIN}_{self.entry.entry_id}_incident",
            )
        self._notice = signature

    def prepare_options(self, config: dict[str, Any]) -> None:
        self.delivery.configure(config["emails_enabled"], config["recipients"])
        self.test_delivery.configure(config["emails_enabled"], config["recipients"])
        if not config["emails_enabled"] or config["recipients"] != self.config["recipients"]:
            self.delivery.cancel_pending()
            self.test_delivery.cancel_pending()

    async def set_emails(self, enabled: bool) -> None:
        if enabled:
            try:
                validate_recipients(self.hass, self.config["recipients"])
            except ValueError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key=str(err)
                ) from err
            if not self.config["recipients"]:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="required_recipient"
                )
        self.delivery.configure(enabled, self.config["recipients"])
        self.test_delivery.configure(enabled, self.config["recipients"])
        if enabled != self.config["emails_enabled"]:
            self.mail_epoch += 1
            self.mail_key = None
            self.mail_kind = None
            self.next_reminder = None
        self.config["emails_enabled"] = enabled
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, "emails_enabled": enabled}
        )
        await self.save()
        self.changed()
        await self.evaluate()

    async def apply_options(self) -> None:
        updated = configuration(self.entry)
        old = {k: v for k, v in self.config.items() if k != "emails_enabled"}
        new = {k: v for k, v in updated.items() if k != "emails_enabled"}
        if old != new:
            self.prepare_options(updated)
            if updated["emails_enabled"] != self.config["emails_enabled"]:
                self.mail_epoch += 1
                self.mail_key = None
                self.mail_kind = None
            await self.hass.config_entries.async_reload(self.entry.entry_id)
        elif updated["emails_enabled"] != self.config["emails_enabled"]:
            await self.set_emails(updated["emails_enabled"])

    async def action(self, action: str, hours: float = 24, confirmed: bool = False) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._action_tasks.add(task)
        try:
            await self._action(action, hours, confirmed)
        finally:
            if task is not None:
                self._action_tasks.discard(task)

    async def _action(self, action: str, hours: float, confirmed: bool) -> None:
        if self.stopped:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_unavailable"
            )
        now = dt_util.utcnow().timestamp()
        await self.evaluate(now)
        if self.stopped:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_unavailable"
            )
        try:
            if action == "test_email":
                if not self.config["emails_enabled"]:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="emails_disabled"
                    )
                if not self.config["recipients"]:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="required_recipient"
                    )
                validate_recipients(self.hass, self.config["recipients"])
                self.test_delivery.queue(f"test:{uuid.uuid4().hex}", "test", now)
                await self.test_delivery.dispatch(now)
                if any(
                    s.get("status") in ("failed", "retry")
                    for s in self.test_delivery.statuses.values()
                ):
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="smtp_error"
                    )
            elif action == "acknowledge":
                self.engine.acknowledge(now)
            elif action == "snooze":
                if not 1 <= hours <= 168:
                    raise ValueError("Snooze must be between 1 and 168 hours")
                self.engine.snooze(now, hours * 3600)
                if self.mail_kind == "reminder":
                    self.delivery.cancel_pending()
            elif action == "record_cleaning":
                self.engine.record_cleaning(now)
            elif action == "confirm_calibration":
                if not confirmed:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="confirmation_required"
                    )
                self.engine.confirm_calibration(now)
            else:
                raise ValueError("Unknown action")
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await self.save()
        self.changed()

    async def _send(self, target: str, title: str, message: str, html: str) -> None:
        kind = self._dispatch_kind.get()
        # A previous recipient may have taken minutes. Revalidate before each real action.
        for _ in range(3):
            await self.evaluate()
            current = self.snapshot(dt_util.utcnow().timestamp())
            if self._evaluated_evidence == self._evidence(current):
                break
        else:
            raise DeliveryError("telemetry_changed")
        # This check is after queue persistence and immediately before HA dispatch.
        if (
            self.stopped
            or not self.config["emails_enabled"]
            or target not in self.config["recipients"]
        ):
            raise DeliveryError("disabled")
        if kind not in ("test", "recovery") and not self._mail_eligible():
            raise DeliveryError("telemetry_not_confirmed")
        if kind == "reminder" and self._snoozed():
            raise DeliveryError("reminders_snoozed")
        if kind == "recovery" and not self._recovery_eligible():
            raise DeliveryError("telemetry_not_confirmed")
        if kind == "watch" and self.engine.result.incident_severity != "watch":
            raise DeliveryError("incident_changed")
        try:
            smtp_identity(self.hass, target)
            state = self.hass.states.get(target)
            # A never-used NotifyEntity has state "unknown" until its first accepted send.
            if state is None or state.state == "unavailable":
                raise ValueError("notifier_unavailable")
            if not self.hass.services.has_service("smtp", "send_message"):
                raise ValueError("notifier_unavailable")
            title, message, html = self._render(kind or "test")
            await self.hass.services.async_call(
                "smtp",
                "send_message",
                {"title": title, "message": message, "html": html},
                target={"entity_id": target},
                blocking=True,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning(
                "SMTP report dispatch failed for a configured recipient (%s)", type(err).__name__
            )
            persistent_notification.async_create(
                self.hass,
                "SMTP report could not be accepted. Check the recipient status and the native SMTP integration.",
                title=self.config["name"],
                notification_id=f"{DOMAIN}_{self.entry.entry_id}_smtp",
            )
            raise DeliveryError("smtp_error") from err

    def _render(self, kind: str) -> tuple[str, str, str]:
        self._dispatch_kind.set(kind)
        now = dt_util.utcnow().timestamp()
        telemetry, truncated = report_telemetry(self.hass, self.config, now, self.started_at)
        temperatures = []
        temperature_times: list[float] = []
        for role in ("supply_temperature", "return_temperature"):
            entity_id = self.config.get(f"{role}_entity")
            item = measurement(
                self.hass.states.get(entity_id)
                if entity_id and scoped_entity(self.hass, entity_id, self.config["device_ids"])
                else None,
                now,
                self.config["stale_after_s"],
                self.started_at,
            )
            temperatures.append(temperature_celsius(item))
            if item.observed_at is not None:
                temperature_times.append(item.observed_at)
        supply, returned = temperatures
        delta_observed = min(temperature_times) if len(temperature_times) == 2 else None
        telemetry.append(
            {
                "entity_id": None,
                "name": "Delta T (supply - return)",
                "unit": "°C",
                "value": supply - returned if supply is not None and returned is not None else None,
                "status": "ok" if supply is not None and returned is not None else "missing",
                "observed_at": iso(delta_observed),
                "freshness_seconds": now - delta_observed if delta_observed is not None else None,
            }
        )
        result = self.engine.result
        from .reasons import describe_reason

        return render_report(
            {
                "generated_at": iso(now),
                "name": self.config["name"],
                "state": public_state(result.state, result.incident_id is not None),
                "reason": describe_reason(result.reason, self.config["language"]),
                "flow": result.flow,
                "reference": result.reference,
                "minimum": self.config["min_flow_l_min"],
                "decline_pct": result.decline_pct,
                "duration_seconds": result.anomaly_duration,
                "last_cleaned": iso(result.last_cleaned),
                "thresholds": asdict(settings(self.config)),
                "telemetry": telemetry,
                "trends": list(self.trends),
                "rules": [
                    "HA last_reported is a Home Assistant report time, not a verified controller acquisition time.",
                    "Historical trend rows are not new observations. Unavailable values do not establish recovery.",
                    "Inventory truncated at 150 entities."
                    if truncated
                    else "Device-scoped inventory; only selected state fields.",
                ],
                "incident": {
                    "id": result.incident_id,
                    "severity": result.incident_severity,
                    "acknowledged": result.acked,
                    "snoozed_until": iso(result.snoozed_until),
                },
            },
            kind,
            self.config["language"],
        )

    def export(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "fingerprint": fingerprint(self.config),
            "engine": self.engine.serialize(),
            "delivery": self.delivery.export(),
            "test_delivery": self.test_delivery.export(),
            "mail_epoch": self.mail_epoch,
            "mail_key": self.mail_key,
            "mail_kind": self.mail_kind,
            "mail_incident": self.mail_incident,
            "mail_severity": self.mail_severity,
            "notice": self._notice,
            "trends": self.trends[-120:],
        }

    async def save(self) -> None:
        async with self._save_lock:
            try:
                await self.store.async_save(self.export())
                self.storage_error = None
            except OSError:
                self.storage_error = "storage_error"
                self.delivery.cancel_pending()
                self.test_delivery.cancel_pending()
                _LOGGER.error(
                    "Viessmann Guard could not persist state; outgoing reports are blocked"
                )
                self.changed()
                raise

    async def stop(self) -> None:
        self.stopped = True
        self.delivery.stop()
        self.test_delivery.stop()
        for unsubscribe in self.unsubscribers:
            unsubscribe()
        self.unsubscribers.clear()
        current = asyncio.current_task()
        pending = {
            task
            for task in (self._evaluate_task, self._delivery_task, *self._action_tasks)
            if task is not None and task is not current and not task.done()
        }
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await self.save()
