"""Button platform for FNB58."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FNB58ConfigEntry
from .const import KEY_RESET_TOTALS
from .entity import FNB58Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FNB58ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the FNB58 buttons from a config entry."""
    async_add_entities([FNB58ResetTotalsButton(entry.runtime_data, KEY_RESET_TOTALS)])


class FNB58ResetTotalsButton(FNB58Entity, ButtonEntity):
    """Zero the host-side energy and capacity totals."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = KEY_RESET_TOTALS

    @property
    def available(self) -> bool:
        """Return True always: the totals live in Home Assistant, not the meter."""
        return True

    async def async_press(self) -> None:
        """Reset both totals.

        Host-side only. Nothing is written to the meter, so the read-only scope
        of this integration holds; the meter's own records are untouched.
        """
        self.coordinator.async_reset_totals()
