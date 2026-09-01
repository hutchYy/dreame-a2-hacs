"""Lawn mower platform for Dreame A2."""
from __future__ import annotations

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
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
