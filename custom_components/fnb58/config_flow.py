"""Config flow for the FNB58 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DEVICE_NAME, DISCOVERY_NAME_PREFIX, DOMAIN


class FNB58ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FNB58."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialise the flow."""
        self._discovered: dict[str, str] = {}  # address -> advertised name

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a Bluetooth discovery."""
        if not discovery_info.connectable:
            return self.async_abort(reason="not_connectable")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        name = discovery_info.name or discovery_info.address
        self._discovered[discovery_info.address] = name
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup of a discovered meter."""
        address = self.unique_id
        assert address is not None
        if user_input is not None:
            return self._async_create_entry(address)

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovered[address]},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manually initiated flow."""
        if not self._discovered:
            for info in async_discovered_service_info(self.hass, connectable=True):
                if info.name and info.name.startswith(DISCOVERY_NAME_PREFIX):
                    self._discovered[info.address] = info.name

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._async_create_entry(address)

        if self._discovered:
            options = {
                address: f"{name} ({address})"
                for address, name in self._discovered.items()
            }
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)})
        else:
            # Nothing advertising right now; let the user type a known address.
            schema = vol.Schema({vol.Required(CONF_ADDRESS): str})

        return self.async_show_form(step_id="user", data_schema=schema)

    def _async_create_entry(self, address: str) -> ConfigFlowResult:
        """Create the config entry for a meter address."""
        return self.async_create_entry(title=DEVICE_NAME, data={CONF_ADDRESS: address})
