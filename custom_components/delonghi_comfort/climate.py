"""Climate platform for De'Longhi Comfort integration."""

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Mapping from device modes to HVAC modes
DEVICE_MODE_TO_HVAC = {
    1: HVACMode.COOL,  # Cooling
    2: HVACMode.DRY,  # Dehumidification
    3: HVACMode.FAN_ONLY,  # Fan
}

HVAC_MODE_TO_DEVICE = {v: k for k, v in DEVICE_MODE_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi climate entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = data["coordinators"]

    entities = [
        DeLonghiClimate(coordinator=coordinator) for coordinator in coordinators
    ]

    entities.extend([DeLonghiHeater(coordinator=coordinator) for coordinator in data["heater_coordinators"]])

    async_add_entities(entities)


class DeLonghiClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a De'Longhi climate device."""

    def __init__(
        self,
        coordinator,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._dsn = coordinator.dsn
        self._api = coordinator.api

        # Entity information
        self._attr_unique_id = f"delonghi_comfort_{self._dsn}"
        self._attr_name = coordinator.device_name

        # Climate features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        ]

        # Fan modes - you can adjust these based on your device's capabilities
        self._attr_fan_modes = ["auto", "low", "medium", "high"]

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 18
        self._attr_max_temp = 32
        self._attr_target_temperature_step = 1
        self._attr_precision = 1

        # Device information
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._dsn)},
            "name": coordinator.device_name,
            "manufacturer": "De'Longhi",
            "model": coordinator.device_model,
            "sw_version": coordinator.device_version,
            "via_device": (DOMAIN, self._dsn),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation."""
        status = self.coordinator.data.get("get_device_status")
        if status == 2:  # OFF
            return HVACAction.OFF

        device_mode = self.coordinator.data.get("get_device_mode")
        if device_mode == 1:  # Cooling
            return HVACAction.COOLING
        elif device_mode == 2:  # Dehumidification
            return HVACAction.DRYING
        elif device_mode == 3:  # Fan
            return HVACAction.FAN

        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.coordinator.data.get("room_temp")

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self.coordinator.data.get("temp_setpoint")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        # Check if device is on/off first
        status = self.coordinator.data.get("get_device_status")
        if status == 2:  # OFF
            return HVACMode.OFF

        # Get device mode
        device_mode = self.coordinator.data.get("get_device_mode")
        return DEVICE_MODE_TO_HVAC.get(device_mode, HVACMode.OFF)

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        return self.coordinator.data.get("room_hum")

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode."""
        # Get fan speed from device data
        fan_speed = self.coordinator.data.get("get_int_fan_speed")
        if fan_speed is not None:
            # Map device fan speed values to fan mode names
            # Based on API: 1=Low, 2=Mid, 3=High, 4=Auto
            fan_speed_map = {1: "low", 2: "medium", 3: "high", 4: "auto"}
            return fan_speed_map.get(fan_speed, "auto")
        return "auto"

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        if await self._api.set_temperature_setpoint(self._dsn, float(temperature)):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set temperature setpoint")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            # Turn off the device
            if await self._api.set_device_status(self._dsn, 2):  # 2 = OFF
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to turn off device")
        else:
            # First turn on the device if it's off
            current_status = self.coordinator.data.get("get_device_status")
            if current_status == 2:  # Device is off
                if not await self._api.set_device_status(self._dsn, 1):  # 1 = ON
                    _LOGGER.error("Failed to turn on device")
                    return

            # Set the mode
            device_mode = HVAC_MODE_TO_DEVICE.get(hvac_mode)
            if device_mode and await self._api.set_device_mode(self._dsn, device_mode):
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to set HVAC mode")

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        # Map fan mode names to device values
        # Based on API: 1=Low, 2=Mid, 3=High, 4=Auto
        fan_mode_map = {"low": 1, "medium": 2, "high": 3, "auto": 4}

        fan_speed = fan_mode_map.get(fan_mode)
        if fan_speed is None:
            _LOGGER.error("Invalid fan mode: %s", fan_mode)
            return

        if await self._api.set_fan_speed(self._dsn, fan_speed):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set fan mode to %s", fan_mode)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if await self._api.set_device_status(self._dsn, 1):  # 1 = ON
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on device")

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        if await self._api.set_device_status(self._dsn, 2):  # 2 = OFF
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off device")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return dict(self.coordinator.data)

class DeLonghiHeater(CoordinatorEntity, ClimateEntity):
    """Representation of a De'Longhi climate device."""

    # Entity - Generic properties
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "heater"

    # Entity - Advanced properties
    _attr_icon = "mdi:radiator"

    # Climate entity - Properties
    _attr_fan_modes = ["0%", "20%", "40%", "60%", "80%", "100%"]
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_max_temp = 28
    _attr_min_temp = 10
    _attr_preset_modes = ["Day mode", "Night mode", "Antifrost", "Manual"]
    _attr_target_temperature_step = 0.5
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._dsn = coordinator.dsn
        self._api = coordinator.api

        self._attr_unique_id = f"delonghi_heater_{self._dsn}"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return dict(self.coordinator.data)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        # Check if device is on/off first
        status = self.coordinator.data.get("device_status")
        return HVACMode.HEAT if status == 1 else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation."""
        status = self.coordinator.data.get("device_status")
        if status == 1:  # ON
            power_level = self.coordinator.data.get("MDH_Resources")
            return HVACAction.IDLE if power_level == 0 else HVACAction.HEATING
        return HVACAction.OFF

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        device_mode = self.coordinator.data.get("device_mode")
        return self.preset_modes[device_mode-1] if 1 <= device_mode <= 4 else None

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.coordinator.data.get("room_temp")

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self.coordinator.data.get("temperature_setpoint")

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode."""
        power_level = self.coordinator.data.get("current_power_level", 0)
        return self.fan_modes[power_level]

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if await self._api.set_device_property(self._dsn, "set_status", 1):  # 1 = ON
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on device")

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        if await self._api.set_device_property(self._dsn, "set_status", 2):  # 2 = OFF
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off device")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        if preset_mode not in self.preset_modes:
            _LOGGER.error("Invalid preset mode: %s", preset_mode)
            return
        device_mode = self.preset_modes.index(preset_mode) + 1
        if await self._api.set_device_property(self._dsn, "set_device_mode", device_mode):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set preset mode to %s", preset_mode)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        power_level = self.fan_modes.index(fan_mode)
        if await self._api.set_device_property(self._dsn, "set_power_level", power_level):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set fan mode to %s", fan_mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if await self._api.set_device_property(self._dsn, "temperature_setpoint", float(temperature)):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set temperature setpoint")
