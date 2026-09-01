"""Buttons for Dreame A2 (find, edge mow, stop, refresh map)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .coordinator import DreameCoordinator
from .entity import DreameEntity


@dataclass(frozen=True, kw_only=True)
class DreameButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[DreameCoordinator], Awaitable]


BUTTONS: tuple[DreameButtonDescription, ...] = (
    DreameButtonDescription(
        key="find_robot", translation_key="find_robot",
        press_fn=lambda c: c.api.find_robot(),
    ),
    DreameButtonDescription(
        key="edge_mow", translation_key="edge_mow",
        press_fn=lambda c: c.api.edge_mowing(),
    ),
    DreameButtonDescription(
        key="stop", translation_key="stop",
        press_fn=lambda c: c.api.stop_mowing(),
    ),
    DreameButtonDescription(
        key="refresh_map", translation_key="refresh_map",
        press_fn=lambda c: c.async_force_map_refresh(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DreameButton(coordinator, desc) for desc in BUTTONS)


class DreameButton(DreameEntity, ButtonEntity):
    entity_description: DreameButtonDescription

    def __init__(self, coordinator, desc: DreameButtonDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
        if self.entity_description.key != "refresh_map":
            await self.coordinator.async_request_refresh()
