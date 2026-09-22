"""Recipient-level lifecycle, persistence and race coverage for the pure outbox."""

import asyncio
import json
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.viessmann_guard.delivery import (
    HISTORY_LIMIT,
    MAX_RECIPIENTS,
    Delivery,
    DeliveryError,
)

FIRST = "first@example.test"
SECOND = "second@example.test"
THIRD = "third@example.test"


def target_id(target):
    return sha256(target.casefold().encode()).hexdigest()


def status(delivery, target=FIRST):
    return delivery.statuses[target_id(target)]


def make_delivery(*, send=None, render=None, save=None, restored=None):
    return Delivery(
        send=send or AsyncMock(),
        render=render or Mock(return_value=("Title", "Plain text", "<p>HTML</p>")),
        save=save or AsyncMock(),
        changed=Mock(),
        restored=restored,
    )


@pytest.mark.asyncio
async def test_success_is_persisted_before_dispatch_and_not_sent_twice():
    saved = []
    send = AsyncMock()
    delivery = None

    async def save():
        saved.append(delivery.export())

    async def send_checked(*args):
        assert next(iter(saved[-1]["statuses"].values()))["status"] == "sending"
        await send(*args)

    delivery = make_delivery(send=send_checked, save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("incident-1", "urgent", 10)
    await delivery.dispatch(10)
    delivery.configure(True, [FIRST])
    delivery.queue("incident-1", "urgent", 20)
    await delivery.dispatch(20)
    assert status(delivery)["status"] == "accepted"
    assert status(delivery)["attempts"] == 1
    assert status(delivery)["accepted_at"] == 10
    assert next(iter(saved[-1]["statuses"].values()))["status"] == "accepted"
    send.assert_awaited_once_with(FIRST, "Title", "Plain text", "<p>HTML</p>")


@pytest.mark.asyncio
async def test_notify_entity_targets_are_directly_addressable_without_raw_email_addresses():
    targets = ["notify.synthetic_smtp_technician", "notify.synthetic_smtp_owner"]
    send = AsyncMock()
    delivery = make_delivery(send=send)
    delivery.configure(True, targets)
    delivery.queue("event", "test", 0)
    await delivery.dispatch(0)
    assert set(delivery.statuses) == set(targets)
    assert all(delivery.statuses[target]["status"] == "accepted" for target in targets)
    assert delivery.status_for(targets[0]) == delivery.statuses[targets[0]]
    delivery.status_for(targets[0]).clear()
    assert delivery.statuses[targets[0]]["status"] == "accepted"
    assert delivery.status_for("notify.unconfigured") == {}
    assert [call.args[0] for call in send.await_args_list] == targets
    assert "@" not in json.dumps(delivery.export())
    restored_send = AsyncMock()
    restored = make_delivery(send=restored_send, restored=delivery.export())
    restored.configure(True, targets)
    restored.queue("event", "test", 15)
    await restored.dispatch(15)
    assert set(restored.statuses) == set(targets)
    restored_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_hashed_notify_entity_keys_migrate_without_resending_acceptance():
    target = "notify.synthetic_smtp_technician"
    delivery = make_delivery()
    delivery.configure(True, [target])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    exported = delivery.export()
    for field in ("statuses", "completed"):
        exported[field][target_id(target)] = exported[field].pop(target)
    send = AsyncMock()
    restored = make_delivery(send=send, restored=exported)
    restored.configure(True, [target])
    restored.queue("event", "urgent", 15)
    await restored.dispatch(15)
    assert restored.statuses[target]["status"] == "accepted"
    assert target_id(target) not in restored.statuses
    assert target_id(target) not in restored.export()["completed"]
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_separate_manual_test_queue_preserves_incident_retry_and_entity_status_keys():
    target = "notify.synthetic_smtp_technician"
    send = AsyncMock(side_effect=[DeliveryError(), None, None])
    incident = make_delivery(send=send, render=lambda kind: (kind, kind, kind))
    manual = make_delivery(send=send, render=lambda kind: (kind, kind, kind))
    for delivery in (incident, manual):
        delivery.configure(True, [target])
    incident.queue("incident-1", "urgent", 0)
    await incident.dispatch(0)
    retry = incident.statuses[target]
    assert retry["status"] == "retry"
    manual.queue("manual-test-1", "test", 15)
    await manual.dispatch(15)
    assert manual.statuses[target]["status"] == "accepted"
    assert incident.statuses[target] == retry
    assert incident.statuses[target]["next_attempt_at"] == 60
    assert manual.export()["statuses"][target]["key"] == "manual-test-1"
    assert incident.export()["statuses"][target]["key"] == "incident-1"
    await incident.dispatch(60)
    assert incident.statuses[target]["status"] == "accepted"
    assert [call.args[1] for call in send.await_args_list] == ["urgent", "test", "urgent"]


@pytest.mark.asyncio
async def test_retries_are_independent_and_bounded():
    attempts = Counter()

    async def send(target, *_):
        attempts[target] += 1
        if target != FIRST:
            raise DeliveryError("smtp_error")

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("incident-1", "urgent", 100)
    await delivery.dispatch(100)
    assert status(delivery, FIRST)["status"] == "accepted"
    assert status(delivery, SECOND)["status"] == "retry"
    assert status(delivery, SECOND)["next_attempt_at"] == 160
    await delivery.dispatch(159)
    assert attempts == {FIRST: 1, SECOND: 1}
    await delivery.dispatch(160)
    assert status(delivery, SECOND)["next_attempt_at"] == 460
    await delivery.dispatch(460)
    assert status(delivery, SECOND)["status"] == "failed"
    assert status(delivery, SECOND)["attempts"] == 3
    assert status(delivery, SECOND)["error"] == "smtp_error"
    delivery.queue("incident-1", "urgent", 900)
    await delivery.dispatch(900)
    assert attempts == {FIRST: 1, SECOND: 3}


@pytest.mark.asyncio
async def test_repeated_evaluations_preserve_same_key_retry_deadlines_and_acceptance():
    send = AsyncMock(side_effect=[DeliveryError(), DeliveryError(), None])
    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST])
    for now in range(0, 391, 15):
        delivery.queue("active-incident", "urgent", now)
        await delivery.dispatch(now)
        record = status(delivery)
        if now < 60:
            assert record["attempts"] == 1
            assert record["next_attempt_at"] == 60
        elif now < 360:
            assert record["attempts"] == 2
            assert record["next_attempt_at"] == 360
        else:
            assert record["attempts"] == 3
            assert record["status"] == "accepted"
            assert record["next_attempt_at"] is None
    assert send.await_count == 3


