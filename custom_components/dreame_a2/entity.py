"""Base entity for Dreame A2."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAME
from .coordinator import DreameCoordinator


class DreameEntity(CoordinatorEntity[DreameCoordinator]):
    """Common base: shares device_info and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameCoordinator, key: str) -> None:
        super().__init__(coordinator)
        did = coordinator.entry.data.get("did") or coordinator.entry.entry_id
        self._attr_unique_id = f"{did}_{key}"
        status = (coordinator.data or {}).get("status", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(did))},
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
            name=status.get("name") or "Dreame A2",
        )

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        return bool((self.coordinator.data or {}).get("status", {}).get("online", True))

    @property
    def _status(self) -> dict:
        return (self.coordinator.data or {}).get("status", {}) or {}

    @property
    def _settings(self) -> dict:
        return (self.coordinator.data or {}).get("settings", {}) or {}

    @property
    def _cfg(self) -> dict:
        return (self.coordinator.data or {}).get("cfg", {}) or {}
