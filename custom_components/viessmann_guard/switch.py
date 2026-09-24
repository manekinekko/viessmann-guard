"""The same persisted email setting as the options flow."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GuardConfigEntry
from .entity import GuardEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: GuardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([EmailSwitch(entry.runtime_data, "emails_enabled")])


class EmailSwitch(GuardEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:email-outline"

    @property
    def is_on(self) -> bool:
        return self.runtime.config["emails_enabled"]

    async def async_turn_on(self, **kwargs) -> None:
        await self.runtime.set_emails(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.runtime.set_emails(False)
