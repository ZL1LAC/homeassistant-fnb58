"""Config flow for the FNB58 integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ADDRESS, DEVICE_NAME, DOMAIN


class FNB58ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FNB58."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}  # address -> name

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered[discovery_info.address] = discovery_info.name or discovery_info.address
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the user step."""
        if not self._discovered:
            for info in async_discovered_service_info(self.hass):
                if info.name and info.name.startswith("FNB58"):
                    self._discovered[info.address] = info.name

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=DEVICE_NAME,
                data={CONF_ADDRESS: address},
            )

        if self._discovered:
            options = {
                addr: f"{DEVICE_NAME} ({name})"
                for addr, name in self._discovered.items()
            }
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)})
        else:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): str})

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "note": (
                    "Read-only over Bluetooth: voltage, current, and power (plus "
                    "energy/capacity calculated in Home Assistant). The meter cannot "
                    "be controlled from Home Assistant over BLE. It does not need to "
                    "be on at all times; connect automatically when powered on and in "
                    "range. Unplug USB data when using Bluetooth."
                )
            },
        )
