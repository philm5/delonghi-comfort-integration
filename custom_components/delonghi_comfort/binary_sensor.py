"""Binary sensor platform for De'Longhi dehumidifier devices."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DeLonghiCoordinator
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

# alarm_state bitmask:  bit 1 (value 2) = tank full,  bit 2 (value 4) = filter warning
DEHUMIDIFIER_BINARY_SENSOR_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="alarm_tank_full",
        translation_key="tank_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="alarm_filter_warning",
        translation_key="filter_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

_ALARM_MASKS = {
    "alarm_tank_full": 2,
    "alarm_filter_warning": 4,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi binary sensor entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        DehumidifierBinarySensor(coordinator, description)
        for coordinator in data["dehumidifier_coordinators"]
        for description in DEHUMIDIFIER_BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class DehumidifierBinarySensor(DeLonghiEntity, BinarySensorEntity):
    """Binary sensor derived from the alarm_state bitmask."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeLonghiCoordinator, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"
        self._attr_device_info = coordinator.get_device_info()
        self._update_attributes()

    def _read_is_on(self) -> bool | None:
        alarm_state = self.coordinator.data.get("alarm_state")
        if alarm_state is None:
            return None
        mask = _ALARM_MASKS[self.entity_description.key]
        return bool(alarm_state & mask)

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        return super().available and "alarm_state" in self.coordinator.data

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_is_on = self._read_is_on()
