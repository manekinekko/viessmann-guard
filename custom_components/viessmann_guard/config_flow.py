"""Guided local configuration. No Viessmann or SMTP connection is made here."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    EMAIL_DEFAULTS,
    LIST_SETTINGS,
    MAX_REPORT_ENTITIES,
    NUMERIC_RULES,
    REQUIRED_ROLES,
    SOURCE_ROLES,
)
from .discovery import Candidate, bind_sources, configured_devices, discover, resolve_sources
from .runtime import configuration
from .validation import validate_emails, validate_rules, validate_sources


def sources_schema(*, optional=False) -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required("name"): vol.All(str, vol.Length(min=1, max=60)),
        vol.Required("device_ids"): selector.DeviceSelector({"multiple": True}),
    }
    for role in SOURCE_ROLES:
        field = vol.Required if role in REQUIRED_ROLES and not optional else vol.Optional
        schema[field(f"{role}_entity")] = selector.EntitySelector(
            {"filter": [{"domain": ["sensor", "binary_sensor", "select", "climate", "number"]}]}
        )
    return vol.Schema(schema)


def rules_schema() -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Optional("min_flow_l_min"): vol.All(
            vol.Coerce(float), vol.Range(min=0.001, max=100000)
        ),
    }
    for key, (default, minimum, maximum) in NUMERIC_RULES.items():
        schema[vol.Required(key, default=default)] = vol.All(
            vol.Coerce(int if key == "calibration_samples" else float),
            vol.Range(min=minimum, max=maximum),
        )
    for key in LIST_SETTINGS:
        default_values = (
            ["on"]
            if key == "pump_on_values"
            else ["off"]
            if key in ("pump_off_values", "fault_clear_values")
            else []
        )
        schema[vol.Required(key, default=default_values)] = selector.SelectSelector(
            {
                "options": [],
                "multiple": True,
                "custom_value": True,
                "mode": selector.SelectSelectorMode.DROPDOWN,
            }
        )
    return vol.Schema(schema)


def emails_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("emails_enabled", default=False): bool,
            vol.Required("recipients", default=[]): selector.EntitySelector(
                {"filter": [{"domain": "notify", "integration": "smtp"}], "multiple": True}
            ),
            vol.Required("reminder_hours", default=24): vol.All(
                vol.Coerce(float), vol.Range(min=1, max=720)
            ),
            vol.Required("watch_email", default=False): bool,
            vol.Required("language", default="en"): vol.In(["en", "fr"]),
        }
    )


def report_schema() -> vol.Schema:
    entities = selector.EntitySelector(
        {
            "filter": [{"domain": ["sensor", "binary_sensor", "select", "climate", "number"]}],
            "multiple": True,
        }
    )
    return vol.Schema(
        {
            vol.Required("report_entities", default=[]): vol.All(
                entities, vol.Length(max=MAX_REPORT_ENTITIES)
            ),
            vol.Required("report_exclude", default=[]): entities,
        }
    )


class GuardFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        self.pending: dict[str, Any] = {}
        self.candidate: Candidate | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GuardOptionsFlow:
        return GuardOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        candidates = discover(self.hass)
        available = [
            item for item in candidates if item.device_id not in configured_devices(self.hass)
        ]
        if not available:
            if candidates:
                return self.async_abort(reason="already_configured")
            return self.async_show_menu(step_id="user", menu_options=["manual"])
        if len(available) == 1:
            self.candidate = available[0]
            return await self.async_step_confirm()
        return await self.async_step_select_device(user_input)

    async def async_step_select_device(self, user_input=None) -> ConfigFlowResult:
        candidates = [
            item
            for item in discover(self.hass)
            if item.device_id not in configured_devices(self.hass)
        ]
        if user_input:
            self.candidate = next(
                (item for item in candidates if item.device_id == user_input["device_id"]), None
            )
            if self.candidate:
                return await self.async_step_confirm()
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device_id"): selector.SelectSelector(
                        {
                            "options": [
                                selector.SelectOptionDict(
                                    value=item.device_id, label=f"{index}. {item.name}"
                                )
                                for index, item in enumerate(candidates, 1)
                            ],
                            "mode": selector.SelectSelectorMode.LIST,
                        }
                    )
                }
            ),
            errors={"base": "source_changed"} if user_input else {},
        )

    async def async_step_confirm(self, user_input=None) -> ConfigFlowResult:
        assert self.candidate is not None
        device_id = self.candidate.device_id
        if device_id in configured_devices(self.hass):
            return self.async_abort(reason="already_configured")
        current = next((item for item in discover(self.hass) if item.device_id == device_id), None)
        if current is None:
            return self.async_abort(reason="source_changed")
        if user_input is not None:
            if current.config != self.candidate.config:
                self.candidate = current
                return self.async_show_form(
                    step_id="confirm",
                    data_schema=vol.Schema({}),
                    description_placeholders=self._summary(current),
                    errors={"base": "source_changed"},
                    last_step=True,
                )
            await self.async_set_unique_id(f"vicare_{device_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=current.config["name"], data=current.config)
        self.candidate = current
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=self._summary(current),
            last_step=True,
        )

    def _summary(self, candidate: Candidate) -> dict[str, str]:
        french = self.hass.config.language.startswith("fr")
        from .onboarding import summary

        return {"summary": summary(candidate.name, candidate.statuses, french)}

    async def async_step_manual(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            errors = validate_sources(self.hass, user_input)
            if set(user_input.get("device_ids", [])) & configured_devices(self.hass):
                errors["device_ids"] = "already_configured"
            if not errors:
                self.pending.update(user_input)
                return await self.async_step_rules()
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(sources_schema(), user_input),
            errors=errors,
        )

    async def async_step_rules(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            errors = validate_rules({**self.pending, **user_input})
            if not errors:
                self.pending.update(user_input)
                self.pending["min_flow_l_min"] = user_input.get("min_flow_l_min")
                self.pending["calibration_samples"] = int(user_input["calibration_samples"])
                return await self.async_step_emails()
        return self.async_show_form(
            step_id="rules",
            data_schema=self.add_suggested_values_to_schema(rules_schema(), user_input),
            errors=errors,
        )

    async def async_step_emails(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            errors = validate_emails(self.hass, user_input)
            if not errors:
                self.pending.update(user_input)
                return await self.async_step_report()
        return self.async_show_form(
            step_id="emails",
            data_schema=self.add_suggested_values_to_schema(
                emails_schema(), user_input or EMAIL_DEFAULTS
            ),
            errors=errors,
        )

    async def async_step_report(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            from .telemetry import validate_report_entities

            errors = validate_report_entities(self.hass, {**self.pending, **user_input})
            if not errors:
                self.pending.update(user_input)
                if set(self.pending["device_ids"]) & configured_devices(self.hass):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=self.pending["name"], data=bind_sources(self.hass, self.pending)
                )
        return self.async_show_form(step_id="report", data_schema=report_schema(), errors=errors)


class GuardOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["minimum", "emails", "sources", "rules", "report"]
        )

    async def _step(self, step: str, schema: vol.Schema, user_input) -> ConfigFlowResult:
        current = resolve_sources(self.hass, configuration(self.config_entry))
        errors = {}
        if user_input is not None:
            runtime = getattr(self.config_entry, "runtime_data", None)
            if (
                step == "emails"
                and user_input.get("emails_enabled") is False
                and runtime is not None
            ):
                # An invalid/removed recipient must never prevent switching mail off.
                await runtime.set_emails(False)
            merged = {**current, **user_input}
            if step == "sources":
                for role in SOURCE_ROLES:
                    key = f"{role}_entity"
                    if key not in user_input:
                        merged[key] = None
                errors = validate_sources(self.hass, merged)
                if set(merged["device_ids"]) & configured_devices(
                    self.hass, excluding=self.config_entry.entry_id
                ):
                    errors["device_ids"] = "already_configured"
                merged = bind_sources(self.hass, merged)
                merged["discovery_statuses"] = {}
            elif step == "rules":
                merged["min_flow_l_min"] = user_input.get("min_flow_l_min")
                errors = validate_rules(merged)
                if not errors:
                    merged["calibration_samples"] = int(merged["calibration_samples"])
            elif step == "minimum":
                merged["min_flow_l_min"] = user_input.get("min_flow_l_min")
                errors = validate_rules(merged)
            elif step == "report":
                from .telemetry import validate_report_entities

                errors = validate_report_entities(self.hass, merged)
                merged["report_registry_ids"] = bind_sources(self.hass, merged)[
                    "report_registry_ids"
                ]
            else:
                errors = validate_emails(self.hass, merged)
            if not errors:
                # Invalidate dispatch synchronously before options persistence/reload.
                runtime = getattr(self.config_entry, "runtime_data", None)
                if runtime is not None:
                    runtime.prepare_options(merged)
                return self.async_create_entry(data=merged)
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {key: value for key, value in (user_input or current).items() if value is not None},
            ),
            errors=errors,
        )

    async def async_step_emails(self, user_input=None) -> ConfigFlowResult:
        return await self._step("emails", emails_schema(), user_input)

    async def async_step_sources(self, user_input=None) -> ConfigFlowResult:
        return await self._step("sources", sources_schema(optional=True), user_input)

    async def async_step_minimum(self, user_input=None) -> ConfigFlowResult:
        return await self._step(
            "minimum",
            vol.Schema(
                {
                    vol.Optional("min_flow_l_min"): vol.All(
                        vol.Coerce(float), vol.Range(min=0.001, max=100000)
                    )
                }
            ),
            user_input,
        )

    async def async_step_rules(self, user_input=None) -> ConfigFlowResult:
        return await self._step("rules", rules_schema(), user_input)

    async def async_step_report(self, user_input=None) -> ConfigFlowResult:
        return await self._step("report", report_schema(), user_input)
