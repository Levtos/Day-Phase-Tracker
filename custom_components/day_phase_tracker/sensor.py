"""Sensor platform for Day Phase Tracker."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import (
    ATTR_CURRENT_PHASE_START,
    ATTR_CURRENT_PHASE_TRIGGER,
    ATTR_ELEVATION,
    ATTR_NEXT_PHASE,
    ATTR_NEXT_PHASE_ESTIMATED,
    ATTR_PHASE_COUNT,
    ATTR_PHASE_INDEX,
    ATTR_PHASES_IN_GROUP,
    ATTR_SUB_PHASE,
    ATTR_TODAY,
    CONF_MASTER_PHASES,
    CONF_NAME,
    CONF_PHASES,
    CONF_SUN_ENTITY,
    DEFAULT_SUN_ENTITY,
)
from .tracker import DayPhaseTracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up day phase sensor entities."""
    # Merge base config with any options saved via the OptionsFlow
    config = {**entry.data, **entry.options}
    tracker = DayPhaseTracker(
        hass,
        config[CONF_PHASES],
        config.get(CONF_MASTER_PHASES, {}),
        config.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY),
    )

    day_sensor = DayPhaseSensor(entry, tracker, config[CONF_NAME])
    entities: list[SensorEntity] = [day_sensor]

    if config.get(CONF_MASTER_PHASES):
        entities.append(MasterPhaseSensor(entry, tracker, config[CONF_NAME]))

    async_add_entities(entities, True)


class BasePhaseSensor(SensorEntity):
    """Base class with periodic refresh wiring."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, tracker: DayPhaseTracker) -> None:
        self._entry = entry
        self._tracker = tracker
        self._snapshot: dict = {}
        self._unsubscribers: list = []

    async def async_added_to_hass(self) -> None:
        entities = (
            [self._tracker.sun_entity]
            + self._tracker.lux_entities
            + self._tracker.trigger_entities
        )
        self._unsubscribers.append(
            async_track_state_change_event(self.hass, entities, self._handle_trigger)
        )
        self._unsubscribers.append(
            async_track_time_interval(self.hass, self._handle_trigger, timedelta(seconds=60))
        )

    async def async_will_remove_from_hass(self) -> None:
        while self._unsubscribers:
            unsub = self._unsubscribers.pop()
            unsub()

    @callback
    def _handle_trigger(self, *_args) -> None:
        self.async_schedule_update_ha_state(True)


class DayPhaseSensor(BasePhaseSensor):
    """Main day phase sensor."""

    _attr_icon = "mdi:weather-sunset"
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, entry: ConfigEntry, tracker: DayPhaseTracker, instance_name: str) -> None:
        super().__init__(entry, tracker)
        object_base = instance_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{entry.entry_id}_{object_base}_dayphase"
        self._attr_name = f"{instance_name} Dayphase"

    @property
    def options(self) -> list[str]:
        """Return all possible phase names (required for ENUM device class)."""
        return [p.name for p in self._tracker.phases]

    @property
    def native_value(self) -> str | None:
        return self._snapshot.get("state")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ELEVATION: self._snapshot.get("elevation"),
            ATTR_PHASE_INDEX: self._snapshot.get("phase_index"),
            ATTR_PHASE_COUNT: self._snapshot.get("phase_count"),
            ATTR_CURRENT_PHASE_START: self._snapshot.get("current_phase_start"),
            ATTR_CURRENT_PHASE_TRIGGER: self._snapshot.get("current_phase_trigger"),
            ATTR_NEXT_PHASE: self._snapshot.get("next_phase"),
            ATTR_NEXT_PHASE_ESTIMATED: self._snapshot.get("next_phase_estimated"),
            ATTR_TODAY: self._snapshot.get("today"),
        }

    async def async_update(self) -> None:
        self._snapshot = self._tracker.calculate()


class MasterPhaseSensor(BasePhaseSensor):
    """Optional master phase sensor."""

    _attr_icon = "mdi:layers-triple"

    def __init__(self, entry: ConfigEntry, tracker: DayPhaseTracker, instance_name: str) -> None:
        super().__init__(entry, tracker)
        object_base = instance_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{entry.entry_id}_{object_base}_master"
        self._attr_name = f"{instance_name} Master Phase"

    @property
    def native_value(self) -> str | None:
        master = self._snapshot.get("master")
        return master.get("name") if master else None

    @property
    def extra_state_attributes(self) -> dict:
        master = self._snapshot.get("master") or {}
        return {
            ATTR_SUB_PHASE: master.get("sub_phase"),
            ATTR_PHASES_IN_GROUP: master.get("phases_in_group"),
        }

    async def async_update(self) -> None:
        self._snapshot = self._tracker.calculate()
