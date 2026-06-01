"""Parse FNB58 BLE notification payloads (V/I/P at offset 21)."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .const import DATA_OFFSET, DATA_SCALE


@dataclass(slots=True)
class FNB58Reading:
    """Parsed values from one BLE notification."""

    voltage: float
    current: float
    power: float


def _valid_primary(voltage: float, current: float, power: float) -> bool:
    return (
        0.0 <= voltage <= 150.0
        and -150.0 <= current <= 150.0
        and -2000.0 <= power <= 2000.0
    )


def parse_notification(data: bytes | bytearray) -> FNB58Reading | None:
    """Parse a notification packet into meter readings."""
    if len(data) < DATA_OFFSET + 12:
        return None

    raw = struct.unpack_from("<iii", data, DATA_OFFSET)
    voltage = raw[0] / DATA_SCALE
    current = raw[1] / DATA_SCALE
    power = raw[2] / DATA_SCALE
    if not _valid_primary(voltage, current, power):
        return None

    return FNB58Reading(voltage=voltage, current=current, power=power)
