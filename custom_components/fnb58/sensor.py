"""Sensor platform for FNB58."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FNB58ConfigEntry, FNB58Coordinator
from .const import (
    KEY_CAPACITY,
    KEY_CURRENT,
    KEY_ENERGY,
    KEY_POWER,
    KEY_VOLTAGE,
    UNIT_AMPERE_HOUR,
)
from .entity import FNB58Entity


@dataclass(frozen=True, kw_only=True)
class FNB58SensorEntityDescription(SensorEntityDescription):
    """Describes an FNB58 sensor."""

    value_fn: Callable[[FNB58Coordinator], float | None]


# Live measurements straight off the BLE stream.
LIVE_SENSORS: tuple[FNB58SensorEntityDescription, ...] = (
    FNB58SensorEntityDescription(
        key=KEY_VOLTAGE,
        translation_key=KEY_VOLTAGE,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda coordinator: coordinator.voltage,
    ),
    FNB58SensorEntityDescription(
        key=KEY_CURRENT,
        translation_key=KEY_CURRENT,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda coordinator: coordinator.current,
    ),
    FNB58SensorEntityDescription(
        key=KEY_POWER,
        translation_key=KEY_POWER,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda coordinator: coordinator.power,
    ),
)

# Totals integrated in Home Assistant, not read from the meter.
TOTAL_SENSORS: tuple[FNB58SensorEntityDescription, ...] = (
    FNB58SensorEntityDescription(
        key=KEY_ENERGY,
        translation_key=KEY_ENERGY,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=4,
        value_fn=lambda coordinator: coordinator.energy_wh,
    ),
    FNB58SensorEntityDescription(
        key=KEY_CAPACITY,
        translation_key=KEY_CAPACITY,
        # No device class: Home Assistant has none for electric charge.
        native_unit_of_measurement=UNIT_AMPERE_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=4,
        value_fn=lambda coordinator: coordinator.capacity_ah,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FNB58ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the FNB58 sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(
                FNB58LiveSensor(coordinator, description)
                for description in LIVE_SENSORS
            ),
            *(
                FNB58TotalSensor(coordinator, description)
                for description in TOTAL_SENSORS
            ),
        ]
    )


class FNB58SensorBase(FNB58Entity, SensorEntity):
    """Common wiring for FNB58 sensors."""

    entity_description: FNB58SensorEntityDescription

    def __init__(
        self,
        coordinator: FNB58Coordinator,
        description: FNB58SensorEntityDescription,
    ) -> None:
        """Initialise the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator)


class FNB58LiveSensor(FNB58SensorBase):
    """A live measurement, which only means anything while connected."""

    @property
    def available(self) -> bool:
        """Return True only while the BLE link is up.

        Reporting the last-seen reading indefinitely after the meter is switched
        off would flat-line history on a value that is no longer being measured.
        """
        return self.coordinator.is_connected


class FNB58TotalSensor(FNB58SensorBase, RestoreSensor):
    """A host-side running total that survives restarts."""

    @property
    def available(self) -> bool:
        """Return True always: a total is meaningful while the meter is off."""
        return True

    async def async_added_to_hass(self) -> None:
        """Seed the coordinator with the total recorded before the restart."""
        # Runs first so the CoordinatorEntity and RestoreEntity chain is wired up
        # before async_get_last_sensor_data is called.
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data is not None and isinstance(last_data.native_value, (int, float)):
            self.coordinator.async_restore_total(
                self.entity_description.key, float(last_data.native_value)
            )
