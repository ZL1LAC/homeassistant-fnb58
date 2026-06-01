"""FNB58 BLE integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ADDRESS,
    CONNECT_TIMEOUT,
    DEVICE_NAME,
    DOMAIN,
    INIT_COMMANDS,
    MAX_SAMPLE_INTERVAL,
    NOTIFY_CHARACTERISTIC,
    RECONNECT_MAX_DELAY,
    RECONNECT_MIN_DELAY,
    WRITE_CHARACTERISTIC,
)
from .parser import parse_notification

if TYPE_CHECKING:
    from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]

# Entities removed in earlier versions (not provided over BLE / read-only scope).
_REMOVED_ENTITY_SUFFIXES = (
    "_dp_voltage",
    "_dn_voltage",
    "_temperature",
    "_debug_packet_logging",
    "_ble_packets_logged",
    "_last_ble_notify",
    "_last_command",
    "_clear_device_records",
    "_stop_protocol_trigger",
    "_reset_integrators",
    "_protocol_trigger",
)


def _async_remove_stale_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove orphaned entities left from older integration versions."""
    registry = er.async_get(hass)
    address = entry.data[CONF_ADDRESS]
    removed_unique_ids = {f"{address}{suffix}" for suffix in _REMOVED_ENTITY_SUFFIXES}
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id in removed_unique_ids:
            registry.async_remove(entity_entry.entity_id)
            _LOGGER.info(
                "Removed stale FNB58 entity %s (no longer supported)",
                entity_entry.entity_id,
            )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FNB58 from a config entry."""
    _async_remove_stale_entities(hass, entry)
    if entry.title != DEVICE_NAME:
        hass.config_entries.async_update_entry(entry, title=DEVICE_NAME)
    coordinator = FNB58Coordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start()
    entry.async_on_unload(coordinator.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unload_ok


class FNB58Coordinator:
    """Manages the BLE connection and parsed data for one FNB58."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self.address = entry.data[CONF_ADDRESS]
        self._client: BleakClient | None = None
        self._listeners: list = []
        self._connect_lock = asyncio.Lock()
        self._stopped = False
        self._reconnect_task: asyncio.Task | None = None
        self._remove_bt_callback: Callable[[], None] | None = None
        self._last_sample_monotonic: float | None = None
        self.voltage: float | None = None
        self.current: float | None = None
        self.power: float | None = None
        self.energy_wh: float = 0.0
        self.capacity_ah: float = 0.0

    @property
    def is_connected(self) -> bool:
        """Return True when the BLE client is connected."""
        return self._client is not None and self._client.is_connected

    def register_listener(self, callback) -> None:
        self._listeners.append(callback)

    def unregister_listener(self, callback) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            cb()

    async def async_start(self) -> None:
        """Register for Bluetooth availability and attempt an initial connect."""
        @callback
        def _async_bluetooth_callback(
            _service_info: bluetooth.BluetoothServiceInfoBleak,
            _change: bluetooth.BluetoothChange,
        ) -> None:
            if self._stopped or self.is_connected:
                return
            self.hass.async_create_task(self._connect_on_advertisement())

        self._remove_bt_callback = bluetooth.async_register_callback(
            self.hass,
            _async_bluetooth_callback,
            {"address": self.address, "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        self.hass.async_create_task(self._connect_on_advertisement())

    async def async_stop(self) -> None:
        """Cancel background tasks and disconnect."""
        self._stopped = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._remove_bt_callback:
            self._remove_bt_callback()
            self._remove_bt_callback = None
        await self.async_disconnect()

    async def _connect_on_advertisement(self) -> None:
        """Best-effort connect when the device is seen by the HA scanner."""
        try:
            await self.async_connect()
        except Exception:
            _LOGGER.debug(
                "FNB58 at %s not connectable yet (will retry when seen again)",
                self.address,
            )

    async def async_connect(self) -> None:
        """Connect, send init commands, enable notifications."""
        from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
        from homeassistant.components.bluetooth import async_ble_device_from_address

        async with self._connect_lock:
            if self._stopped:
                return
            if self.is_connected:
                return

            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise RuntimeError(
                    f"FNB58 ({self.address}) not found by HA Bluetooth scanner"
                )

            client = None
            try:
                client = await asyncio.wait_for(
                    establish_connection(
                        BleakClientWithServiceCache,
                        ble_device,
                        ble_device.name or DEVICE_NAME,
                        disconnected_callback=self._on_disconnected,
                        ble_device_callback=lambda: (
                            async_ble_device_from_address(
                                self.hass, self.address, connectable=True
                            )
                            or ble_device
                        ),
                    ),
                    timeout=CONNECT_TIMEOUT,
                )
                for cmd in INIT_COMMANDS:
                    await client.write_gatt_char(WRITE_CHARACTERISTIC, cmd)
                await client.start_notify(NOTIFY_CHARACTERISTIC, self._on_notification)
            except Exception:
                if client is not None and client.is_connected:
                    await client.disconnect()
                raise

            self._client = client
            _LOGGER.info("Connected to FNB58 at %s", self.address)
            self._notify_listeners()

    async def async_disconnect(self) -> None:
        """Disconnect the BLE client if connected."""
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    def _on_notification(self, _sender, data: bytearray) -> None:
        """Handle BLE notification (may run on the Bleak callback thread)."""
        self.hass.loop.call_soon_threadsafe(
            lambda: self._process_notification(bytearray(data))
        )

    def _process_notification(self, data: bytearray) -> None:
        """Parse a notification on the Home Assistant event loop."""
        reading = parse_notification(data)
        if reading is None:
            return

        now = time.monotonic()
        if self._last_sample_monotonic is not None:
            dt = now - self._last_sample_monotonic
            if 0 < dt <= MAX_SAMPLE_INTERVAL:
                dt_hours = dt / 3600.0
                self.energy_wh += reading.power * dt_hours
                self.capacity_ah += reading.current * dt_hours
        self._last_sample_monotonic = now

        self.voltage = reading.voltage
        self.current = reading.current
        self.power = reading.power
        self._notify_listeners()

    def _on_disconnected(self, _client) -> None:
        _LOGGER.warning("FNB58 at %s disconnected – scheduling reconnect", self.address)
        self._client = None
        self._last_sample_monotonic = None
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._handle_disconnected())
        )

    async def _handle_disconnected(self) -> None:
        """Update availability and start reconnect attempts."""
        self._notify_listeners()
        if not self._stopped:
            self._start_reconnect()

    def _start_reconnect(self) -> None:
        """Start a reconnect loop unless one is already running."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self.hass.async_create_task(self._async_reconnect())

    async def _async_reconnect(self) -> None:
        """Retry connecting with capped exponential backoff until stopped."""
        delay = RECONNECT_MIN_DELAY
        while not self._stopped:
            await asyncio.sleep(delay)
            if self._stopped or self.is_connected:
                return
            try:
                await self.async_connect()
                _LOGGER.info("FNB58 reconnected at %s", self.address)
                return
            except Exception:
                _LOGGER.debug(
                    "FNB58 reconnect attempt failed, retrying in %ss", delay
                )
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
