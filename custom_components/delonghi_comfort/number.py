"""Number platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTIONS = (
    NumberEntityDescription(
        key="temp_setpoint",
        translation_key="temperature_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=16,
        native_max_value=32,
        native_step=1,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key="humidity_setpoint",
        translation_key="humidity_setpoint",
        device_class=NumberDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=30,
        native_max_value=80,
        native_step=5,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi number entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = data["coordinators"]

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiNumber(
                    coordinator=coordinator,
                    description=description,
                )
                for description in NUMBER_DESCRIPTIONS
            ]
        )

    async_add_entities(entities)


class DeLonghiNumber(CoordinatorEntity, NumberEntity):
    """Representation of a De'Longhi number entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
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
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.coordinator.data.get(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        if self.entity_description.key == "temp_setpoint":
            success = await self.coordinator.api.set_temperature_setpoint(
                self.coordinator.dsn, value
            )
        elif self.entity_description.key == "humidity_setpoint":
            success = await self.coordinator.api.set_humidity_setpoint(
                self.coordinator.dsn, value
            )
        else:
            success = False

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set %s to %s", self.entity_description.key, value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )
