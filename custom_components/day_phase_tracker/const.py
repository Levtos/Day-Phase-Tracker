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
