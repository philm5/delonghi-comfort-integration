"""Humidifier platform for De'Longhi dehumidifier devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityDescription,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .entity import DeLonghiEntity, async_handle_command_errors

from .const import DOMAIN
from .coordinator import DeLonghiCoordinator

_LOGGER = logging.getLogger(__name__)

DEHUMIDIFIER_ENTITY_DESCRIPTION = HumidifierEntityDescription(
    key="dehumidifier",
    translation_key="dehumidifier",
    device_class=HumidifierDeviceClass.DEHUMIDIFIER,
)

DEVICE_MODE_TO_DEHUMIDIFIER = {
    1: "dehumidify",
    2: "dry",
    3: "fan_only",
}
DEHUMIDIFIER_TO_DEVICE_MODE = {v: k for k, v in DEVICE_MODE_TO_DEHUMIDIFIER.items()}



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi dehumidifier entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        DeLonghiDehumidifier(coordinator)
        for coordinator in data["dehumidifier_coordinators"]
    )


# HA combines CoordinatorEntity's dynamic availability with Entity's cached descriptor.
class DeLonghiDehumidifier(DeLonghiEntity, HumidifierEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """De'Longhi dehumidifier."""

    entity_description = DEHUMIDIFIER_ENTITY_DESCRIPTION
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "dehumidifier"
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_available_modes = list(DEVICE_MODE_TO_DEHUMIDIFIER.values())
    _attr_min_humidity = 30
    _attr_max_humidity = 80

    def __init__(self, coordinator: DeLonghiCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_dehumidifier_{coordinator.dsn}"
        self._attr_device_info = coordinator.get_device_info()
        self._update_attributes()

    @callback
    def _update_attributes(self) -> None:
        """Populate HA's backing attributes and invalidate their cached values."""
        data = self.coordinator.data
        self._attr_is_on = data.get("device_status") == 1
        self._attr_current_humidity = data.get("current_humidity")
        self._attr_target_humidity = data.get("humidity_setpoint")
        mode = data.get("device_mode")
        self._attr_mode = (
            DEVICE_MODE_TO_DEHUMIDIFIER.get(mode) if isinstance(mode, int) else None
        )

    @async_handle_command_errors
    async def async_turn_on(self, **kwargs: Any) -> None:
        if await self.coordinator.api.set_device_property(
            self.coordinator.dsn, "set_status", 1
        ):
            await self.coordinator.async_request_refresh()
        else:
            raise HomeAssistantError("Failed to turn on dehumidifier %s" % (self.coordinator.dsn,))

    @async_handle_command_errors
    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self.coordinator.api.set_device_property(
            self.coordinator.dsn, "set_status", 2
        ):
            await self.coordinator.async_request_refresh()
        else:
            raise HomeAssistantError("Failed to turn off dehumidifier %s" % (self.coordinator.dsn,))

    @async_handle_command_errors
    async def async_set_humidity(self, humidity: int) -> None:
        if await self.coordinator.api.set_humidity_setpoint(
            self.coordinator.dsn, humidity
        ):
            await self.coordinator.async_request_refresh()
        else:
            raise HomeAssistantError("Failed to set humidity setpoint on %s" % (self.coordinator.dsn,))

    @async_handle_command_errors
    async def async_set_mode(self, mode: str) -> None:
        value = DEHUMIDIFIER_TO_DEVICE_MODE.get(mode)
        if value is None:
            raise ServiceValidationError("Unknown dehumidifier mode: %s" % (mode,))
        if await self.coordinator.api.set_device_property(
            self.coordinator.dsn, "device_mode", value
        ):
            await self.coordinator.async_request_refresh()
        else:
            raise HomeAssistantError("Failed to set dehumidifier mode to %s" % (mode,))
