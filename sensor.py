"""Sensor platform for FNB58."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FNB58Coordinator
from .const import CONF_ADDRESS, DEVICE_MODEL, DEVICE_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FNB58Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FNB58VoltageSensor(coordinator, entry),
            FNB58CurrentSensor(coordinator, entry),
            FNB58PowerSensor(coordinator, entry),
            FNB58EnergySensor(coordinator, entry),
            FNB58CapacitySensor(coordinator, entry),
        ]
    )


class FNB58SensorBase(SensorEntity):
    """Base class for FNB58 sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(self, coordinator: FNB58Coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_ADDRESS])},
            name=DEVICE_NAME,
            manufacturer="FNIRSI",
            model=DEVICE_MODEL,
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class FNB58LiveSensorBase(FNB58SensorBase):
    """Live V/I/P — available when connected or showing last reading."""

    @property
    def available(self) -> bool:
        return self._coordinator.is_connected or self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        if self._coordinator.is_connected:
            return {}
        if self.native_value is not None:
            return {"connection": "disconnected"}
        return {}


class FNB58IntegratedSensorBase(FNB58SensorBase):
    """Sensors that stay available with persisted totals when disconnected."""

    @property
    def available(self) -> bool:
        return True


class FNB58VoltageSensor(FNB58LiveSensorBase):
    _attr_name = "Voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_voltage"

    @property
    def native_value(self):
        return self._coordinator.voltage


class FNB58CurrentSensor(FNB58LiveSensorBase):
    _attr_name = "Current"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_current"

    @property
    def native_value(self):
        return self._coordinator.current


class FNB58PowerSensor(FNB58LiveSensorBase):
    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_power"

    @property
    def native_value(self):
        return self._coordinator.power


class FNB58EnergySensor(FNB58IntegratedSensorBase):
    _attr_name = "Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_energy"

    @property
    def native_value(self):
        return self._coordinator.energy_wh


class FNB58CapacitySensor(FNB58IntegratedSensorBase):
    _attr_name = "Capacity"
    _attr_native_unit_of_measurement = "Ah"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_capacity"

    @property
    def native_value(self):
        return self._coordinator.capacity_ah
