"""Switch platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DeLonghiCoordinator
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

SWITCH_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="get_device_status",
        translation_key="device_power",
        icon="mdi:power",
    ),
    SwitchEntityDescription(
        key="get_silent_function",
        translation_key="silent_mode",
        icon="mdi:volume-mute",
    ),
)

DEHUMIDIFIER_SWITCH_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="set_eco",
        translation_key="eco_mode",
        icon="mdi:sprout",
    ),
    SwitchEntityDescription(
        key="swing",
        translation_key="swing",
        icon="mdi:arrow-oscillating",
    ),
)

HEATER_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="eco",
        icon="mdi:sprout",
        name="Eco",
    ),
    SwitchEntityDescription(
        key="lock",
        icon="mdi:lock",
        name="Child lock",
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi switch entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    for coordinator in data["airconditioner_coordinators"]:
        entities.extend(
            DeLonghiSwitch(coordinator=coordinator, description=description)
            for description in SWITCH_DESCRIPTIONS
        )

    for coordinator in data["heater_coordinators"]:
        entities.extend(
            HeaterSwitch(coordinator=coordinator, description=description)
            for description in HEATER_DESCRIPTIONS
        )

    for coordinator in data["dehumidifier_coordinators"]:
        entities.extend(
            DehumidifierSwitch(coordinator=coordinator, description=description)
            for description in DEHUMIDIFIER_SWITCH_DESCRIPTIONS
        )

    async_add_entities(entities)


class DeLonghiSwitch(DeLonghiEntity, SwitchEntity):
    """Representation of a De'Longhi switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeLonghiCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch entity."""
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

    def _read_is_on(self) -> bool | None:
        """Return True if the switch is on."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Device status: 1 = ON, 2 = OFF
        return value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self.entity_description.key == "get_device_status":
            success = await self.coordinator.api.set_device_status(self.coordinator.dsn, 1)
        elif self.entity_description.key == "get_silent_function":
            success = await self.coordinator.api.set_silent_mode(self.coordinator.dsn, 1)
        else:
            _LOGGER.error("Unknown switch: %s", self.entity_description.key)
            return

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to change %s to 1", self.entity_description.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self.entity_description.key == "get_device_status":
            success = await self.coordinator.api.set_device_status(self.coordinator.dsn, 2)
        elif self.entity_description.key == "get_silent_function":
            success = await self.coordinator.api.set_silent_mode(self.coordinator.dsn, 0)
        else:
            _LOGGER.error("Unknown switch: %s", self.entity_description.key)
            return

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to change %s to 0", self.entity_description.key)

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_is_on = self._read_is_on()

class HeaterSwitch(DeLonghiEntity, SwitchEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Representation of a De'Longhi heater switch entity."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeLonghiCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_{description.key}"
        self._attr_device_info = coordinator.get_device_info()
        self._update_attributes()

    def _read_is_on(self) -> bool | None:
        """Return True if the switch is on."""
        value = self.coordinator.data.get(f"get_{self.entity_description.key}")
        if value is None:
            return None
        # Device status: 1 = ON, 0 = OFF
        return value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.api.set_device_property(self.coordinator.dsn, f"set_{self.entity_description.key}", 1)
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on: %s", self.entity_description.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.api.set_device_property(self.coordinator.dsn, f"set_{self.entity_description.key}", 0)
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off: %s", self.entity_description.key)

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_is_on = self._read_is_on()


class DehumidifierSwitch(DeLonghiEntity, SwitchEntity):
    """Switch entity for De'Longhi dehumidifier (set_eco, swing)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeLonghiCoordinator, description: SwitchEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"
        )
        self._attr_device_info = coordinator.get_device_info()
        self._update_attributes()

    def _read_is_on(self) -> bool | None:
        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None
        return value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, self.entity_description.key, 1
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on %s", self.entity_description.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, self.entity_description.key, 0
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off %s", self.entity_description.key)

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        return (
            super().available
            and self.entity_description.key in self.coordinator.data
        )

    def _update_attributes(self) -> None:
        """Refresh HA backing attributes from the coordinator snapshot."""
        self._attr_is_on = self._read_is_on()