@pytest.mark.asyncio
async def test_new_key_supersedes_old_retry_without_explicit_cancellation():
    send = AsyncMock(side_effect=[DeliveryError(), None])
    delivery = make_delivery(send=send, render=lambda kind: (kind, kind, kind))
    delivery.configure(True, [FIRST])
    delivery.queue("urgent-event", "urgent", 0)
    await delivery.dispatch(0)
    assert status(delivery)["status"] == "retry"
    delivery.queue("recovery-event", "recovery", 15)
    await delivery.dispatch(15)
    await delivery.dispatch(60)
    assert [call.args[1] for call in send.await_args_list] == ["urgent", "recovery"]
    assert status(delivery)["key"] == "recovery-event"
    assert status(delivery)["attempts"] == 1
    assert status(delivery)["status"] == "accepted"


@pytest.mark.asyncio
async def test_first_recipient_failure_does_not_block_second():
    send = AsyncMock(side_effect=[DeliveryError("smtp_error"), None])
    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    assert status(delivery, FIRST)["status"] == "retry"
    assert status(delivery, SECOND)["status"] == "accepted"


@pytest.mark.asyncio
async def test_off_during_first_send_stops_other_recipients():
    calls = []

    async def send(target, *_):
        calls.append(target)
        delivery.configure(False, [FIRST, SECOND])

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("incident-1", "urgent", 0)
    await delivery.dispatch(0)
    await delivery.dispatch(3600)
    assert calls == [FIRST]
    assert status(delivery, FIRST)["status"] == "accepted"
    assert status(delivery, SECOND)["status"] == "disabled"


@pytest.mark.asyncio
async def test_disable_then_reenable_cannot_revive_inflight_dispatch():
    calls = []

    async def send(target, *_):
        calls.append(target)
        delivery.configure(False, [FIRST, SECOND])
        delivery.configure(True, [FIRST, SECOND])

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("old-incident", "urgent", 0)
    await delivery.dispatch(0)
    await delivery.dispatch(1000)
    assert calls == [FIRST]
    assert status(delivery, SECOND)["status"] == "disabled"


@pytest.mark.asyncio
async def test_new_job_is_not_overwritten_by_old_inflight_acceptance():
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def send(target, title, *_):
        calls.append((target, title))
        if len(calls) == 1:
            started.set()
            await finish.wait()

    delivery = make_delivery(send=send, render=lambda kind: (kind, kind, kind))
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("incident-1", "urgent", 0)
    task = asyncio.create_task(delivery.dispatch(0))
    await started.wait()
    delivery.configure(False, [FIRST, SECOND])
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("revalidated-incident", "reminder", 1)
    finish.set()
    await task
    assert status(delivery, FIRST)["key"] == "revalidated-incident"
    assert status(delivery, FIRST)["status"] == "pending"
    assert delivery.export()["completed"][target_id(FIRST)]["incident-1"]["status"] == "accepted"
    assert calls == [(FIRST, "urgent")]
    await delivery.dispatch(1)
    assert calls == [(FIRST, "urgent"), (FIRST, "reminder"), (SECOND, "reminder")]


@pytest.mark.asyncio
async def test_old_inflight_intent_survives_new_job_snapshot():
    started, finish = asyncio.Event(), asyncio.Event()

    async def send(*_):
        started.set()
        await finish.wait()

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST])
    delivery.queue("old", "urgent", 0)
    task = asyncio.create_task(delivery.dispatch(0))
    await started.wait()
    delivery.queue("new", "recovery", 1)
    saved = delivery.export()
    assert saved["completed"][target_id(FIRST)]["old"]["status"] == "sending"
    finish.set()
    await task

    send_after_restart = AsyncMock()
    restored = make_delivery(send=send_after_restart, restored=saved)
    restored.configure(True, [FIRST])
    restored.queue("old", "urgent", 2)
    await restored.dispatch(2)
    send_after_restart.assert_not_awaited()
    assert status(restored)["status"] == "unknown"


@pytest.mark.asyncio
async def test_requeuing_an_inflight_key_after_another_event_does_not_duplicate():
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def send(target, *_):
        calls.append(target)
        started.set()
        await finish.wait()

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST])
    delivery.queue("old", "urgent", 0)
    task = asyncio.create_task(delivery.dispatch(0))
    await started.wait()
    delivery.queue("new", "report", 1)
    delivery.queue("old", "urgent", 2)
    finish.set()
    await task
    await delivery.dispatch(2)
    assert calls == [FIRST]
    assert status(delivery)["key"] == "old"
    assert status(delivery)["status"] == "accepted"


@pytest.mark.asyncio
async def test_removing_recipient_purges_state_and_addition_has_no_implicit_backlog():
    send = AsyncMock()
    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    delivery.configure(True, [FIRST, THIRD])
    assert target_id(SECOND) not in delivery.statuses
    assert target_id(THIRD) not in delivery.statuses
    await delivery.dispatch(0)
    assert [call.args[0] for call in send.await_args_list] == [FIRST]
    delivery.queue("event", "urgent", 1)
    await delivery.dispatch(1)
    assert [call.args[0] for call in send.await_args_list] == [FIRST, THIRD]
    assert target_id(SECOND) not in json.dumps(delivery.export())


@pytest.mark.asyncio
async def test_removal_during_send_does_not_reintroduce_removed_state():
    async def send(*_):
        delivery.configure(True, [SECOND])

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    assert target_id(FIRST) not in delivery.statuses
    assert target_id(FIRST) not in delivery.export()["completed"]
    assert status(delivery, SECOND)["status"] == "pending"


@pytest.mark.asyncio
async def test_removed_then_added_inflight_target_has_new_identity_generation():
    async def send(*_):
        delivery.configure(True, [])
        delivery.configure(True, [FIRST])
        delivery.queue("new", "recovery", 1)

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST])
    delivery.queue("old", "urgent", 0)
    await delivery.dispatch(0)
    assert status(delivery)["key"] == "new"
    assert status(delivery)["status"] == "pending"
    assert not delivery.export()["completed"]


@pytest.mark.asyncio
async def test_restored_acceptance_deduplicates_after_configuration():
    delivery = make_delivery()
    delivery.configure(True, [FIRST])
    delivery.queue("incident-1", "urgent", 10)
    await delivery.dispatch(10)
    send = AsyncMock()
    restored = make_delivery(send=send, restored=delivery.export())
    restored.configure(True, [FIRST])
    restored.queue("incident-1", "urgent", 20)
    await restored.dispatch(20)
    send.assert_not_awaited()
    assert status(restored)["status"] == "accepted"


@pytest.mark.asyncio
async def test_restored_sending_is_unknown_and_never_retried():
    snapshots = []

    async def save():
        snapshots.append(delivery.export())

    delivery = make_delivery(save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("incident-1", "urgent", 0)
    await delivery.dispatch(0)
    send = AsyncMock()
    restored = make_delivery(send=send, restored=snapshots[0])
    restored.configure(True, [FIRST])
    restored.queue("incident-1", "urgent", 500)
    await restored.dispatch(500)
    assert status(restored)["status"] == "unknown"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_revalidated_restored_retry_keeps_attempt_count_and_deadline():
    original = make_delivery(send=AsyncMock(side_effect=DeliveryError()))
    original.configure(True, [FIRST])
    original.queue("event", "urgent", 100)
    await original.dispatch(100)
    send = AsyncMock()
    restored = make_delivery(send=send, restored=original.export())
    restored.configure(True, [FIRST])
    restored.queue("event", "urgent", 159)
    await restored.dispatch(159)
    send.assert_not_awaited()
    await restored.dispatch(160)
    send.assert_awaited_once()
    assert status(restored)["attempts"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("with_retry", [False, True])
async def test_restored_pending_or_retry_is_not_replayed_without_revalidation(with_retry):
    original = make_delivery(send=AsyncMock(side_effect=DeliveryError()))
    original.configure(True, [FIRST])
    original.queue("event", "urgent", 0)
    if with_retry:
        await original.dispatch(0)
    send = AsyncMock()
    restored = make_delivery(send=send, restored=original.export())
    restored.configure(True, [FIRST])
    await restored.dispatch(1000)
    send.assert_not_awaited()
    assert status(restored)["status"] == ("retry" if with_retry else "pending")
    restored.queue("fresh-event", "report", 1001)
    await restored.dispatch(1001)
    send.assert_awaited_once()
    assert status(restored)["key"] == "fresh-event"
    assert status(restored)["attempts"] == 1


@pytest.mark.asyncio
async def test_off_queue_does_nothing_and_enabling_does_not_replay():
    send, render = AsyncMock(), Mock(return_value=("Title", "Text", "<p>Text</p>"))
    delivery = make_delivery(send=send, render=render)
    delivery.configure(False, [FIRST])
    for kind in ("test", "report", "urgent"):
        delivery.queue(kind, kind, 0)
    await delivery.dispatch(0)
    assert delivery.statuses == {}
    delivery.configure(True, [FIRST])
    await delivery.dispatch(100)
    send.assert_not_awaited()
    render.assert_not_called()


@pytest.mark.asyncio
async def test_disable_cancels_retry_and_preserves_prior_success():
    delivery = make_delivery(send=AsyncMock(side_effect=[None, DeliveryError()]))
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    delivery.configure(False, [FIRST, SECOND])
    delivery.configure(True, [FIRST, SECOND])
    await delivery.dispatch(1000)
    assert status(delivery, FIRST)["status"] == "accepted"
    assert status(delivery, SECOND)["status"] == "disabled"


@pytest.mark.asyncio
async def test_save_failure_prevents_send_and_is_bounded():
    send = AsyncMock()
    save = AsyncMock(side_effect=OSError("secret password first@example.test"))
    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    await delivery.dispatch(60)
    await delivery.dispatch(360)
    await delivery.dispatch(1000)
    assert status(delivery)["status"] == "failed"
    assert status(delivery)["error"] == "storage_error"
    assert status(delivery)["attempts"] == 3
    assert save.await_count == 3
    send.assert_not_awaited()
    exported = json.dumps(delivery.export())
    assert "secret" not in exported
    assert FIRST not in exported


@pytest.mark.asyncio
async def test_save_barrier_is_awaited_and_disable_during_save_prevents_call():
    saving, finish = asyncio.Event(), asyncio.Event()
    send = AsyncMock()

    async def save():
        saving.set()
        await finish.wait()

    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    task = asyncio.create_task(delivery.dispatch(0))
    await saving.wait()
    send.assert_not_awaited()
    delivery.configure(False, [FIRST])
    finish.set()
    await task
    send.assert_not_awaited()
    assert status(delivery)["status"] == "disabled"


@pytest.mark.asyncio
async def test_disabling_at_second_recipient_save_barrier_preserves_only_first_acceptance():
    saving_second, finish = asyncio.Event(), asyncio.Event()
    send = AsyncMock()
    saves = 0

    async def save():
        nonlocal saves
        saves += 1
        if saves == 3:
            saving_second.set()
            await finish.wait()

    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    task = asyncio.create_task(delivery.dispatch(0))
    await saving_second.wait()
    delivery.configure(False, [FIRST, SECOND])
    finish.set()
    await task
    assert [call.args[0] for call in send.await_args_list] == [FIRST]
    assert status(delivery, FIRST)["status"] == "accepted"
    assert status(delivery, SECOND)["status"] == "disabled"


@pytest.mark.asyncio
async def test_recipient_change_during_save_does_not_leave_unsent_intent_stuck():
    saves = 0
    send = AsyncMock()

    async def save():
        nonlocal saves
        saves += 1
        if saves == 1:
            delivery.configure(True, [FIRST, THIRD])

    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    send.assert_not_awaited()
    assert status(delivery)["status"] == "pending"
    await delivery.dispatch(1)
    send.assert_awaited_once()
    assert status(delivery)["attempts"] == 1


@pytest.mark.asyncio
async def test_accepted_result_save_failure_does_not_retry_acceptance():
    send = AsyncMock()
    save = AsyncMock(side_effect=[None, OSError("secret")])
    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    await delivery.dispatch(1000)
    send.assert_awaited_once()
    assert status(delivery)["status"] == "accepted"
    assert status(delivery)["error"] == "storage_error"


@pytest.mark.asyncio
async def test_each_actual_attempt_renders_a_fresh_snapshot():
    render = Mock(side_effect=[("first", "one", "<p>one</p>"), ("second", "two", "<p>two</p>")])
    send = AsyncMock(side_effect=[DeliveryError(), None])
    delivery = make_delivery(send=send, render=render)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    assert render.call_count == 0
    await delivery.dispatch(0)
    await delivery.dispatch(60)
    assert [call.args[1] for call in send.await_args_list] == ["first", "second"]
    assert render.call_count == 2


@pytest.mark.asyncio
async def test_expected_error_messages_are_never_persisted_or_exposed():
    error = DeliveryError("SMTP rejected recipient first@example.test, password=hunter2")
    assert str(error) == "smtp_error"
    delivery = make_delivery(send=AsyncMock(side_effect=error))
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    exported = json.dumps(delivery.export())
    assert "hunter2" not in exported
    assert FIRST not in exported
    assert status(delivery)["error"] == "smtp_error"


@pytest.mark.asyncio
async def test_unexpected_dispatch_failure_persists_unknown_then_propagates():
    snapshots = []

    async def save():
        snapshots.append(delivery.export())

    send = AsyncMock(side_effect=[RuntimeError("private@example.test credentials"), None])
    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    with pytest.raises(RuntimeError):
        await delivery.dispatch(0)
    assert snapshots[-1]["statuses"][target_id(FIRST)]["status"] == "unknown"
    assert snapshots[-1]["completed"][target_id(FIRST)]["event"]["status"] == "unknown"
    assert send.await_count == 1
    await delivery.dispatch(1000)
    assert status(delivery, FIRST)["status"] == "unknown"
    assert status(delivery, FIRST)["error"] == "dispatch_error"
    assert status(delivery, SECOND)["status"] == "accepted"
    assert send.await_count == 2
    assert "private" not in json.dumps(delivery.export())


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [ValueError, TypeError])
async def test_render_failure_is_bounded_and_sanitized(error_type):
    delivery = make_delivery(render=Mock(side_effect=error_type("secret")))
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    for now in (0, 60, 360, 1000):
        await delivery.dispatch(now)
    assert status(delivery)["status"] == "failed"
    assert status(delivery)["attempts"] == 3
    assert status(delivery)["error"] == "render_error"
    assert "secret" not in json.dumps(delivery.export())


@pytest.mark.asyncio
async def test_unexpected_save_failure_propagates_without_dispatch():
    send = AsyncMock()
    delivery = make_delivery(send=send, save=AsyncMock(side_effect=RuntimeError("unexpected")))
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    with pytest.raises(RuntimeError):
        await delivery.dispatch(0)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_render_failure_propagates_without_dispatch():
    send = AsyncMock()
    delivery = make_delivery(send=send, render=Mock(side_effect=RuntimeError("unexpected")))
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    with pytest.raises(RuntimeError):
        await delivery.dispatch(0)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_result_save_failure_propagates_without_retrying_acceptance():
    send = AsyncMock()
    save = AsyncMock(side_effect=[None, RuntimeError("unexpected")])
    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    with pytest.raises(RuntimeError):
        await delivery.dispatch(0)
    assert status(delivery)["status"] == "accepted"
    await delivery.dispatch(1000)
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_dispatch_is_serial_and_does_not_duplicate():
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def send(target, *_):
        calls.append(target)
        started.set()
        await finish.wait()

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    first = asyncio.create_task(delivery.dispatch(0))
    await started.wait()
    second = asyncio.create_task(delivery.dispatch(0))
    await asyncio.sleep(0)
    assert calls == [FIRST]
    finish.set()
    await asyncio.gather(first, second)
    assert calls == [FIRST]


@pytest.mark.asyncio
async def test_cancellation_propagates_and_does_not_retry_ambiguous_send():
    started = asyncio.Event()
    snapshots = []

    async def save():
        snapshots.append(delivery.export())

    async def send(*_):
        started.set()
        await asyncio.Event().wait()

    delivery = make_delivery(send=send, save=save)
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    task = asyncio.create_task(delivery.dispatch(0))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert status(delivery)["status"] == "unknown"
    assert snapshots[-1]["statuses"][target_id(FIRST)]["status"] == "unknown"
    delivery.cancel_pending()
    delivery.queue("event", "urgent", 1000)
    await delivery.dispatch(1000)
    assert status(delivery)["status"] == "unknown"
    restarted = make_delivery(restored=delivery.export())
    assert status(restarted)["status"] == "unknown"


@pytest.mark.asyncio
async def test_stop_fences_pending_and_future_dispatches():
    calls = []

    async def send(target, *_):
        calls.append(target)
        delivery.stop()

    delivery = make_delivery(send=send)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("event", "urgent", 0)
    await delivery.dispatch(0)
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("new", "test", 1)
    await delivery.dispatch(1000)
    assert calls == [FIRST]
    assert status(delivery, FIRST)["status"] == "accepted"
    assert status(delivery, SECOND)["status"] == "disabled"


@pytest.mark.asyncio
async def test_latest_event_replaces_pending_urgent_with_recovery():
    send = AsyncMock()
    delivery = make_delivery(send=send, render=lambda kind: (kind, kind, kind))
    delivery.configure(True, [FIRST, SECOND])
    delivery.queue("urgent-event", "urgent", 0)
    delivery.cancel_pending()
    delivery.queue("recovery-event", "recovery", 1)
    await delivery.dispatch(1)
    assert [call.args[1] for call in send.await_args_list] == ["recovery", "recovery"]
    assert len(delivery.statuses) == 2


@pytest.mark.asyncio
async def test_state_and_history_are_bounded_and_snapshots_are_detached():
    delivery = make_delivery()
    recipients = [f"target{index}@example.test" for index in range(MAX_RECIPIENTS + 3)]
    delivery.configure(True, recipients)
    for index in range(HISTORY_LIMIT + 3):
        delivery.queue(f"event-{index}", "report", index)
        await delivery.dispatch(index)
    exported = delivery.export()
    assert len(exported["statuses"]) == MAX_RECIPIENTS
    assert all(len(history) == HISTORY_LIMIT for history in exported["completed"].values())
    assert len(json.dumps(exported)) < 300_000
    exported["statuses"].clear()
    exported["completed"].clear()
    delivery.statuses.clear()
    assert len(delivery.statuses) == MAX_RECIPIENTS


def pending_snapshot():
    delivery = make_delivery()
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    return delivery.export()


@pytest.mark.parametrize("restored", [[], "private@example.test", 1, {"version": 1}])
def test_nonempty_unknown_or_nondict_restore_is_rejected(restored):
    with pytest.raises(ValueError) as error:
        make_delivery(restored=restored)
    assert "private@example.test" not in str(error.value)


@pytest.mark.parametrize("version", [None, False, True, 0, 2, 1.0, "1"])
def test_unsupported_restored_version_is_rejected(version):
    restored = pending_snapshot()
    restored["version"] = version
    with pytest.raises(ValueError, match="version"):
        make_delivery(restored=restored)


@pytest.mark.parametrize(
    "field,value",
    [
        ("enabled", "true"),
        ("statuses", []),
        ("completed", []),
        ("latest", []),
        ("latest", {"key": "event"}),
        ("latest", {"key": "", "kind": "urgent"}),
    ],
)
def test_malformed_top_level_restore_is_rejected(field, value):
    restored = pending_snapshot()
    restored[field] = value
    with pytest.raises(ValueError):
        make_delivery(restored=restored)


@pytest.mark.parametrize(
    "changes",
    [
        {"key": ""},
        {"key": "private\n@example.test"},
        {"key": "x" * 257},
        {"kind": ""},
        {"kind": "x" * 65},
        {"status": []},
        {"status": "invalid"},
        {"attempts": "1"},
        {"attempts": None},
        {"attempts": True},
        {"attempts": -1},
        {"attempts": 4},
        {"attempts": 3},
        {"error": []},
        {"error": "private@example.test"},
        {"updated_at": None},
        {"updated_at": float("nan")},
        {"updated_at": float("inf")},
        {"updated_at": 10**400},
        {"next_attempt_at": None},
        {"next_attempt_at": "tomorrow"},
        {"accepted_at": 10},
        {"status": "accepted", "attempts": 1, "next_attempt_at": None},
        {"status": "failed", "attempts": 1, "next_attempt_at": None},
        {"status": "sending", "attempts": 0, "next_attempt_at": None},
        {"raw_attributes": {"password": "private-secret"}},
    ],
)
def test_malformed_record_restore_is_rejected_without_clamping_or_reset(changes):
    restored = pending_snapshot()
    record = restored["statuses"][target_id(FIRST)]
    record.update(changes)
    with pytest.raises(ValueError) as error:
        make_delivery(restored=restored)
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "field",
    ["key", "kind", "status", "attempts", "updated_at", "next_attempt_at", "accepted_at", "error"],
)
def test_missing_record_fields_are_rejected(field):
    restored = pending_snapshot()
    del restored["statuses"][target_id(FIRST)][field]
    with pytest.raises(ValueError):
        make_delivery(restored=restored)


