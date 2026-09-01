"""Numbers for Dreame A2 (cut height, obstacle thresholds, volume)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .api import DreameApi
from .entity import DreameEntity


@dataclass(frozen=True, kw_only=True)
class DreameNumberDescription(NumberEntityDescription):
    value_fn: Callable[[dict], float | None]
    set_fn: Callable[[DreameApi, float], Awaitable]


NUMBERS: tuple[DreameNumberDescription, ...] = (
    DreameNumberDescription(
        key="cut_height", translation_key="cut_height",
        native_min_value=3.0, native_max_value=7.0, native_step=0.1,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS, mode=NumberMode.SLIDER,
        value_fn=lambda d: (d.get("settings", {}).get("cut_height") or 0) / 10 or None,
        set_fn=lambda api, v: api.set_mowing_settings({"cut_height": round(v * 10)}),
    ),
    DreameNumberDescription(
        key="obstacle_height", translation_key="obstacle_height",
        native_min_value=5, native_max_value=20, native_step=5,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS, mode=NumberMode.SLIDER,
        value_fn=lambda d: d.get("settings", {}).get("obstacle_height"),
        set_fn=lambda api, v: api.set_mowing_settings({"obstacle_height": int(v)}),
    ),
    DreameNumberDescription(
        key="obstacle_distance", translation_key="obstacle_distance",
        native_min_value=10, native_max_value=20, native_step=5,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS, mode=NumberMode.SLIDER,
        value_fn=lambda d: d.get("settings", {}).get("obstacle_distance"),
        set_fn=lambda api, v: api.set_mowing_settings({"obstacle_distance": int(v)}),
    ),
    DreameNumberDescription(
        key="volume", translation_key="volume",
        native_min_value=0, native_max_value=100, native_step=5,
        native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER,
        value_fn=lambda d: d.get("cfg", {}).get("VOL"),
        set_fn=lambda api, v: api.set_volume(int(v)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DreameNumber(coordinator, desc) for desc in NUMBERS)


class DreameNumber(DreameEntity, NumberEntity):
    entity_description: DreameNumberDescription

    def __init__(self, coordinator, desc: DreameNumberDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data or {})

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.coordinator.api, value)
        await self.coordinator.async_request_refresh()
