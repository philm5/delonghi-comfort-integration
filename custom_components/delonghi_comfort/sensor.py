"""Sensor platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DeLonghiCoordinator
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="room_temp",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="temp_setpoint",
        translation_key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="room_hum",
        translation_key="room_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="get_device_status",
        translation_key="device_status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="get_device_mode",
        translation_key="device_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="get_int_fan_speed",
        translation_key="fan_speed",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="get_silent_function",
        translation_key="silent_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="filter_hours",
        translation_key="filter_hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="power_consumption",
        translation_key="power_consumption",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="wifi_signal",
        translation_key="wifi_signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="operating_hours",
        translation_key="operating_hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi sensor entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    for coordinator in data["airconditioner_coordinators"]:
        entities.extend(
            DeLonghiSensor(coordinator=coordinator, description=description)
            for description in SENSOR_DESCRIPTIONS
        )

    entities.extend(
        HeaterTemperature(coordinator=coordinator)
        for coordinator in data["heater_coordinators"]
    )

    entities.extend(
        DehumidifierSensor(coordinator=coordinator, description=description)
        for coordinator in data["dehumidifier_coordinators"]
        for description in DEHUMIDIFIER_SENSOR_DESCRIPTIONS
    )

    async_add_entities(entities)


class DeLonghiSensor(DeLonghiEntity, SensorEntity):
    """Representation of a De'Longhi sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeLonghiCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

        # Device information
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.dsn)},
            name=coordinator.device_name,
            manufacturer="De'Longhi",
            model=coordinator.device_model,
            sw_version=coordinator.device_version,
        )
        self._update_attributes()

    def _read_native_value(self) -> Any:
        """Return the value of the sensor."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Apply value transformation for specific sensors
        if self.entity_description.key == "get_device_status":
            return "on" if value == 1 else "off" if value == 2 else "unknown"
        if self.entity_description.key == "get_device_mode":
            return {1: "cooling", 2: "dehumidification", 3: "fan_only"}.get(
                value, "unknown"
            )
        if self.entity_description.key == "get_silent_function":
            return "on" if value == 1 else "off" if value == 0 else "unknown"

        return value

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_native_value = self._read_native_value()


DEHUMIDIFIER_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="current_humidity",
        translation_key="room_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="room_temp",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="current_speed",
        translation_key="fan_speed",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="heat_exchanger_temp",
        translation_key="heat_exchanger_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="alarm_state",
        translation_key="alarm_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


class DehumidifierSensor(DeLonghiEntity, SensorEntity):
    """Sensor for De'Longhi dehumidifier devices."""

    _attr_has_entity_name = True

    # Properties requiring ÷10 scaling
    _SCALED_KEYS = {"room_temp", "heat_exchanger_temp"}

    def __init__(self, coordinator: DeLonghiCoordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"  # stable, keep prefix
        )
        self._attr_device_info = coordinator.get_device_info()
        self._update_attributes()

    def _read_native_value(self) -> Any:
        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None
        if self.entity_description.key in self._SCALED_KEYS:
            return value / 10
        return value

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        return (
            super().available
            and self.entity_description.key in self.coordinator.data
        )

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_native_value = self._read_native_value()


class HeaterTemperature(DeLonghiEntity, SensorEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Representation of a De'Longhi heater temperature sensor."""
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_name = "Temperature"

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DeLonghiCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_temperature"
        self._attr_device_info = coordinator.get_device_info()
        self._update_attributes()

    def _read_native_value(self) -> Any:
        """Return the value of the sensor."""
        return self.coordinator.data.get("room_temp")

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_native_value = self._read_native_value()
