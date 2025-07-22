"""Select platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SELECT_DESCRIPTIONS = (
    SelectEntityDescription(
        key="get_device_mode",
        translation_key="device_mode",
        options=["cooling", "dehumidification", "fan_only"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi select entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = data["coordinators"]

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiSelect(
                    coordinator=coordinator,
                    description=description,
                )
                for description in SELECT_DESCRIPTIONS
            ]
        )

    async_add_entities(entities)


class DeLonghiSelect(CoordinatorEntity, SelectEntity):
    """Representation of a De'Longhi select entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: SelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

        # Device information
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.dsn)},
            "name": coordinator.device_name,
            "manufacturer": "De'Longhi",
            "model": coordinator.device_model,
            "sw_version": coordinator.device_version,
        }

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Convert device mode value to option
        mode_map = {1: "cooling", 2: "dehumidification", 3: "fan_only"}
        return mode_map.get(value)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        # Convert option to device mode value
        option_map = {"cooling": 1, "dehumidification": 2, "fan_only": 3}

        device_mode = option_map.get(option)
        if device_mode is None:
            _LOGGER.error("Unknown option: %s", option)
            return

        success = await self.coordinator.api.set_device_mode(
            self.coordinator.dsn, device_mode
        )

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set device mode to %s", option)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )
