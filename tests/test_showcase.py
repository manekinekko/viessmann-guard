"""A reproducible showcase using synthetic entities in a real isolated HA instance."""

from datetime import timedelta

from test_integration import reports, settle, setup_guard


async def test_mocked_home_assistant_showcase(hass, source_config, freezer):
    config = {
        **source_config,
        "calibration_samples": 3,
        "calibration_duration_s": 60,
        "relative_persistence_s": 30,
    }
    entry = await setup_guard(hass, config)
    runtime = entry.runtime_data
    print("\nSYNTHETIC DEMO ONLY. Minimum 8 L/min is not a manufacturer recommendation.")

    def display(stage):
        result = runtime.engine.result
        print(
            f"{stage}: state={result.state}, reason={result.reason}, "
            f"flow={result.flow}, reference={result.reference}, "
            f"incident={bool(result.incident_id)}, emails={runtime.config['emails_enabled']}"
        )

    display("Start")
    for _ in range(2):
        await reports(hass, config, freezer)
        await settle(runtime)
    await runtime.action("confirm_calibration", confirmed=True)
    for _ in range(3):
        await reports(hass, config, freezer, seconds=30)
        await settle(runtime)
    display("Healthy calibration")
    assert runtime.engine.result.reference == 12

    await reports(hass, config, freezer, flow="9")
    await settle(runtime)
    await reports(hass, config, freezer, seconds=31, flow="9")
    await settle(runtime)
    display("Relative decline")
    assert runtime.engine.result.state == "watch"

    await reports(hass, config, freezer, flow="4")
    await settle(runtime)
    await reports(hass, config, freezer, seconds=31, flow="4")
    await settle(runtime)
    display("Below synthetic minimum")
    assert runtime.engine.result.state == "urgent"
    incident_id = runtime.engine.result.incident_id

    await runtime.action("record_cleaning")
    await runtime.action("acknowledge")
    await runtime.action("snooze")
    display("Intervention recorded, not resolved")
    assert runtime.engine.result.incident_id == incident_id
    assert runtime.engine.result.reference == 12

    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds)
        await settle(runtime)
    display("Stable recovery")
    assert runtime.engine.result.incident_id is None

    freezer.tick(timedelta(seconds=181))
    await runtime.evaluate()
    display("No fresh telemetry")
    assert runtime.engine.result.state == "diagnostic_unavailable"
    assert not runtime.config["emails_enabled"]
    assert runtime.delivery.statuses == {}
    assert not hass.services.has_service("smtp", "send_message")
    assert await hass.config_entries.async_unload(entry.entry_id)
