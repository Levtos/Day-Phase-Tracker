"""Constants for the Day Phase Tracker integration."""

from __future__ import annotations

DOMAIN = "day_phase_tracker"
PLATFORMS = ["sensor"]

CONF_NAME = "name"
CONF_PHASES = "phases"
CONF_MASTER_PHASES = "master_phases"
CONF_SUN_ENTITY = "sun_entity"

DEFAULT_SUN_ENTITY = "sun.sun"

DEFAULT_SCAN_SECONDS = 60

ATTR_ELEVATION = "elevation"
ATTR_PHASE_INDEX = "phase_index"
ATTR_PHASE_COUNT = "phase_count"
ATTR_CURRENT_PHASE_START = "current_phase_start"
ATTR_CURRENT_PHASE_TRIGGER = "current_phase_trigger"
ATTR_NEXT_PHASE = "next_phase"
ATTR_NEXT_PHASE_ESTIMATED = "next_phase_estimated"
ATTR_TODAY = "today"
ATTR_SUB_PHASE = "sub_phase"
ATTR_PHASES_IN_GROUP = "phases_in_group"

DIRECTION_RISING = "rising"
DIRECTION_FALLING = "falling"
VALID_DIRECTIONS = {DIRECTION_RISING, DIRECTION_FALLING}

LUX_OPERATOR_AND = "and"
LUX_OPERATOR_OR = "or"

CONF_TIME_MAX = "time_max"
CONF_LUX_ENTITY = "lux_entity"
CONF_LUX_THRESHOLD = "lux_threshold"
CONF_LUX_OPERATOR = "lux_operator"

# Standard solar elevation thresholds (degrees).
# None marks the "enter manually" option in the config flow.
ELEVATION_PRESETS: dict[str, float | None] = {
    "astronomical_twilight": -18.0,
    "nautical_twilight": -12.0,
    "civil_twilight": -6.0,
    "sunrise_sunset": -0.83,
    "golden_hour": 6.0,
    "high_sun": 45.0,
    "custom": None,
}
