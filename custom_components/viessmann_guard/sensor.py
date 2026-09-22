"""Native monitoring and diagnostic sensors."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GuardConfigEntry
from .entity import GuardEntity
from .reasons import REASON_CODES, describe_reason
from .runtime import GuardRuntime

KEYS = (
    "state",
    "reason",
    "current_flow",
    "reference_flow",
    "minimum_flow",
    "decline",
    "telemetry_updated",
    "last_cleaned",
    "email_status",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GuardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [GuardSensor(runtime, key) for key in KEYS]
        + [RecipientSensor(runtime, recipient) for recipient in runtime.config["recipients"]]
    )


class GuardSensor(GuardEntity, SensorEntity):
    def __init__(self, runtime: GuardRuntime, key: str) -> None:
        super().__init__(runtime, key)
        self.key = key
        if key.endswith("_flow"):
            self._attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
            self._attr_native_unit_of_measurement = "L/min"
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "decline":
            self._attr_native_unit_of_measurement = "%"
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key in ("telemetry_updated", "last_cleaned"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key == "state":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["normal", "learning", "watch", "urgent", "diagnostic_unavailable"]
        elif key == "reason":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(REASON_CODES)
        if key in ("email_status", "reason"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        result = self.runtime.engine.result
        if self.key == "state":
            return self.runtime.diagnostic_state
        if self.key == "reason":
            return result.reason
        if self.key == "current_flow":
            return self.runtime.observed_flow()
        if self.key == "reference_flow":
            return result.reference
        if self.key == "minimum_flow":
            return self.runtime.config["min_flow_l_min"]
        if self.key == "decline":
            return round(result.decline_pct, 1) if result.decline_pct is not None else None
        if self.key == "email_status":
            if self.runtime.storage_error:
                return self.runtime.storage_error
            if not self.runtime.config["emails_enabled"]:
                return "disabled"
            states = {
                item.get("status")
                for queue in (self.runtime.delivery, self.runtime.test_delivery)
                for item in queue.statuses.values()
            }
            for status in ("unknown", "failed", "retry", "sending", "pending", "accepted"):
                if status in states:
                    return status
            return "ready"
        value = (
            self.runtime.last_telemetry if self.key == "telemetry_updated" else result.last_cleaned
        )
        return datetime.fromtimestamp(value, UTC) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        result = self.runtime.engine.result
        if self.key == "state":
            return {
                "engine_phase": result.state,
                "reason": result.reason,
                "reason_text": describe_reason(result.reason, self.runtime.config["language"]),
                "incident_id": result.incident_id,
                "incident_severity": result.incident_severity,
                "incident_confirmed": result.incident_confirmed,
                "acknowledged": result.acked,
                "snoozed_until": result.snoozed_until,
                "anomaly_duration_seconds": result.anomaly_duration,
                "absolute_alerts_configured": self.runtime.config["min_flow_l_min"] is not None,
                "limitations": self.runtime.limitations,
                "limitations_text": " ".join(
                    describe_reason(reason, self.runtime.config["language"])
                    for reason in self.runtime.limitations
                ),
                "source_statuses": self.runtime.config.get("discovery_statuses", {}),
            }
        if self.key == "email_status":
            return {"recipients": self.runtime.recipient_statuses}
        return None


class RecipientSensor(GuardEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: GuardRuntime, recipient: str) -> None:
        key = hashlib.sha256(recipient.encode()).hexdigest()[:16]
        super().__init__(runtime, f"recipient_{key}")
        self.recipient = recipient
        self._attr_translation_key = "recipient_status"
        state = runtime.hass.states.get(recipient)
        self._attr_translation_placeholders = {"recipient": state.name if state else recipient}

    @property
    def native_value(self) -> str:
        if not self.runtime.config["emails_enabled"]:
            return "disabled"
        return self.runtime.recipient_statuses.get(self.recipient, {}).get("status", "ready")

    @property
    def extra_state_attributes(self):
        return dict(self.runtime.recipient_statuses.get(self.recipient, {}))
