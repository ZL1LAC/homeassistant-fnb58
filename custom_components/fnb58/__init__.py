"""FNB58 BLE integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONNECT_TIMEOUT,
    DEVICE_NAME,
    DOMAIN,
    INIT_COMMANDS,
    KEY_CAPACITY,
    KEY_ENERGY,
    MAX_SAMPLE_INTERVAL,
    NOTIFY_CHARACTERISTIC,
    RECONNECT_MAX_DELAY,
    RECONNECT_MIN_DELAY,
    WRITE_CHARACTERISTIC,
)
from .parser import FNB58Reading, parse_notification

if TYPE_CHECKING:
    from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]

type FNB58ConfigEntry = ConfigEntry[FNB58Coordinator]

# Failures expected in normal operation: the meter is off, out of range, already
# claimed by USB, or the adapter dropped the link. Anything else propagates.
_EXPECTED_BLE_ERRORS = (BleakError, OSError, TimeoutError)

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


async def async_migrate_entry(hass: HomeAssistant, entry: FNB58ConfigEntry) -> bool:
    """Migrate an older config entry."""
    if entry.minor_version < 2:
        # One-off registry cleanup that used to run on every single setup.
        _async_remove_stale_entities(hass, entry)
        hass.config_entries.async_update_entry(entry, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FNB58ConfigEntry) -> bool:
    """Set up FNB58 from a config entry."""
    coordinator = FNB58Coordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # ConfigEntryNotReady is deliberately not raised: this meter is expected to be
    # powered off much of the time, so the entry loads and the live entities report
    # unavailable until the Bluetooth scanner sees it.
    coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FNB58ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unload_ok


class FNB58Coordinator(DataUpdateCoordinator[FNB58Reading | None]):
    """Manages the BLE connection and parsed data for one FNB58.

    Push-only: there is no polling. BLE notifications drive
    ``async_set_updated_data``, and connect/disconnect drive
    ``async_update_listeners`` so entity availability follows the link.
    """

    def __init__(self, hass: HomeAssistant, entry: FNB58ConfigEntry) -> None:
        """Initialise the coordinator for one meter."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DEVICE_NAME,
            update_interval=None,
        )
        self._entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._stopped = False
        self._connect_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._remove_bt_callback: Callable[[], None] | None = None
        self._last_sample_monotonic: float | None = None

        # Host-side integrated totals, split into a restored base and what this
        # session has accumulated. Keeping them apart means a restore arriving
        # after the first notifications cannot discard those samples.
        self.energy_wh_base = 0.0
        self.capacity_ah_base = 0.0
        self.energy_wh_session = 0.0
        self.capacity_ah_session = 0.0
        self._restored: set[str] = set()

        # Diagnostics
        self.packets_accepted = 0
        self.packets_rejected = 0
        self.last_raw_packet: str | None = None
        self.last_connected: datetime | None = None
        self.last_disconnected: datetime | None = None

    @property
    def is_connected(self) -> bool:
        """Return True when the BLE client is connected."""
        return self._client is not None and self._client.is_connected

    @property
    def voltage(self) -> float | None:
        """Return the last measured voltage."""
        return self.data.voltage if self.data else None

    @property
    def current(self) -> float | None:
        """Return the last measured current."""
        return self.data.current if self.data else None

    @property
    def power(self) -> float | None:
        """Return the last measured power."""
        return self.data.power if self.data else None

    @property
    def energy_wh(self) -> float:
        """Return the running energy total in watt-hours."""
        return self.energy_wh_base + self.energy_wh_session

    @property
    def capacity_ah(self) -> float:
        """Return the running capacity total in amp-hours."""
        return self.capacity_ah_base + self.capacity_ah_session

    @callback
    def async_restore_total(self, key: str, value: float) -> None:
        """Seed a total from its entity's restored state. First call wins."""
        if key in self._restored:
            return
        self._restored.add(key)
        if key == KEY_ENERGY:
            self.energy_wh_base = value
        elif key == KEY_CAPACITY:
            self.capacity_ah_base = value

    @callback
    def async_reset_totals(self) -> None:
        """Zero both host-side totals. Nothing is written to the meter."""
        self.energy_wh_base = 0.0
        self.capacity_ah_base = 0.0
        self.energy_wh_session = 0.0
        self.capacity_ah_session = 0.0
        # Mark both as restored so re-adding an entity cannot resurrect the old
        # value from its last recorded state.
        self._restored = {KEY_ENERGY, KEY_CAPACITY}
        self.async_update_listeners()

    @callback
    def async_start(self) -> None:
        """Register for Bluetooth availability and attempt an initial connect."""

        @callback
        def _async_bluetooth_callback(
            _service_info: bluetooth.BluetoothServiceInfoBleak,
            _change: bluetooth.BluetoothChange,
        ) -> None:
            if self._stopped or self.is_connected:
                return
            self._async_spawn_connect()

        self._remove_bt_callback = bluetooth.async_register_callback(
            self.hass,
            _async_bluetooth_callback,
            {"address": self.address, "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        self._async_spawn_connect()

    async def async_stop(self) -> None:
        """Cancel background work and disconnect."""
        self._stopped = True
        if self._remove_bt_callback:
            self._remove_bt_callback()
            self._remove_bt_callback = None
        for task in (self._connect_task, self._reconnect_task):
            if task and not task.done():
                task.cancel()
        self._connect_task = None
        self._reconnect_task = None
        await self.async_disconnect()

    @callback
    def _async_spawn_connect(self) -> None:
        """Fire a one-shot best-effort connect attempt in the background.

        Background tasks are excluded from ``async_block_till_done``, so a meter
        that is switched off cannot stall startup or an entry reload.
        """
        if self._connect_task and not self._connect_task.done():
            return
        self._connect_task = self._entry.async_create_background_task(
            self.hass,
            self._connect_on_advertisement(),
            name=f"{DOMAIN} connect {self.address}",
            eager_start=True,
        )

    async def _connect_on_advertisement(self) -> None:
        """Best-effort connect when the device is seen by the HA scanner."""
        try:
            await self.async_connect()
        except _EXPECTED_BLE_ERRORS as err:
            _LOGGER.debug(
                "FNB58 at %s not connectable yet (%s); will retry when seen again",
                self.address,
                err,
            )

    async def async_connect(self) -> None:
        """Connect, send the stream-start handshake, enable notifications."""
        async with self._connect_lock:
            if self._stopped or self.is_connected:
                return

            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise BleakError(
                    f"FNB58 ({self.address}) not found by the HA Bluetooth scanner"
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
                # Broad on purpose: whatever went wrong, do not leak a half-open
                # client. The error is re-raised for the caller to classify.
                if client is not None and client.is_connected:
                    await client.disconnect()
                raise

            self._client = client
            self.last_connected = dt_util.utcnow()
            _LOGGER.info("Connected to FNB58 at %s", self.address)
            self.async_update_listeners()

    async def async_disconnect(self) -> None:
        """Disconnect the BLE client if connected."""
        client, self._client = self._client, None
        if client and client.is_connected:
            try:
                await client.disconnect()
            except _EXPECTED_BLE_ERRORS as err:
                _LOGGER.debug(
                    "Error disconnecting from FNB58 at %s: %s", self.address, err
                )

    def _on_notification(self, _sender, data: bytearray) -> None:
        """Handle a BLE notification (may run on the Bleak callback thread)."""
        self.hass.loop.call_soon_threadsafe(self._process_notification, bytes(data))

    @callback
    def _process_notification(self, data: bytes) -> None:
        """Parse a notification on the Home Assistant event loop."""
        self.last_raw_packet = data.hex()
        reading = parse_notification(data)
        if reading is None:
            self.packets_rejected += 1
            return
        self.packets_accepted += 1

        now = time.monotonic()
        if self._last_sample_monotonic is not None:
            elapsed = now - self._last_sample_monotonic
            if 0 < elapsed <= MAX_SAMPLE_INTERVAL:
                elapsed_hours = elapsed / 3600.0
                # Forward flow only, so both totals stay monotonic and remain
                # valid for SensorStateClass.TOTAL_INCREASING. Counting reverse
                # current would make each dip look like a meter reset to
                # long-term statistics.
                if reading.power > 0:
                    self.energy_wh_session += reading.power * elapsed_hours
                if reading.current > 0:
                    self.capacity_ah_session += reading.current * elapsed_hours
        self._last_sample_monotonic = now

        self.async_set_updated_data(reading)

    def _on_disconnected(self, _client: BleakClient) -> None:
        """Handle BLE disconnection (may run on the Bleak callback thread)."""
        self.hass.loop.call_soon_threadsafe(self._async_handle_disconnected)

    @callback
    def _async_handle_disconnected(self) -> None:
        """Mark the meter offline and start reconnect attempts."""
        _LOGGER.warning("FNB58 at %s disconnected - scheduling reconnect", self.address)
        self._client = None
        self._last_sample_monotonic = None
        self.last_disconnected = dt_util.utcnow()
        self.async_update_listeners()
        if not self._stopped:
            self._async_start_reconnect()

    @callback
    def _async_start_reconnect(self) -> None:
        """Start a reconnect loop unless one is already running."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self._entry.async_create_background_task(
            self.hass,
            self._async_reconnect(),
            name=f"{DOMAIN} reconnect {self.address}",
            eager_start=True,
        )

    async def _async_reconnect(self) -> None:
        """Retry connecting with capped exponential backoff until stopped."""
        delay = RECONNECT_MIN_DELAY
        while not self._stopped:
            await asyncio.sleep(delay)
            if self._stopped or self.is_connected:
                return
            try:
                await self.async_connect()
            except _EXPECTED_BLE_ERRORS as err:
                _LOGGER.debug(
                    "FNB58 reconnect attempt failed (%s), retrying in %ss", err, delay
                )
            else:
                _LOGGER.info("FNB58 reconnected at %s", self.address)
                return
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
