"""Explicit observation and incident-management actions, never equipment controls."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GuardConfigEntry
from .entity import GuardEntity

ACTIONS = ("acknowledge", "snooze", "record_cleaning", "confirm_calibration", "test_email")


async def async_setup_entry(
    hass: HomeAssistant, entry: GuardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([GuardButton(entry.runtime_data, key) for key in ACTIONS])


class GuardButton(GuardEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        # The entity's label states the clean/healthy confirmation; dashboard adds a dialog.
        key = self._attr_translation_key
        assert key is not None
        await self.runtime.action(key, confirmed=True)