def test_raw_address_and_excess_recipient_restore_are_rejected_not_truncated():
    restored = pending_snapshot()
    record = restored["statuses"].pop(target_id(FIRST))
    restored["statuses"][FIRST] = record
    with pytest.raises(ValueError):
        make_delivery(restored=restored)
    restored["statuses"] = {
        f"notify.target_{index}": deepcopy(record) for index in range(MAX_RECIPIENTS + 1)
    }
    with pytest.raises(ValueError):
        make_delivery(restored=restored)


@pytest.mark.asyncio
async def test_malformed_history_is_rejected_without_losing_accepted_deduplication():
    original = make_delivery()
    original.configure(True, [FIRST])
    original.queue("event", "urgent", 0)
    await original.dispatch(0)
    exported = original.export()
    target = target_id(FIRST)
    for invalid_history in ([], {"wrong-key": deepcopy(exported["statuses"][target])}):
        restored = deepcopy(exported)
        restored["completed"][target] = invalid_history
        with pytest.raises(ValueError):
            make_delivery(restored=restored)
    restored = deepcopy(exported)
    restored["completed"][target] = {
        f"key-{index}": {**exported["statuses"][target], "key": f"key-{index}"}
        for index in range(HISTORY_LIMIT + 1)
    }
    with pytest.raises(ValueError):
        make_delivery(restored=restored)
    restored = deepcopy(exported)
    restored["statuses"][target].update(
        status="pending", attempts=0, accepted_at=None, next_attempt_at=0
    )
    with pytest.raises(ValueError, match="Conflicting"):
        make_delivery(restored=restored)


def test_empty_restore_is_supported_and_status_lookup_accepts_direct_address():
    assert make_delivery(restored={}).statuses == {}
    delivery = make_delivery()
    delivery.configure(True, [FIRST])
    delivery.queue("event", "urgent", 0)
    assert delivery.status_for(FIRST)["status"] == "pending"
    assert FIRST not in json.dumps(delivery.export())
