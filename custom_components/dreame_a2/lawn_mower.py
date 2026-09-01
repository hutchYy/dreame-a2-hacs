"""Lawn mower platform for Dreame A2."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .const import (
    STATE_CHARGING_PENDING,
    STATE_DOCKED,
    STATE_ERROR,
    STATE_MOWING,
    STATE_PAUSED,
    STATE_RETURNING,
)
from .entity import DreameEntity

ACTIVITY_MAP = {
    STATE_MOWING: LawnMowerActivity.MOWING,
    STATE_PAUSED: LawnMowerActivity.PAUSED,
    STATE_RETURNING: LawnMowerActivity.RETURNING,
    STATE_ERROR: LawnMowerActivity.ERROR,
    STATE_CHARGING_PENDING: LawnMowerActivity.DOCKED,
    STATE_DOCKED: LawnMowerActivity.DOCKED,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DreameLawnMower(entry.runtime_data)])

    # Parameterized actions that have no native entity equivalent.
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "mow_zones",
        {vol.Required("zones"): vol.All(cv.ensure_list, [vol.Coerce(int)])},
        "async_mow_zones",
    )
    platform.async_register_entity_service(
        "mow_spot",
        {vol.Required("area"): vol.All(cv.ensure_list, [vol.Coerce(float)])},
        "async_mow_spot",
    )
    platform.async_register_entity_service(
        "patrol_zone_edges",
        {vol.Required("zones"): vol.All(cv.ensure_list, [vol.Coerce(int)])},
        "async_patrol_zone_edges",
    )
    platform.async_register_entity_service(
        "patrol_point",
        {vol.Required("x"): vol.Coerce(int), vol.Required("y"): vol.Coerce(int)},
        "async_patrol_point",
    )


class DreameLawnMower(DreameEntity, LawnMowerEntity):
    """The mower itself."""

    _attr_name = None  # use the device name
    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "mower")

    @property
    def activity(self) -> LawnMowerActivity | None:
        code = self._status.get("state_code")
        return ACTIVITY_MAP.get(code)

    async def async_start_mowing(self) -> None:
        # Resume if paused, otherwise start a fresh whole-lawn job.
        if self._status.get("state_code") == STATE_PAUSED:
            await self.coordinator.api.resume_mowing()
        else:
            await self.coordinator.api.start_mowing()
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        await self.coordinator.api.pause_mowing()
        await self.coordinator.async_request_refresh()

    async def async_dock(self) -> None:
        await self.coordinator.api.dock()
        await self.coordinator.async_request_refresh()

    async def async_mow_zones(self, zones: list[int]) -> None:
        await self.coordinator.api.zone_mowing(zones)
        await self.coordinator.async_request_refresh()

    async def async_mow_spot(self, area: list) -> None:
        await self.coordinator.api.spot_mowing(area)
        await self.coordinator.async_request_refresh()

    async def async_patrol_zone_edges(self, zones: list[int]) -> None:
        """Patrol the boundary of the given zones (built from the active map)."""
        INT_MAX = 2147483647
        map_data = (self.coordinator.data or {}).get("map") or {}
        wanted = set(zones)
        edge: list[list[int]] = []
        for z in map_data.get("map", []):
            if z.get("type") == 0 and z.get("id") in wanted:
                edge.extend(p for p in (z.get("data") or []) if p and p[0] != INT_MAX)
        if not edge:
            raise HomeAssistantError(f"No boundary points found for zones {zones}")
        await self.coordinator.api.cruise_edge(edge)
        await self.coordinator.async_request_refresh()

    async def async_patrol_point(self, x: int, y: int) -> None:
        await self.coordinator.api.cruise_point([x, y])
        await self.coordinator.async_request_refresh()
