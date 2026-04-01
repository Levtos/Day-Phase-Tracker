"""Core tracking logic for day phases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_SUN_ENTITY,
    DIRECTION_FALLING,
    DIRECTION_RISING,
    LUX_OPERATOR_AND,
)


@dataclass(slots=True)
class PhaseDefinition:
    name: str
    elevation_trigger: float
    direction: str
    fallback_time: str
    time_max: str | None = None
    lux_entity: str | None = None
    lux_threshold: float | None = None
    lux_operator: str = LUX_OPERATOR_AND


class DayPhaseTracker:
    """Compute current phase and metadata."""

    def __init__(
        self,
        hass: HomeAssistant,
        phases: list[dict],
        master_phases: dict[str, list[str]],
        sun_entity: str = DEFAULT_SUN_ENTITY,
    ):
        self.hass = hass
        self.sun_entity = sun_entity
        self.phases = [
            PhaseDefinition(
                name=item["name"],
                elevation_trigger=float(item["elevation_trigger"]),
                direction=item["direction"],
                fallback_time=item["fallback_time"],
                time_max=item.get("time_max"),
                lux_entity=item.get("lux_entity"),
                lux_threshold=(
                    float(item["lux_threshold"])
                    if item.get("lux_threshold") is not None
                    else None
                ),
                lux_operator=item.get("lux_operator", LUX_OPERATOR_AND),
            )
            for item in phases
        ]
        self.master_phases = master_phases
        self.today_hits: dict[str, str | None] = {phase.name: None for phase in self.phases}
        self._today_date = dt_util.now().date()

    @property
    def lux_entities(self) -> list[str]:
        """Unique lux sensor entity IDs used across all phases."""
        return list({p.lux_entity for p in self.phases if p.lux_entity})

    def _parse_clock(self, value: str, now: datetime) -> datetime:
        # Accepts both "HH:MM" and "HH:MM:SS" (TimeSelector returns HH:MM:SS)
        parts = value.split(":")
        return now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)

    def _is_rising(self, now: datetime) -> bool:
        sun = self.hass.states.get(self.sun_entity)
        if not sun:
            return True
        next_noon_raw = sun.attributes.get("next_noon")
        if not next_noon_raw:
            return True

        next_noon = dt_util.parse_datetime(next_noon_raw)
        if next_noon is None:
            return True
        local_noon = dt_util.as_local(next_noon)
        # next_noon is today's noon if we're before noon (rising),
        # or tomorrow's noon if we're past noon (falling).
        return local_noon.date() == now.date()

    def _phase_matches_elevation(self, phase: PhaseDefinition, elevation: float, is_rising: bool) -> bool:
        if phase.direction == DIRECTION_RISING:
            if is_rising and elevation >= phase.elevation_trigger:
                return True
            return (not is_rising) and elevation >= phase.elevation_trigger

        if phase.direction == DIRECTION_FALLING:
            return (not is_rising) and elevation <= phase.elevation_trigger

        return False

    def _phase_matches_lux(self, phase: PhaseDefinition) -> bool:
        """Return True when the phase's lux condition is satisfied."""
        if not phase.lux_entity or phase.lux_threshold is None:
            return True
        lux_state = self.hass.states.get(phase.lux_entity)
        if not lux_state:
            return False
        try:
            return float(lux_state.state) <= phase.lux_threshold
        except (ValueError, TypeError):
            return False

    def calculate(self) -> dict:
        """Calculate the active phase and attributes."""
        now = dt_util.now()
        if now.date() != self._today_date:
            self.today_hits = {phase.name: None for phase in self.phases}
            self._today_date = now.date()

        sun = self.hass.states.get(self.sun_entity)
        elevation = float(sun.attributes.get("elevation", 0.0)) if sun else 0.0
        is_rising = self._is_rising(now)

        matched = self.phases[0]
        trigger = f"fallback >= {matched.fallback_time}"

        for phase in self.phases:
            # Hard time ceiling: skip phase entirely if past time_max
            if phase.time_max:
                time_max_dt = self._parse_clock(phase.time_max, now)
                if now >= time_max_dt:
                    continue

            fallback_dt = self._parse_clock(phase.fallback_time, now)

            # Elevation condition
            elev_ok = self._phase_matches_elevation(phase, elevation, is_rising)

            # Combine elevation with optional lux condition
            if phase.lux_entity:
                lux_ok = self._phase_matches_lux(phase)
                if phase.lux_operator == LUX_OPERATOR_AND:
                    signal = elev_ok and lux_ok
                else:  # OR
                    signal = elev_ok or lux_ok
            else:
                signal = elev_ok

            if signal:
                matched = phase
                comparator = ">=" if phase.direction == DIRECTION_RISING else "<="
                trig = f"elevation {comparator} {phase.elevation_trigger}°"
                if phase.lux_entity:
                    trig += f" {phase.lux_operator.upper()} lux <= {phase.lux_threshold}"
                trigger = trig
            elif now >= fallback_dt:
                matched = phase
                trigger = f"fallback >= {phase.fallback_time}"

        if self.today_hits.get(matched.name) is None:
            self.today_hits[matched.name] = now.strftime("%H:%M")

        idx = self.phases.index(matched)
        next_phase = self.phases[(idx + 1) % len(self.phases)]
        next_fallback = self._parse_clock(next_phase.fallback_time, now)
        if next_fallback <= now:
            next_fallback = next_fallback + timedelta(days=1)

        result = {
            "state": matched.name,
            "elevation": round(elevation, 2),
            "phase_index": idx + 1,
            "phase_count": len(self.phases),
            "current_phase_start": self.today_hits[matched.name],
            "current_phase_trigger": trigger,
            "next_phase": next_phase.name,
            "next_phase_estimated": next_fallback.strftime("%H:%M"),
            "today": self.today_hits.copy(),
        }

        for master_name, children in self.master_phases.items():
            if matched.name in children:
                result["master"] = {
                    "name": master_name,
                    "sub_phase": matched.name,
                    "phases_in_group": children,
                }
                break

        return result
