"""Entity base scoped to a single monitored installation."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .runtime import GuardRuntime


class GuardEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: GuardRuntime, key: str) -> None:
        self.runtime = runtime
        self.entity_key = key
        self._attr_unique_id = f"{runtime.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            name=runtime.config["name"],
            manufacturer="Viessmann Guard community",
            model="Read-only flow monitor",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def suggested_object_id(self) -> str:
        """Keep example IDs independent of translated action labels."""
        return self.entity_key

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.runtime.subscribe(self.async_write_ha_state))
