"""Config flow for Day Phase Tracker."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_MASTER_PHASES, CONF_NAME, CONF_PHASES, DOMAIN, VALID_DIRECTIONS


def _normalize_name(name: str) -> str:
    return name.strip()


def _validate_phases(raw_text: str) -> list[dict[str, Any]]:
    try:
        phases = json.loads(raw_text)
    except json.JSONDecodeError as err:
        raise vol.Invalid(f"Invalid JSON for phases: {err}") from err

    if not isinstance(phases, list) or len(phases) < 2:
        raise vol.Invalid("At least two phases are required")

    for idx, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            raise vol.Invalid(f"Phase {idx} must be an object")
        for key in ("name", "elevation_trigger", "direction", "fallback_time"):
            if key not in phase:
                raise vol.Invalid(f"Phase {idx} missing '{key}'")
        if phase["direction"] not in VALID_DIRECTIONS:
            raise vol.Invalid(f"Phase {idx} direction must be rising/falling")
    return phases


def _validate_master_phases(raw_text: str, phases: list[dict[str, Any]]) -> dict[str, list[str]]:
    if not raw_text.strip():
        return {}

    try:
        master = json.loads(raw_text)
    except json.JSONDecodeError as err:
        raise vol.Invalid(f"Invalid JSON for master phases: {err}") from err

    if not isinstance(master, dict):
        raise vol.Invalid("Master phases must be a JSON object")

    phase_names = {phase["name"] for phase in phases}
    for key, values in master.items():
        if not isinstance(values, list) or not values:
            raise vol.Invalid(f"Master phase '{key}' must reference a non-empty list")
        unknown = [item for item in values if item not in phase_names]
        if unknown:
            raise vol.Invalid(f"Master phase '{key}' contains unknown phases: {unknown}")

    return master


class DayPhaseTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Day Phase Tracker."""

    VERSION = 1

    _user_input: dict[str, Any]

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the first step (name)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = _normalize_name(user_input[CONF_NAME])
            if not name:
                errors["base"] = "name_required"
            else:
                self._user_input = {CONF_NAME: name}
                return await self.async_step_phases()

        schema = vol.Schema({vol.Required(CONF_NAME): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_phases(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle phase definition step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                phases = _validate_phases(user_input[CONF_PHASES])
            except vol.Invalid:
                errors["base"] = "invalid_phases"
            else:
                self._user_input[CONF_PHASES] = phases
                self._user_input[CONF_MASTER_PHASES] = {}
                return await self.async_step_master()

        default = json.dumps(
            [
                {
                    "name": "early_morning",
                    "elevation_trigger": -5.4,
                    "direction": "rising",
                    "fallback_time": "06:30",
                },
                {
                    "name": "late_night",
                    "elevation_trigger": -11.4,
                    "direction": "falling",
                    "fallback_time": "00:00",
                },
            ],
            indent=2,
        )
        schema = vol.Schema({vol.Required(CONF_PHASES, default=default): str})
        return self.async_show_form(step_id="phases", data_schema=schema, errors=errors)

    async def async_step_master(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle optional master phases."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                master_phases = _validate_master_phases(
                    user_input[CONF_MASTER_PHASES], self._user_input[CONF_PHASES]
                )
            except vol.Invalid:
                errors["base"] = "invalid_master"
            else:
                self._user_input[CONF_MASTER_PHASES] = master_phases
                await self.async_set_unique_id(self._user_input[CONF_NAME].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._user_input[CONF_NAME],
                    data=self._user_input,
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_MASTER_PHASES, default=""): str,
            }
        )
        return self.async_show_form(step_id="master", data_schema=schema, errors=errors)
