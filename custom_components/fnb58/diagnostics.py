"""Diagnostics support for FNB58."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import FNB58ConfigEntry

TO_REDACT = {CONF_ADDRESS}


def _isoformat(value: datetime | None) -> str | None:
    """Return an ISO timestamp, or None if the event has not happened."""
    return value.isoformat() if value else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FNB58ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    reading = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "connection": {
            "connected": coordinator.is_connected,
            "last_connected": _isoformat(coordinator.last_connected),
            "last_disconnected": _isoformat(coordinator.last_disconnected),
        },
        "packets": {
            "accepted": coordinator.packets_accepted,
            "rejected": coordinator.packets_rejected,
            # Raw frame, so the undocumented BLE header can be confirmed from a
            # real device rather than guessed at in the parser.
            "last_raw": coordinator.last_raw_packet,
        },
        "reading": {
            "voltage": reading.voltage,
            "current": reading.current,
            "power": reading.power,
        }
        if reading
        else None,
        "totals": {
            "energy_wh": coordinator.energy_wh,
            "energy_wh_restored": coordinator.energy_wh_base,
            "energy_wh_session": coordinator.energy_wh_session,
            "capacity_ah": coordinator.capacity_ah,
            "capacity_ah_restored": coordinator.capacity_ah_base,
            "capacity_ah_session": coordinator.capacity_ah_session,
        },
    }
