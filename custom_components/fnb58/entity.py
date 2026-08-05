"""Shared entity base for the FNB58 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FNB58Coordinator
from .const import DEVICE_MANUFACTURER, DEVICE_MODEL, DEVICE_NAME, DOMAIN


class FNB58Entity(CoordinatorEntity[FNB58Coordinator]):
    """Base entity tying every FNB58 entity to the one meter device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FNB58Coordinator, key: str) -> None:
        """Initialise the entity for a given data key."""
        super().__init__(coordinator)
        address = coordinator.address
        # The unique_id shape is load-bearing: existing installs depend on it.
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name=DEVICE_NAME,
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )
