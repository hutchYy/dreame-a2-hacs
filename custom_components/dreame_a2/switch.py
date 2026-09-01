"""Switches for Dreame A2 (mowing preferences + device settings)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .api import DreameApi
from .entity import DreameEntity


@dataclass(frozen=True, kw_only=True)
class DreameSwitchDescription(SwitchEntityDescription):
    value_fn: Callable[[dict], bool]
    set_fn: Callable[[DreameApi, bool], Awaitable]


def _pref(key: str):
    """A mowing-preference toggle backed by set_mowing_settings."""
    return (
        lambda d: bool(d.get("settings", {}).get(key)),
        lambda api, on, k=key: api.set_mowing_settings({k: 1 if on else 0}),
    )


def _cfg(code: str, setter: str):
    """A device-setting toggle backed by getCFG + a dedicated setter."""
    return (
        lambda d, c=code: bool(d.get("cfg", {}).get(c)),
        lambda api, on, s=setter: getattr(api, s)(on),
    )


_PREF_SWITCHES = {
    "edge_auto": "edge_auto",
    "edge_safe": "edge_safe",
    "edgemaster": "cutter_position",
    "edge_obstacle_avoidance": "edge_obstacle_avoidance",
    "lidar_obstacle": "lidar_obstacle",
    "efficient_mode": "efficient_mode",
}

_CFG_SWITCHES = {
    "frost_protect": ("FDP", "set_frost_protect"),
    "weather_adapt": ("WRF", "set_weather_adapt"),
    "pathway_avoidance": ("PATH", "set_pathway_avoidance"),
    "child_lock": ("CLS", "set_child_lock"),
    "daytime_lights": ("DLS", "set_daytime_lights"),
    "auto_recharge_standby": ("STUN", "set_auto_recharge_standby"),
    "ai_photos": ("AOP", "set_ai_photos"),
}


def _build() -> list[DreameSwitchDescription]:
    out: list[DreameSwitchDescription] = []
    for key, pref_key in _PREF_SWITCHES.items():
        vf, sf = _pref(pref_key)
        out.append(DreameSwitchDescription(key=key, translation_key=key, value_fn=vf, set_fn=sf))
    for key, (code, setter) in _CFG_SWITCHES.items():
        vf, sf = _cfg(code, setter)
        out.append(DreameSwitchDescription(key=key, translation_key=key, value_fn=vf, set_fn=sf))
    return out


SWITCHES = _build()


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DreameSwitch(coordinator, desc) for desc in SWITCHES)


class DreameSwitch(DreameEntity, SwitchEntity):
    entity_description: DreameSwitchDescription

    def __init__(self, coordinator, desc: DreameSwitchDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data or {})

    async def async_turn_on(self, **kwargs) -> None:
        await self.entity_description.set_fn(self.coordinator.api, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.entity_description.set_fn(self.coordinator.api, False)
        await self.coordinator.async_request_refresh()
