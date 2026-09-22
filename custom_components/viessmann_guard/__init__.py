"""Viessmann Guard: a read-only observer of existing Home Assistant entities."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .runtime import GuardRuntime

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
type GuardConfigEntry = ConfigEntry[GuardRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def handle_action(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_unavailable"
            )
        await entry.runtime_data.action(
            call.service, call.data.get("hours", 24), call.data.get("confirmed", False)
        )

    for action in ("acknowledge", "snooze", "record_cleaning", "confirm_calibration", "test_email"):
        fields: dict[Any, Any] = {vol.Required("entry_id"): cv.string}
        if action == "snooze":
            fields[vol.Optional("hours", default=24)] = vol.All(
                vol.Coerce(float), vol.Range(min=1, max=168)
            )
        if action == "confirm_calibration":
            fields[vol.Required("confirmed")] = vol.All(cv.boolean, vol.Equal(True))
        hass.services.async_register(DOMAIN, action, handle_action, schema=vol.Schema(fields))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GuardConfigEntry) -> bool:
    runtime = GuardRuntime(hass, entry)
    try:
        await runtime.start()
    except (ValueError, OSError) as err:
        _LOGGER.error(
            "Viessmann Guard storage/configuration could not be loaded (%s)", type(err).__name__
        )
        raise ConfigEntryError("Viessmann Guard storage or configuration is invalid") from err
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: GuardConfigEntry) -> None:
    await entry.runtime_data.apply_options()


async def async_unload_entry(hass: HomeAssistant, entry: GuardConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
        return True
    return False


async def async_remove_entry(hass: HomeAssistant, entry: GuardConfigEntry) -> None:
    from .storage import GuardStore

    await GuardStore(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def async_migrate_entry(hass: HomeAssistant, entry: GuardConfigEntry) -> bool:
    if entry.version != 1:
        _LOGGER.error("Unsupported Viessmann Guard configuration version: %s", entry.version)
        return False
    return True
