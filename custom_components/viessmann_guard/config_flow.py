"""Guided local configuration. No Viessmann or SMTP connection is made here."""

import math
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
from .validation import validate_recipients, validate_rules, validate_sources


def finite_number(value: float) -> float:
    if not math.isfinite(value):
        raise vol.Invalid("A finite number is required")
    return value


def sources_schema() -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required("name"): vol.All(str, vol.Length(min=1, max=60), vol.Match(r"^[^\r\n]+$")),
        vol.Required("device_ids"): selector.DeviceSelector({"multiple": True}),
    }
    for role in SOURCE_ROLES:
        field = vol.Required if role in REQUIRED_ROLES else vol.Optional
        schema[field(f"{role}_entity")] = selector.EntitySelector(
            {"filter": [{"domain": ["sensor", "binary_sensor", "select", "climate", "number"]}]}
        )
    return vol.Schema(schema)


def rules_schema() -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required("min_flow_l_min"): vol.All(
            vol.Coerce(float), finite_number, vol.Range(min=0.001, max=100000)
        ),
    }
    for key, (default, minimum, maximum) in NUMERIC_RULES.items():
        schema[vol.Required(key, default=default)] = vol.All(
            vol.Coerce(int if key == "calibration_samples" else float),
            finite_number,
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
                vol.Coerce(float), finite_number, vol.Range(min=1, max=720)
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

    def __init__(self) -> None:
        self.pending: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GuardOptionsFlow:
        return GuardOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            errors = validate_sources(self.hass, user_input)
            if not errors:
                self.pending.update(user_input)
                return await self.async_step_rules()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(sources_schema(), user_input),
            errors=errors,
        )

    async def async_step_rules(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            errors = validate_rules({**self.pending, **user_input})
            if not errors:
                self.pending.update(user_input)
                return await self.async_step_emails()
        return self.async_show_form(
            step_id="rules",
            data_schema=self.add_suggested_values_to_schema(rules_schema(), user_input),
            errors=errors,
        )

    async def async_step_emails(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                validate_recipients(self.hass, user_input["recipients"])
                if user_input["emails_enabled"] and not user_input["recipients"]:
                    raise ValueError("required_recipient")
            except ValueError as err:
                errors["recipients"] = str(err)
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
                return self.async_create_entry(title=self.pending["name"], data=self.pending)
        return self.async_show_form(step_id="report", data_schema=report_schema(), errors=errors)


class GuardOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["emails", "sources", "rules", "report"]
        )

    async def _step(self, step: str, schema: vol.Schema, user_input) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
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
            elif step == "rules":
                errors = validate_rules(merged)
            elif step == "report":
                from .telemetry import validate_report_entities

                errors = validate_report_entities(self.hass, merged)
            else:
                try:
                    validate_recipients(self.hass, merged["recipients"])
                    if merged["emails_enabled"] and not merged["recipients"]:
                        raise ValueError("required_recipient")
                except ValueError as err:
                    errors["recipients"] = str(err)
            if not errors:
                # Invalidate dispatch synchronously before options persistence/reload.
                runtime = getattr(self.config_entry, "runtime_data", None)
                if runtime is not None:
                    runtime.prepare_options(merged)
                return self.async_create_entry(data=merged)
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(schema, user_input or current),
            errors=errors,
        )

    async def async_step_emails(self, user_input=None) -> ConfigFlowResult:
        return await self._step("emails", emails_schema(), user_input)

    async def async_step_sources(self, user_input=None) -> ConfigFlowResult:
        return await self._step("sources", sources_schema(), user_input)

    async def async_step_rules(self, user_input=None) -> ConfigFlowResult:
        return await self._step("rules", rules_schema(), user_input)

    async def async_step_report(self, user_input=None) -> ConfigFlowResult:
        return await self._step("report", report_schema(), user_input)
