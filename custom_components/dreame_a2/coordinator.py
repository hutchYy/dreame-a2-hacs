"""Data update coordinator for the Dreame A2 mower."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DreameApi, DreameError
from .const import DEFAULT_SCAN_INTERVAL, MAP_REFRESH_INTERVAL, PARAMS_MAP, STATE_MOWING

_LOGGER = logging.getLogger(__name__)


class DreameCoordinator(DataUpdateCoordinator[dict]):
    """Polls status/settings frequently and the map on a slower cadence."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: DreameApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Dreame A2",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.api = api
        self._map_ts = 0.0
        self._map: dict | None = None
        self._dock = None
        self._pose = None
        self._trail: list | None = None
        self._history: list | None = None

    async def _async_update_data(self) -> dict:
        try:
            status = await self.api.get_status()

            # One MAPL call drives both the map list and the active index, then
            # read the active map's mowing preferences.
            maps = await self.api.get_map_list()
            active_idx = next((m["index"] for m in maps if m["is_current"]),
                              maps[0]["index"] if maps else 0)
            d = await self.api.get_preferences(active_idx)
            settings = {n: d[p] for n, p in PARAMS_MAP.items() if d and p < len(d)}

            cfg = await self.api.get_cfg()
            totals = await self.api.get_totals()
            consumables = await self.api.get_consumables()

            # Robot pose is cheap and useful while active; refresh every cycle.
            try:
                self._pose = await self.api.get_robot_pose()
            except DreameError:
                pass

            # Map geometry is expensive (chunked) — refresh on a slower cadence,
            # but speed up while mowing so the trail and robot marker advance.
            now = time.time()
            mowing = status.get("state_code") == STATE_MOWING
            refresh_after = 25 if mowing else MAP_REFRESH_INTERVAL
            if self._map is None or (now - self._map_ts) > refresh_after:
                try:
                    self._map = await self.api.fetch_map_data()
                    self._dock = await self.api.get_dock_pos()
                    # The mown path (MITRC). Bounded chunk count keeps the
                    # serialized command queue from stalling on huge lawns.
                    self._trail = await self.api.fetch_mowing_trail(max_chunks=200)
                    self._history = await self.api.get_history()
                    self._map_ts = now
                except DreameError as err:
                    _LOGGER.debug("Map refresh failed: %s", err)

            return {
                "status": status,
                "settings": settings,
                "cfg": cfg,
                "totals": totals,
                "consumables": consumables,
                "maps": maps,
                "active_map": active_idx,
                "map": self._map,
                "dock": self._dock,
                "pose": self._pose,
                "trail": self._trail,
                "history": self._history,
            }
        except DreameError as err:
            raise UpdateFailed(str(err)) from err

    async def async_force_map_refresh(self) -> None:
        """Invalidate the cached map so the next update re-fetches it."""
        self._map_ts = 0.0
        await self.async_request_refresh()
