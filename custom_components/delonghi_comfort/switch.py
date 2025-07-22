"""Switch platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SWITCH_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="get_device_status",
        translation_key="device_power",
        icon="mdi:power",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi switch entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = data["coordinators"]

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiSwitch(
                    coordinator=coordinator,
                    description=description,
                )
                for description in SWITCH_DESCRIPTIONS
            ]
        )

    async_add_entities(entities)


class DeLonghiSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a De'Longhi switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch entity."""
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
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Device status: 1 = ON, 2 = OFF
        return value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.api.set_device_status(self.coordinator.dsn, 1)

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on device %s", self.coordinator.dsn)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.api.set_device_status(self.coordinator.dsn, 2)

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off device %s", self.coordinator.dsn)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )
