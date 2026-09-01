"""Sensors for Dreame A2."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .const import CONSUMABLE_MAX, STATE_LABELS
from .entity import DreameEntity


def _consumable_pct(data: dict, index: int, max_min: int):
    used = data.get("consumables") or []
    if index >= len(used):
        return None
    return max(0, min(100, round(100 - used[index] / max_min * 100)))


def _since(data: dict):
    start = (data.get("totals") or {}).get("start")
    return datetime.fromtimestamp(start, tz=timezone.utc) if start else None


@dataclass(frozen=True, kw_only=True)
class DreameSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], object]


SENSORS: tuple[DreameSensorDescription, ...] = (
    DreameSensorDescription(
        key="battery", translation_key="battery",
        device_class=SensorDeviceClass.BATTERY, native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("status", {}).get("battery"),
    ),
    DreameSensorDescription(
        key="state", translation_key="state",
        device_class=SensorDeviceClass.ENUM, options=list(STATE_LABELS.values()),
        value_fn=lambda d: STATE_LABELS.get(d.get("status", {}).get("state_code")),
    ),
    DreameSensorDescription(
        key="area_mowed", translation_key="area_mowed",
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("status", {}).get("area_mowed"),
    ),
    DreameSensorDescription(
        key="area_total", translation_key="area_total",
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        value_fn=lambda d: d.get("status", {}).get("area_total"),
    ),
    DreameSensorDescription(
        key="session_time", translation_key="session_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda d: d.get("status", {}).get("time_elapsed"),
    ),
    DreameSensorDescription(
        key="lifetime_area", translation_key="lifetime_area",
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: (d.get("totals") or {}).get("area"),
    ),
    DreameSensorDescription(
        key="lifetime_time", translation_key="lifetime_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: (d.get("totals") or {}).get("time"),
    ),
    DreameSensorDescription(
        key="session_count", translation_key="session_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: (d.get("totals") or {}).get("count"),
    ),
    DreameSensorDescription(
        key="in_service_since", translation_key="in_service_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_since,
    ),
    DreameSensorDescription(
        key="blade_life", translation_key="blade_life",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _consumable_pct(d, 0, CONSUMABLE_MAX["blade"]),
    ),
    DreameSensorDescription(
        key="brush_life", translation_key="brush_life",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _consumable_pct(d, 1, CONSUMABLE_MAX["brush"]),
    ),
    DreameSensorDescription(
        key="maintenance_life", translation_key="maintenance_life",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _consumable_pct(d, 2, CONSUMABLE_MAX["maintenance"]),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DreameSensor(coordinator, desc) for desc in SENSORS)


class DreameSensor(DreameEntity, SensorEntity):
    entity_description: DreameSensorDescription

    def __init__(self, coordinator, desc: DreameSensorDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data or {})
