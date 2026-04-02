"""Config flow for Day Phase Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
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
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_STATE,
    DEFAULT_SUN_ENTITY,
    DIRECTION_RISING,
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


def _elevation_to_preset(phase: dict) -> str:
    """Reverse-map a stored phase dict back to the elevation preset key."""
    if phase.get(CONF_TRIGGER_ENTITY):
        return "entity_state"
    elev = phase.get("elevation_trigger")
    if elev is None:
        return "custom"
    for key, val in ELEVATION_PRESETS.items():
        if val is not None and abs(val - float(elev)) < 1e-6:
            return key
    return "custom"


def _phase_schema(
    name_default: str = "",
    preset_default: str = "civil_twilight",
    direction_default: str = DIRECTION_RISING,
    fallback_default: str = "06:00:00",
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name", default=name_default): TextSelector(),
            vol.Required("elevation_preset", default=preset_default): SelectSelector(
                SelectSelectorConfig(
                    options=list(ELEVATION_PRESETS.keys()),
                    mode=SelectSelectorMode.LIST,
                    translation_key="elevation_preset",
                )
            ),
            vol.Required("direction", default=direction_default): SelectSelector(
                SelectSelectorConfig(
                    options=_DIRECTION_OPTIONS,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required("fallback_time", default=fallback_default): TimeSelector(),
        }
    )


def _phase_custom_schema(default: float = 0.0) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("elevation_trigger", default=default): NumberSelector(
                NumberSelectorConfig(min=-90, max=90, step=0.1)
            )
        }
    )


def _phase_entity_schema(
    entity_default: str = "",
    state_default: str = "on",
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_TRIGGER_ENTITY): EntitySelector(),
            vol.Optional(CONF_TRIGGER_STATE, default=state_default): TextSelector(),
        }
    )


def _phase_extra_schema(
    time_max_default: str = "",
    lux_threshold_default: float = 500,
    lux_operator_default: str = LUX_OPERATOR_AND,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_TIME_MAX, default=time_max_default): TextSelector(),
            vol.Optional(CONF_LUX_ENTITY): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_LUX_THRESHOLD, default=lux_threshold_default): NumberSelector(
                NumberSelectorConfig(min=0, max=100000, step=1)
            ),
            vol.Optional(CONF_LUX_OPERATOR, default=lux_operator_default): SelectSelector(
                SelectSelectorConfig(
                    options=_LUX_OPERATOR_OPTIONS,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
    )


def _validate_time_max(user_input: dict, errors: dict) -> str | None:
    """Validate and return normalised time_max, or None. Sets errors in-place."""
    time_max_raw = (user_input.get(CONF_TIME_MAX) or "").strip()
    if not time_max_raw:
        return None
    try:
        h, m = int(time_max_raw.split(":")[0]), int(time_max_raw.split(":")[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except (ValueError, IndexError):
        errors[CONF_TIME_MAX] = "invalid_time"
        return None
    return time_max_raw


# ---------------------------------------------------------------------------
# Config flow (initial setup)
# ---------------------------------------------------------------------------


class DayPhaseTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Day Phase Tracker."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._name: str = ""
        self._sun_entity: str = DEFAULT_SUN_ENTITY
        self._phase_count: int = 0
        self._phases: list[dict[str, Any]] = []
        self._master_phases: dict[str, list[str]] = {}
        self._pending_phase: dict[str, Any] = {}

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> DayPhaseTrackerOptionsFlow:
        """Return the options flow handler."""
        return DayPhaseTrackerOptionsFlow(config_entry)

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
                if preset == "entity_state":
                    self._pending_phase["elevation_trigger"] = None
                    return await self.async_step_phase_entity()
                self._pending_phase["elevation_trigger"] = ELEVATION_PRESETS[preset]
                return await self.async_step_phase_extra()

        return self.async_show_form(
            step_id="phase",
            data_schema=_phase_schema(),
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
            data_schema=_phase_custom_schema(),
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(idx + 1),
                "phase_count": str(self._phase_count),
            },
        )

    # ------------------------------------------------------------------
    # Step 3b-alt: entity-state trigger (SUN2 binary sensors, etc.)
    # ------------------------------------------------------------------

    async def async_step_phase_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        idx = len(self._phases)
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input.get(CONF_TRIGGER_ENTITY) or ""
            if not entity_id:
                errors[CONF_TRIGGER_ENTITY] = "entity_required"
            else:
                self._pending_phase[CONF_TRIGGER_ENTITY] = entity_id
                self._pending_phase[CONF_TRIGGER_STATE] = (
                    user_input.get(CONF_TRIGGER_STATE, "on").strip() or "on"
                )
                return await self.async_step_phase_extra()

        return self.async_show_form(
            step_id="phase_entity",
            data_schema=_phase_entity_schema(),
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(idx + 1),
                "phase_count": str(self._phase_count),
            },
            errors=errors,
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
            time_max_raw = _validate_time_max(user_input, errors)

            if not errors:
                lux_entity = user_input.get(CONF_LUX_ENTITY) or None
                self._phases.append(
                    {
                        **self._pending_phase,
                        CONF_TIME_MAX: time_max_raw,
                        CONF_LUX_ENTITY: lux_entity,
                        CONF_LUX_THRESHOLD: (
                            float(user_input[CONF_LUX_THRESHOLD]) if lux_entity else None
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
            data_schema=_phase_extra_schema(),
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


# ---------------------------------------------------------------------------
# Options flow (edit existing config)
# ---------------------------------------------------------------------------


class DayPhaseTrackerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing Day Phase Tracker entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        # Merge initial data + any previously saved options
        base = {**config_entry.data, **config_entry.options}
        self._sun_entity: str = base.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
        self._phases: list[dict[str, Any]] = list(base.get(CONF_PHASES, []))
        self._master_phases: dict[str, list[str]] = dict(base.get(CONF_MASTER_PHASES, {}))
        self._pending_phase: dict[str, Any] = {}
        self._editing_idx: int | None = None  # None = add-new, int = edit existing

    # ------------------------------------------------------------------
    # Top-level menu
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["edit_settings", "phases_menu", "masters_menu", "opt_finish"],
        )

    # ------------------------------------------------------------------
    # Global settings (sun entity)
    # ------------------------------------------------------------------

    async def async_step_edit_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._sun_entity = user_input[CONF_SUN_ENTITY]
            return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUN_ENTITY, default=self._sun_entity): EntitySelector(
                        EntitySelectorConfig(domain="sun")
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Phases menu
    # ------------------------------------------------------------------

    async def async_step_phases_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="phases_menu",
            menu_options=["phase_add", "phase_edit", "phase_remove", "phase_reorder", "phases_back"],
            description_placeholders={
                "phase_count": str(len(self._phases)),
            },
        )

    async def async_step_phases_back(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_init()

    # ------------------------------------------------------------------
    # Add new phase (reuses config-flow sub-steps via _editing_idx=None)
    # ------------------------------------------------------------------

    async def async_step_phase_add(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._editing_idx = None
        self._pending_phase = {}
        return await self.async_step_opt_phase()

    # ------------------------------------------------------------------
    # Edit phase — select which one
    # ------------------------------------------------------------------

    async def async_step_phase_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if not self._phases:
            return await self.async_step_phases_menu()

        if user_input is not None:
            chosen = user_input.get("phase_name")
            for idx, phase in enumerate(self._phases):
                if phase["name"] == chosen:
                    self._editing_idx = idx
                    self._pending_phase = dict(phase)
                    return await self.async_step_opt_phase()
            errors["phase_name"] = "name_required"

        phase_options = [p["name"] for p in self._phases]
        return self.async_show_form(
            step_id="phase_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("phase_name"): SelectSelector(
                        SelectSelectorConfig(
                            options=phase_options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Remove phase
    # ------------------------------------------------------------------

    async def async_step_phase_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._phases:
            return await self.async_step_phases_menu()

        if user_input is not None:
            chosen = user_input.get("phase_name")
            self._phases = [p for p in self._phases if p["name"] != chosen]
            # Remove from master groups too
            for key in list(self._master_phases.keys()):
                self._master_phases[key] = [
                    s for s in self._master_phases[key] if s != chosen
                ]
                if not self._master_phases[key]:
                    del self._master_phases[key]
            return await self.async_step_phases_menu()

        phase_options = [p["name"] for p in self._phases]
        return self.async_show_form(
            step_id="phase_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("phase_name"): SelectSelector(
                        SelectSelectorConfig(
                            options=phase_options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={
                "phase_count": str(len(self._phases)),
            },
        )

    # ------------------------------------------------------------------
    # Reorder phases
    # ------------------------------------------------------------------

    async def async_step_phase_reorder(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            ordered = user_input.get("phase_order") or []
            name_to_phase = {p["name"]: p for p in self._phases}
            self._phases = [name_to_phase[n] for n in ordered if n in name_to_phase]
            return await self.async_step_phases_menu()

        phase_options = [p["name"] for p in self._phases]
        return self.async_show_form(
            step_id="phase_reorder",
            data_schema=vol.Schema(
                {
                    vol.Required("phase_order", default=phase_options): SelectSelector(
                        SelectSelectorConfig(
                            options=phase_options,
                            multiple=True,
                        )
                    ),
                }
            ),
            description_placeholders={
                "phase_count": str(len(self._phases)),
            },
        )

    # ------------------------------------------------------------------
    # Shared phase form (add or edit)
    # ------------------------------------------------------------------

    async def async_step_opt_phase(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        editing = self._editing_idx is not None

        if user_input is not None:
            name = user_input["name"].strip()
            other_names = {
                p["name"] for i, p in enumerate(self._phases)
                if i != self._editing_idx
            }
            if not name:
                errors["name"] = "name_required"
            elif name in other_names:
                errors["name"] = "duplicate_phase_name"
            else:
                self._pending_phase = {
                    "name": name,
                    "direction": user_input["direction"],
                    "fallback_time": user_input["fallback_time"],
                }
                preset = user_input["elevation_preset"]
                if preset == "custom":
                    return await self.async_step_opt_phase_custom()
                if preset == "entity_state":
                    self._pending_phase["elevation_trigger"] = None
                    return await self.async_step_opt_phase_entity()
                self._pending_phase["elevation_trigger"] = ELEVATION_PRESETS[preset]
                return await self.async_step_opt_phase_extra()

        # Pre-fill when editing
        if editing:
            p = self._phases[self._editing_idx]
            schema = _phase_schema(
                name_default=p["name"],
                preset_default=_elevation_to_preset(p),
                direction_default=p.get("direction", DIRECTION_RISING),
                fallback_default=p.get("fallback_time", "06:00:00"),
            )
        else:
            schema = _phase_schema()

        return self.async_show_form(
            step_id="opt_phase",
            data_schema=schema,
            description_placeholders={
                "phase_num": str(
                    (self._editing_idx + 1) if editing else (len(self._phases) + 1)
                ),
                "phase_count": str(len(self._phases)),
                "action": "Edit" if editing else "Add",
            },
            errors=errors,
        )

    async def async_step_opt_phase_custom(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._pending_phase["elevation_trigger"] = float(user_input["elevation_trigger"])
            return await self.async_step_opt_phase_extra()

        editing = self._editing_idx is not None
        current_elev = (
            float(self._phases[self._editing_idx].get("elevation_trigger") or 0.0)
            if editing
            else 0.0
        )
        return self.async_show_form(
            step_id="opt_phase_custom",
            data_schema=_phase_custom_schema(default=current_elev),
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(
                    (self._editing_idx + 1) if editing else (len(self._phases) + 1)
                ),
                "phase_count": str(len(self._phases)),
            },
        )

    async def async_step_opt_phase_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        editing = self._editing_idx is not None

        if user_input is not None:
            entity_id = user_input.get(CONF_TRIGGER_ENTITY) or ""
            if not entity_id:
                errors[CONF_TRIGGER_ENTITY] = "entity_required"
            else:
                self._pending_phase[CONF_TRIGGER_ENTITY] = entity_id
                self._pending_phase[CONF_TRIGGER_STATE] = (
                    user_input.get(CONF_TRIGGER_STATE, "on").strip() or "on"
                )
                return await self.async_step_opt_phase_extra()

        if editing:
            p = self._phases[self._editing_idx]
            schema = _phase_entity_schema(
                state_default=p.get(CONF_TRIGGER_STATE, "on"),
            )
        else:
            schema = _phase_entity_schema()

        return self.async_show_form(
            step_id="opt_phase_entity",
            data_schema=schema,
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(
                    (self._editing_idx + 1) if editing else (len(self._phases) + 1)
                ),
                "phase_count": str(len(self._phases)),
            },
            errors=errors,
        )

    async def async_step_opt_phase_extra(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        editing = self._editing_idx is not None

        if user_input is not None:
            time_max_raw = _validate_time_max(user_input, errors)

            if not errors:
                lux_entity = user_input.get(CONF_LUX_ENTITY) or None
                completed_phase = {
                    **self._pending_phase,
                    CONF_TIME_MAX: time_max_raw,
                    CONF_LUX_ENTITY: lux_entity,
                    CONF_LUX_THRESHOLD: (
                        float(user_input[CONF_LUX_THRESHOLD]) if lux_entity else None
                    ),
                    CONF_LUX_OPERATOR: (
                        user_input.get(CONF_LUX_OPERATOR, LUX_OPERATOR_AND)
                        if lux_entity
                        else LUX_OPERATOR_AND
                    ),
                }
                if editing:
                    self._phases[self._editing_idx] = completed_phase
                else:
                    self._phases.append(completed_phase)
                self._editing_idx = None
                return await self.async_step_phases_menu()

        if editing:
            p = self._phases[self._editing_idx]
            schema = _phase_extra_schema(
                time_max_default=p.get(CONF_TIME_MAX) or "",
                lux_threshold_default=float(p.get(CONF_LUX_THRESHOLD) or 500),
                lux_operator_default=p.get(CONF_LUX_OPERATOR, LUX_OPERATOR_AND),
            )
        else:
            schema = _phase_extra_schema()

        return self.async_show_form(
            step_id="opt_phase_extra",
            data_schema=schema,
            description_placeholders={
                "phase_name": self._pending_phase.get("name", ""),
                "phase_num": str(
                    (self._editing_idx + 1) if editing else (len(self._phases) + 1)
                ),
                "phase_count": str(len(self._phases)),
            },
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Masters menu
    # ------------------------------------------------------------------

    async def async_step_masters_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="masters_menu",
            menu_options=["master_edit_add", "master_edit_remove", "masters_back"],
            description_placeholders={
                "group_count": str(len(self._master_phases)),
            },
        )

    async def async_step_masters_back(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_init()

    async def async_step_master_edit_add(
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
                return await self.async_step_masters_menu()

        phase_options = [p["name"] for p in self._phases]
        return self.async_show_form(
            step_id="master_edit_add",
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

    async def async_step_master_edit_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._master_phases:
            return await self.async_step_masters_menu()

        if user_input is not None:
            group_name = user_input.get("master_name")
            self._master_phases.pop(group_name, None)
            return await self.async_step_masters_menu()

        group_options = list(self._master_phases.keys())
        return self.async_show_form(
            step_id="master_edit_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("master_name"): SelectSelector(
                        SelectSelectorConfig(
                            options=group_options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Finish — write to entry.options
    # ------------------------------------------------------------------

    async def async_step_opt_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_create_entry(
            data={
                CONF_SUN_ENTITY: self._sun_entity,
                CONF_PHASES: self._phases,
                CONF_MASTER_PHASES: self._master_phases,
            }
        )
