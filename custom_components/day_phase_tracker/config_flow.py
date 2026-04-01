"""Config flow for Day Phase Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)

from .const import (
    CONF_LUX_ENTITY,
    CONF_LUX_OPERATOR,
    CONF_LUX_THRESHOLD,
    CONF_MASTER_PHASES,
    CONF_NAME,
    CONF_PHASES,
    CONF_SUN_ENTITY,
    CONF_TIME_MAX,
    DEFAULT_SUN_ENTITY,
    DOMAIN,
    ELEVATION_PRESETS,
    LUX_OPERATOR_AND,
    LUX_OPERATOR_OR,
)

_DIRECTION_OPTIONS = [
    {"value": "rising", "label": "Rising (↑)"},
    {"value": "falling", "label": "Falling (↓)"},
]

_LUX_OPERATOR_OPTIONS = [
    {"value": LUX_OPERATOR_AND, "label": "AND — both must match"},
    {"value": LUX_OPERATOR_OR, "label": "OR — either triggers the phase"},
]


class DayPhaseTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Day Phase Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._name: str = ""
        self._sun_entity: str = DEFAULT_SUN_ENTITY
        self._phase_count: int = 0
        self._phases: list[dict[str, Any]] = []
        self._master_phases: dict[str, list[str]] = {}
        # Accumulates fields across the phase sub-steps before appending to _phases
        self._pending_phase: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Step 1: instance name + sun entity
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors["base"] = "name_required"
            else:
                self._name = name
                self._sun_entity = user_input[CONF_SUN_ENTITY]
                return await self.async_step_phase_count()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): TextSelector(),
                    vol.Required(CONF_SUN_ENTITY, default=DEFAULT_SUN_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sun")
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2: how many phases
    # ------------------------------------------------------------------

    async def async_step_phase_count(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._phase_count = int(user_input["phase_count"])
            self._phases = []
            return await self.async_step_phase()

        return self.async_show_form(
            step_id="phase_count",
            data_schema=vol.Schema(
                {
                    vol.Required("phase_count", default=4): NumberSelector(
                        NumberSelectorConfig(
                            min=2, max=12, step=1, mode=NumberSelectorMode.BOX
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 3a: core phase fields
    # ------------------------------------------------------------------

    async def async_step_phase(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        idx = len(self._phases)
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "name_required"
            elif name in {p["name"] for p in self._phases}:
                errors["name"] = "duplicate_phase_name"
            else:
                self._pending_phase = {
                    "name": name,
                    "direction": user_input["direction"],
                    "fallback_time": user_input["fallback_time"],
                }
                preset = user_input["elevation_preset"]
                if preset == "custom":
                    return await self.async_step_phase_custom()
                self._pending_phase["elevation_trigger"] = ELEVATION_PRESETS[preset]
                return await self.async_step_phase_extra()

        return self.async_show_form(
            step_id="phase",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): TextSelector(),
                    vol.Required("elevation_preset"): SelectSelector(
                        SelectSelectorConfig(
                            options=list(ELEVATION_PRESETS.keys()),
                            mode=SelectSelectorMode.LIST,
                            translation_key="elevation_preset",
                        )
                    ),
                    vol.Required("direction"): SelectSelector(
                        SelectSelectorConfig(
                            options=_DIRECTION_OPTIONS,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required("fallback_time"): TimeSelector(),
                }
            ),
            description_placeholders={
                "phase_num": str(idx + 1),
                "phase_count": str(self._phase_count),
            },
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3b (optional): custom elevation number
    # ------------------------------------------------------------------

    async def async_step_phase_custom(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        idx = len(self._phases)

        if user_input is not None:
            self._pending_phase["elevation_trigger"] = float(user_input["elevation_trigger"])
            return await self.async_step_phase_extra()

        return self.async_show_form(
            step_id="phase_custom",
            data_schema=vol.Schema(
                {
                    vol.Required("elevation_trigger"): NumberSelector(
                        NumberSelectorConfig(min=-90, max=90, step=0.1)
                    )
                }
            ),
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(idx + 1),
                "phase_count": str(self._phase_count),
            },
        )

    # ------------------------------------------------------------------
    # Step 3c: optional constraints (lux + time window)
    # ------------------------------------------------------------------

    async def async_step_phase_extra(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        idx = len(self._phases)
        errors: dict[str, str] = {}

        if user_input is not None:
            # --- time_max (optional text field, empty = no limit) -------
            time_max_raw = (user_input.get(CONF_TIME_MAX) or "").strip()
            if time_max_raw:
                parts = time_max_raw.replace(":", "").ljust(4, "0")
                try:
                    h, m = int(time_max_raw.split(":")[0]), int(time_max_raw.split(":")[1])
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        raise ValueError
                except (ValueError, IndexError):
                    errors[CONF_TIME_MAX] = "invalid_time"

            if not errors:
                lux_entity = user_input.get(CONF_LUX_ENTITY) or None
                self._phases.append(
                    {
                        **self._pending_phase,
                        CONF_TIME_MAX: time_max_raw or None,
                        CONF_LUX_ENTITY: lux_entity,
                        CONF_LUX_THRESHOLD: (
                            float(user_input[CONF_LUX_THRESHOLD])
                            if lux_entity
                            else None
                        ),
                        CONF_LUX_OPERATOR: (
                            user_input.get(CONF_LUX_OPERATOR, LUX_OPERATOR_AND)
                            if lux_entity
                            else LUX_OPERATOR_AND
                        ),
                    }
                )
                if len(self._phases) >= self._phase_count:
                    return await self.async_step_master_menu()
                return await self.async_step_phase()

        return self.async_show_form(
            step_id="phase_extra",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_TIME_MAX, default=""): TextSelector(),
                    vol.Optional(CONF_LUX_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_LUX_THRESHOLD, default=500): NumberSelector(
                        NumberSelectorConfig(min=0, max=100000, step=1)
                    ),
                    vol.Optional(CONF_LUX_OPERATOR, default=LUX_OPERATOR_AND): SelectSelector(
                        SelectSelectorConfig(
                            options=_LUX_OPERATOR_OPTIONS,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(idx + 1),
                "phase_count": str(self._phase_count),
            },
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Master phases – menu
    # ------------------------------------------------------------------

    async def async_step_master_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="master_menu",
            menu_options=["master_add", "master_done"],
            description_placeholders={
                "group_count": str(len(self._master_phases)),
            },
        )

    # ------------------------------------------------------------------
    # Master phases – add one group
    # ------------------------------------------------------------------

    async def async_step_master_add(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            group_name = user_input["master_name"].strip()
            sub = user_input.get("sub_phases") or []
            if not group_name:
                errors["master_name"] = "name_required"
            elif not sub:
                errors["sub_phases"] = "min_phases"
            else:
                self._master_phases[group_name] = sub
                return await self.async_step_master_menu()

        phase_options = [p["name"] for p in self._phases]
        return self.async_show_form(
            step_id="master_add",
            data_schema=vol.Schema(
                {
                    vol.Required("master_name"): TextSelector(),
                    vol.Required("sub_phases"): SelectSelector(
                        SelectSelectorConfig(options=phase_options, multiple=True)
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------

    async def async_step_master_done(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(self._name.lower())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._name,
            data={
                CONF_NAME: self._name,
                CONF_SUN_ENTITY: self._sun_entity,
                CONF_PHASES: self._phases,
                CONF_MASTER_PHASES: self._master_phases,
            },
        )
