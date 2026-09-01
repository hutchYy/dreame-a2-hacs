"""Sensors for Dreame A2."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
from .const import STATE_LABELS
from .entity import DreameEntity


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
