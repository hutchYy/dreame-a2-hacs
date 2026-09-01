"""Binary sensors for Dreame A2."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .const import STATE_CHARGING_PENDING, STATE_DOCKED, STATE_ERROR
from .entity import DreameEntity


@dataclass(frozen=True, kw_only=True)
class DreameBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict], bool]


BINARY_SENSORS: tuple[DreameBinaryDescription, ...] = (
    DreameBinaryDescription(
        key="online", translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: bool(d.get("status", {}).get("online")),
    ),
    DreameBinaryDescription(
        key="problem", translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("status", {}).get("state_code") == STATE_ERROR,
    ),
    DreameBinaryDescription(
        key="charging", translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.get("status", {}).get("state_code") in (STATE_DOCKED, STATE_CHARGING_PENDING),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DreameBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class DreameBinarySensor(DreameEntity, BinarySensorEntity):
    entity_description: DreameBinaryDescription

    def __init__(self, coordinator, desc: DreameBinaryDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def available(self) -> bool:
        # connectivity should report even when offline
        if self.entity_description.key == "online":
            return self.coordinator.last_update_success
        return super().available
