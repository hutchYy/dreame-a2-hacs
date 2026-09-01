"""Selects for Dreame A2 (mowing pattern, navigation path, active map)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .entity import DreameEntity

PATTERN_OPTIONS = {"off": 0, "crisscross": 1, "chequerboard": 2}
PATTERN_REVERSE = {v: k for k, v in PATTERN_OPTIONS.items()}

NAV_OPTIONS = {"direct": 0, "smart": 1}
NAV_REVERSE = {v: k for k, v in NAV_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        DreamePatternSelect(coordinator),
        DreameNavPathSelect(coordinator),
        DreameActiveMapSelect(coordinator),
    ])


class DreamePatternSelect(DreameEntity, SelectEntity):
    _attr_translation_key = "cutting_pattern"
    _attr_options = list(PATTERN_OPTIONS)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cutting_pattern")

    @property
    def current_option(self) -> str | None:
        return PATTERN_REVERSE.get(self._settings.get("direction_mode"))

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.api.set_mowing_settings({"direction_mode": PATTERN_OPTIONS[option]})
        await self.coordinator.async_request_refresh()


class DreameNavPathSelect(DreameEntity, SelectEntity):
    _attr_translation_key = "navigation_path"
    _attr_options = list(NAV_OPTIONS)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "navigation_path")

    @property
    def current_option(self) -> str | None:
        return NAV_REVERSE.get(self._cfg.get("PROT"))

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.api._set("PROT", {"value": NAV_OPTIONS[option]})
        await self.coordinator.async_request_refresh()


class DreameActiveMapSelect(DreameEntity, SelectEntity):
    """Choose which stored map the robot uses."""

    _attr_translation_key = "active_map"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "active_map")

    def _maps(self) -> list[dict]:
        return (self.coordinator.data or {}).get("maps", []) or []

    @property
    def options(self) -> list[str]:
        return [f"Map {m['index']}" for m in self._maps()] or ["Map 0"]

    @property
    def current_option(self) -> str | None:
        active = (self.coordinator.data or {}).get("active_map")
        return f"Map {active}" if active is not None else None

    async def async_select_option(self, option: str) -> None:
        idx = int(option.split()[-1])
        await self.coordinator.api.switch_map(idx)
        # Switching maps changes geometry and settings — refresh everything.
        await self.coordinator.async_force_map_refresh()
