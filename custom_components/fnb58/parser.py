"""Parse FNB58 BLE notification payloads (V/I/P at offset 21)."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

from .const import DATA_OFFSET, DATA_SCALE

_LOGGER = logging.getLogger(__name__)

# Shortest frame that can hold the three int32 values we read
MIN_PACKET_LENGTH = DATA_OFFSET + 12

# The meter derives power from volts x amps, so a frame where the reported power
# disagrees with V*I is not a measurement frame. This is deliberately a derived
# check rather than a header-byte check: the BLE framing is not documented, and
# gating on a guessed header byte would silently discard every real reading.
# Tolerance is generous because each channel is filtered independently.
POWER_TOLERANCE_W = 1.0
POWER_TOLERANCE_FRACTION = 0.25


@dataclass(slots=True)
class FNB58Reading:
    """Parsed values from one BLE notification."""

    voltage: float
    current: float
    power: float


def _in_range(voltage: float, current: float, power: float) -> bool:
    """Return True when all three values are physically plausible."""
    return (
        0.0 <= voltage <= 150.0
        and -150.0 <= current <= 150.0
        and -2000.0 <= power <= 2000.0
    )


def _power_is_consistent(voltage: float, current: float, power: float) -> bool:
    """Return True when the reported power agrees with volts x amps."""
    expected = voltage * current
    tolerance = max(POWER_TOLERANCE_W, POWER_TOLERANCE_FRACTION * abs(expected))
    return abs(power - expected) <= tolerance


def parse_notification(data: bytes | bytearray) -> FNB58Reading | None:
    """Parse a notification frame into meter readings, or None if it is not one."""
    if len(data) < MIN_PACKET_LENGTH:
        return None

    raw_voltage, raw_current, raw_power = struct.unpack_from("<iii", data, DATA_OFFSET)
    voltage = raw_voltage / DATA_SCALE
    current = raw_current / DATA_SCALE
    power = raw_power / DATA_SCALE

    if not _in_range(voltage, current, power):
        _LOGGER.debug("Discarding out-of-range FNB58 frame: %s", data.hex())
        return None

    if not _power_is_consistent(voltage, current, power):
        _LOGGER.debug(
            "Discarding inconsistent FNB58 frame (V=%s I=%s P=%s): %s",
            voltage,
            current,
            power,
            data.hex(),
        )
        return None

    return FNB58Reading(voltage=voltage, current=current, power=power)
