"""A bounded, persistent email outbox with recipient-specific delivery attempts.

SMTP acceptance is not proof of delivery. Persisted send intents become unknown
after restart and are not retried automatically: exactly-once delivery is not
possible across an SMTP call and an independent storage write.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from hashlib import sha256
from math import isfinite
from typing import Any

MAX_RECIPIENTS = 20
MAX_ATTEMPTS = 3
HISTORY_LIMIT = 32
RETRY_DELAYS = (60.0, 300.0)
_STATES = {"pending", "retry", "sending", "accepted", "failed", "disabled", "unknown"}
_TERMINAL = {"accepted", "unknown", "failed"}
_RECORD_FIELDS = {
    "key",
    "kind",
    "status",
    "attempts",
    "updated_at",
    "next_attempt_at",
    "accepted_at",
    "error",
}
_ERROR_CODES = {
    "disabled",
    "telemetry_not_confirmed",
    "telemetry_changed",
    "incident_changed",
    "reminders_snoozed",
    "smtp_error",
    "smtp_unavailable",
    "service_unavailable",
    "timeout",
    "storage_error",
    "render_error",
    "dispatch_error",
}


def _target_key(target: str) -> str:
    if re.fullmatch(r"notify\.[a-z0-9_]+", target):
        return target
    return sha256(target.casefold().encode()).hexdigest()


class DeliveryError(Exception):
    """An expected failure, described only by an allowlisted public error code."""

    def __init__(self, code: str = "smtp_error") -> None:
        self.code = code if isinstance(code, str) and code in _ERROR_CODES else "smtp_error"
        super().__init__(self.code)


def _time(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
        return float(value)
    return default


def _identifier(value: Any, limit: int = 256) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value if char.isprintable())[:limit]


def _stored_identifier(value: Any, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or _identifier(value, limit) != value:
        raise ValueError("Invalid delivery state identifier")
    return value


def _stored_time(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("Invalid delivery state timestamp")
    try:
        timestamp = float(value)
    except OverflowError:
        raise ValueError("Invalid delivery state timestamp") from None
    if not isfinite(timestamp):
        raise ValueError("Invalid delivery state timestamp")
    return timestamp


def _restore_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise ValueError("Invalid delivery state record")
    key = _stored_identifier(value["key"])
    kind = _stored_identifier(value["kind"], 64)
    state = value["status"]
    if not isinstance(state, str) or state not in _STATES:
        raise ValueError("Invalid delivery state status")
    attempts = value["attempts"]
    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not 0 <= attempts <= MAX_ATTEMPTS
        or (state not in {"pending", "disabled"} and attempts == 0)
        or (state in {"pending", "retry"} and attempts == MAX_ATTEMPTS)
        or (state == "failed" and attempts != MAX_ATTEMPTS)
    ):
        raise ValueError("Invalid delivery state attempt count")
    error = value["error"]
    if error is not None and (not isinstance(error, str) or error not in _ERROR_CODES):
        raise ValueError("Invalid delivery state error code")
    if state in {"pending", "retry"}:
        next_attempt_at = _stored_time(value["next_attempt_at"])
    elif value["next_attempt_at"] is None:
        next_attempt_at = None
    else:
        raise ValueError("Invalid delivery state retry timestamp")
    if state == "accepted":
        accepted_at = _stored_time(value["accepted_at"])
    elif value["accepted_at"] is None:
        accepted_at = None
    else:
        raise ValueError("Invalid delivery state acceptance timestamp")
    record: dict[str, Any] = {
        "key": key,
        "kind": kind,
        "status": "unknown" if state == "sending" else state,
        "attempts": attempts,
        "updated_at": _stored_time(value["updated_at"]),
        "next_attempt_at": next_attempt_at,
        "accepted_at": accepted_at,
        "error": error,
    }
    return record


class Delivery:
    """Keep one current event, with bounded terminal history for deduplication.

    Notify entity IDs remain addressable in exported state; direct addresses are
    hashed and exist solely in the live configuration. Adding a recipient does
    not replay an old event; queue the freshly validated event explicitly,
    including after restart. The latest 32 terminal keys per target are retained,
    not an unlimited archive of historical notifications.
    """

    def __init__(
        self,
        send: Callable[[str, str, str, str], Awaitable[None]],
        render: Callable[[str], tuple[str, str, str]],
        save: Callable[[], Awaitable[None]],
        changed: Callable[[], None],
        restored: dict | None = None,
    ) -> None:
        self._send = send
        self._render = render
        self._save = save
        self._changed = changed
        self._lock = asyncio.Lock()
        self._enabled = False
        self._stopped = False
        self._configured = False
        self._epoch = 0
        self._targets: dict[str, str] = {}
        self._target_versions: dict[str, object] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self._completed: dict[str, dict[str, dict[str, Any]]] = {}
        self._inflight: dict[str, dict[str, Any]] = {}
        self._latest: tuple[str, str] | None = None
        self._restore(restored)

    def _restore(self, restored: dict | None) -> None:
        if restored is None or restored == {}:
            return
        if not isinstance(restored, dict) or set(restored) != {
            "version",
            "enabled",
            "latest",
            "statuses",
            "completed",
        }:
            raise ValueError("Invalid delivery state schema")
        if type(restored["version"]) is not int or restored["version"] != 1:
            raise ValueError("Unsupported delivery state version")
        if not isinstance(restored["enabled"], bool):
            raise ValueError("Invalid delivery state enabled flag")
        self._enabled = restored["enabled"]
        latest = restored["latest"]
        if latest is not None:
            if not isinstance(latest, dict) or set(latest) != {"key", "kind"}:
                raise ValueError("Invalid delivery state event")
            _stored_identifier(latest["key"])
            _stored_identifier(latest["kind"], 64)
        # A persisted event is historical until the runtime revalidates and queues it.
        for field, destination in (
            ("statuses", self._records),
            ("completed", self._completed),
        ):
            source = restored.get(field)
            if not isinstance(source, dict) or len(source) > MAX_RECIPIENTS:
                raise ValueError("Invalid delivery state recipients")
            for target, value in source.items():
                if not isinstance(target, str) or not re.fullmatch(
                    r"(?:[0-9a-f]{64}|notify\.[a-z0-9_]+)", target
                ):
                    raise ValueError("Invalid delivery state recipient identifier")
                if field == "statuses":
                    destination[target] = _restore_record(value)
                else:
                    if not isinstance(value, dict) or len(value) > HISTORY_LIMIT:
                        raise ValueError("Invalid delivery state history")
                    history = {}
                    for history_key, item in value.items():
                        record = _restore_record(item)
                        if history_key != record["key"] or record["status"] not in _TERMINAL:
                            raise ValueError("Invalid delivery state history record")
                        history[history_key] = record
                    destination[target] = history
        if len(set(self._records) | set(self._completed)) > MAX_RECIPIENTS:
            raise ValueError("Invalid delivery state recipients")
        for target, record in self._records.items():
            previous = self._completed.get(target, {}).get(record["key"])
            if previous is not None and (
                previous["status"] != record["status"] or previous["attempts"] != record["attempts"]
            ):
                raise ValueError("Conflicting delivery state records")
            if record["status"] in _TERMINAL:
                self._remember(target, record)
        if not self._enabled:
            self._invalidate_pending()

    @property
    def statuses(self) -> dict[str, dict[str, Any]]:
        """Return detached statuses keyed by notify entity ID (or address hash)."""
        return deepcopy(self._records)

    def status_for(self, target: str) -> dict[str, Any]:
        """Look up a detached status by configured target, without exposing addresses."""
        target = target.strip()
        record = self._records.get(_target_key(target))
        if record is None:
            record = self._records.get(sha256(target.casefold().encode()).hexdigest())
        return deepcopy(record) if record is not None else {}

    def export(self) -> dict[str, Any]:
        """Return JSON-compatible state without addresses or exception messages."""
        completed = deepcopy(self._completed)
        for target_id, record in self._inflight.items():
            if target_id in self._targets and self._records.get(target_id) is not record:
                history = completed.setdefault(target_id, {})
                history[record["key"]] = deepcopy(record)
                while len(history) > HISTORY_LIMIT:
                    del history[next(iter(history))]
        return {
            "version": 1,
            "enabled": self._enabled,
            "latest": {"key": self._latest[0], "kind": self._latest[1]}
            if self._latest is not None
            else None,
            "statuses": self.statuses,
            "completed": completed,
        }

    def configure(self, enabled: bool, recipients: list[str]) -> None:
        """Immediately fence off old dispatchers and discard removed recipients."""
        targets: dict[str, str] = {}
        for target in recipients:
            if not isinstance(target, str):
                continue
            target = target.strip()
            if not target or any(char in target for char in "\r\n\0"):
                continue
            target_id = _target_key(target)
            targets[target_id] = target
            if len(targets) >= MAX_RECIPIENTS:
                break
        enabled = bool(enabled) and not self._stopped
        if self._configured and targets == self._targets and enabled == self._enabled:
            return

        self._epoch += 1
        previous_enabled = self._enabled
        self._enabled = enabled
        for target_id, target in targets.items():
            legacy_id = sha256(target.casefold().encode()).hexdigest()
            if legacy_id != target_id:
                for records in (self._records, self._completed):
                    if legacy_id in records:
                        records.setdefault(target_id, records.pop(legacy_id))
        for target_id in set(self._records) | set(self._completed) | set(self._targets):
            if target_id not in targets:
                self._records.pop(target_id, None)
                self._completed.pop(target_id, None)
                self._target_versions.pop(target_id, None)
                self._inflight.pop(target_id, None)
        for target_id in targets:
            self._target_versions.setdefault(target_id, object())
        self._targets = targets
        self._configured = True
        if not enabled or not previous_enabled:
            self._invalidate_pending()
        self._changed()

    def _invalidate_pending(self) -> None:
        self._latest = None
        for target_id, record in self._records.items():
            if record["status"] in {"pending", "retry", "sending"}:
                if self._inflight.get(target_id) is record:
                    continue
                record.update(status="disabled", next_attempt_at=None)

    def cancel_pending(self) -> None:
        """Cancel queued work, including work paused at the persistence barrier."""
        self._epoch += 1
        self._invalidate_pending()
        self._changed()

    def stop(self) -> None:
        """Permanently stop this instance without cancelling an SMTP call in flight."""
        self._stopped = True
        self.cancel_pending()

    def queue(self, key: str, kind: str, now: float) -> None:
        """Queue one latest event, retaining successes and exhausted/unknown sends."""
        if not self._enabled or self._stopped:
            return
        key, kind = _identifier(key), _identifier(kind, 64)
        if not key or not kind:
            raise ValueError("A nonempty event key and report kind are required")
        now = _time(now)
        event = key, kind
        changed = self._latest != event
        if changed:
            self._epoch += 1
            self._latest = event
        for target_id in self._targets:
            existing = self._records.get(target_id)
            if existing is not None and existing["key"] == key and existing["status"] != "disabled":
                continue
            completed = self._completed.get(target_id, {}).get(key)
            inflight = self._inflight.get(target_id)
            if completed is not None:
                self._records[target_id] = deepcopy(completed)
            elif inflight is not None and inflight["key"] == key:
                self._records[target_id] = inflight
            else:
                self._records[target_id] = {
                    "key": key,
                    "kind": kind,
                    "status": "pending",
                    "attempts": 0,
                    "updated_at": now,
                    "next_attempt_at": now,
                    "accepted_at": None,
                    "error": None,
                }
            changed = True
        if changed:
            self._changed()

    def _remember(self, target_id: str, record: dict[str, Any]) -> None:
        history = self._completed.setdefault(target_id, {})
        history.pop(record["key"], None)
        history[record["key"]] = deepcopy(record)
        while len(history) > HISTORY_LIMIT:
            del history[next(iter(history))]

    def _valid(self, epoch: int, target_id: str, record: dict[str, Any]) -> bool:
        return (
            not self._stopped
            and self._enabled
            and self._epoch == epoch
            and target_id in self._targets
            and self._records.get(target_id) is record
            and self._latest == (record["key"], record["kind"])
        )

    def _failure(self, record: dict[str, Any], code: str, now: float, valid: bool) -> None:
        if not valid:
            record.update(status="disabled", next_attempt_at=None, error=code, updated_at=now)
        elif record["attempts"] >= MAX_ATTEMPTS:
            record.update(status="failed", next_attempt_at=None, error=code, updated_at=now)
        else:
            record.update(
                status="retry",
                next_attempt_at=now + RETRY_DELAYS[max(0, record["attempts"] - 1)],
                error=code,
                updated_at=now,
            )

    def _release_unsent(self, target_id: str, record: dict[str, Any], now: float) -> None:
        if self._records.get(target_id) is record and record["status"] == "sending":
            record.update(
                status="pending" if self._enabled and not self._stopped else "disabled",
                attempts=max(0, record["attempts"] - 1),
                next_attempt_at=now if self._enabled and not self._stopped else None,
            )
            self._changed()

    async def _persist_result(self, record: dict[str, Any]) -> None:
        self._changed()
        try:
            await self._save()
        except OSError:
            # A saved "sending" intent is safer than replaying a possibly accepted email.
            record["error"] = "storage_error"
            self._changed()

    async def dispatch(self, now: float) -> None:
        """Attempt only due jobs; one recipient's failure never retries another."""
        async with self._lock:
            if not self._configured or not self._enabled or self._stopped:
                return
            now = _time(now)
            epoch = self._epoch
            for target_id, record in list(self._records.items()):
                if self._epoch != epoch or self._stopped or not self._enabled:
                    break
                if (
                    not self._valid(epoch, target_id, record)
                    or record["status"] not in {"pending", "retry"}
                    or _time(record["next_attempt_at"]) > now
                ):
                    continue
                target_version = self._target_versions[target_id]
                record.update(
                    status="sending",
                    attempts=record["attempts"] + 1,
                    next_attempt_at=None,
                    updated_at=now,
                    error=None,
                )
                self._changed()
                try:
                    await self._save()
                except OSError:
                    self._failure(
                        record, "storage_error", now, self._valid(epoch, target_id, record)
                    )
                    if self._records.get(target_id) is record and record["status"] == "failed":
                        self._remember(target_id, record)
                    self._changed()
                    continue
                if not self._valid(epoch, target_id, record):
                    self._release_unsent(target_id, record, now)
                    continue
                try:
                    title, message, html = self._render(record["kind"])
                except ValueError, TypeError:
                    self._failure(record, "render_error", now, True)
                    if record["status"] == "failed":
                        self._remember(target_id, record)
                    await self._persist_result(record)
                    continue
                if not self._valid(epoch, target_id, record):
                    self._release_unsent(target_id, record, now)
                    continue
                self._inflight[target_id] = record
                try:
                    await self._send(self._targets[target_id], title, message, html)
                except DeliveryError as error:
                    self._failure(record, error.code, now, self._valid(epoch, target_id, record))
                else:
                    record.update(
                        status="accepted",
                        accepted_at=now,
                        updated_at=now,
                        next_attempt_at=None,
                        error=None,
                    )
                finally:
                    # Unexpected failures and cancellation propagate after persisting the
                    # ambiguous send, so neither can later become an automatic retry.
                    if record["status"] == "sending":
                        record.update(
                            status="unknown",
                            next_attempt_at=None,
                            error="dispatch_error",
                            updated_at=now,
                        )
                    if self._inflight.get(target_id) is record:
                        self._inflight.pop(target_id, None)
                    if self._target_versions.get(target_id) is target_version:
                        if record["status"] in _TERMINAL:
                            self._remember(target_id, record)
                        await self._persist_result(record)
