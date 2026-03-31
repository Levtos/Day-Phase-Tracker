"""Core tracking logic for day phases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DIRECTION_FALLING, DIRECTION_RISING


@dataclass(slots=True)
class PhaseDefinition:
    name: str
    elevation_trigger: float
    direction: str
    fallback_time: str


class DayPhaseTracker:
    """Compute current phase and metadata."""

    def __init__(self, hass: HomeAssistant, phases: list[dict], master_phases: dict[str, list[str]]):
        self.hass = hass
        self.phases = [
            PhaseDefinition(
                name=item["name"],
                elevation_trigger=float(item["elevation_trigger"]),
                direction=item["direction"],
                fallback_time=item["fallback_time"],
            )
            for item in phases
        ]
        self.master_phases = master_phases
        self.today_hits: dict[str, str | None] = {phase.name: None for phase in self.phases}
        self._today_date = dt_util.now().date()

    def _parse_clock(self, value: str, now: datetime) -> datetime:
        hour, minute = value.split(":", 1)
        return now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)

    def _is_rising(self, now: datetime) -> bool:
        sun = self.hass.states.get("sun.sun")
        if not sun:
            return True
        next_noon_raw = sun.attributes.get("next_noon")
        if not next_noon_raw:
            return True

        next_noon = dt_util.parse_datetime(next_noon_raw)
        if next_noon is None:
            return True
        local_noon = dt_util.as_local(next_noon)
        previous_noon = local_noon - timedelta(days=1)
        return previous_noon <= now < local_noon

    def _phase_matches_elevation(self, phase: PhaseDefinition, elevation: float, is_rising: bool) -> bool:
        if phase.direction == DIRECTION_RISING:
            if is_rising and elevation >= phase.elevation_trigger:
                return True
            return (not is_rising) and elevation >= phase.elevation_trigger

        if phase.direction == DIRECTION_FALLING:
            return (not is_rising) and elevation <= phase.elevation_trigger

        return False

    def calculate(self) -> dict:
        """Calculate the active phase and attributes."""
        now = dt_util.now()
        if now.date() != self._today_date:
            self.today_hits = {phase.name: None for phase in self.phases}
            self._today_date = now.date()

        sun = self.hass.states.get("sun.sun")
        elevation = float(sun.attributes.get("elevation", 0.0)) if sun else 0.0
        is_rising = self._is_rising(now)

        matched = self.phases[0]
        trigger = f"fallback >= {matched.fallback_time}"

        for phase in self.phases:
            fallback_dt = self._parse_clock(phase.fallback_time, now)
            if self._phase_matches_elevation(phase, elevation, is_rising):
                matched = phase
                comparator = ">=" if phase.direction == DIRECTION_RISING else "<="
                trigger = f"elevation {comparator} {phase.elevation_trigger}°"
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
