"""The Day Phase Tracker integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_LUX_ENTITY,
    CONF_LUX_OPERATOR,
    CONF_LUX_THRESHOLD,
    CONF_MASTER_PHASES,
    CONF_PHASES,
    CONF_SUN_ENTITY,
    CONF_TIME_MAX,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_STATE,
    DEFAULT_SUN_ENTITY,
    DOMAIN,
    DIRECTION_RISING,
    LUX_OPERATOR_AND,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

# Current schema version — bump MINOR_VERSION when adding optional fields.
# Bump VERSION when a breaking change requires full re-setup.
_CURRENT_VERSION = 1
_CURRENT_MINOR = 1


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry to current schema."""
    version = entry.version
    minor = entry.minor_version if hasattr(entry, "minor_version") else 0

    _LOGGER.debug(
        "Migrating Day Phase Tracker entry from v%s.%s to v%s.%s",
        version, minor, _CURRENT_VERSION, _CURRENT_MINOR,
    )

    if version > _CURRENT_VERSION:
        # Cannot downgrade
        return False

    data = dict(entry.data)

    if version == 1 and minor < 1:
        # v1.0 → v1.1: Normalise phase dicts — add any optional keys that
        # were introduced after the initial release.
        normalised_phases = []
        for phase in data.get(CONF_PHASES, []):
            normalised_phases.append({
                "name": phase.get("name", ""),
                "direction": phase.get("direction", DIRECTION_RISING),
                "fallback_time": phase.get("fallback_time", "00:00"),
                "elevation_trigger": phase.get("elevation_trigger"),
                CONF_TIME_MAX: phase.get(CONF_TIME_MAX),
                CONF_LUX_ENTITY: phase.get(CONF_LUX_ENTITY),
                CONF_LUX_THRESHOLD: phase.get(CONF_LUX_THRESHOLD),
                CONF_LUX_OPERATOR: phase.get(CONF_LUX_OPERATOR, LUX_OPERATOR_AND),
                CONF_TRIGGER_ENTITY: phase.get(CONF_TRIGGER_ENTITY),
                CONF_TRIGGER_STATE: phase.get(CONF_TRIGGER_STATE, "on"),
            })
        data[CONF_PHASES] = normalised_phases
        data.setdefault(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
        data.setdefault(CONF_MASTER_PHASES, {})

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        version=_CURRENT_VERSION,
        minor_version=_CURRENT_MINOR,
    )
    _LOGGER.info("Migration of Day Phase Tracker entry successful.")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Day Phase Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload sensors when options are updated via the OptionsFlow
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry so sensors pick up changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
