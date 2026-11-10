"""Entity state must follow coordinator updates, including HA's cached properties."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.exceptions import ServiceValidationError

from custom_components.delonghi_comfort.api import DeLonghiAPI
from custom_components.delonghi_comfort.binary_sensor import (
    DehumidifierBinarySensor, DEHUMIDIFIER_BINARY_SENSOR_DESCRIPTIONS,
)
from custom_components.delonghi_comfort.climate import DeLonghiClimate, DeLonghiHeater
from custom_components.delonghi_comfort.config_flow import DelonghiComfortConfigFlow
from custom_components.delonghi_comfort.coordinator import DeLonghiCoordinator
from custom_components.delonghi_comfort.humidifier import DeLonghiDehumidifier
from custom_components.delonghi_comfort.number import DeLonghiNumber, NUMBER_DESCRIPTIONS
from custom_components.delonghi_comfort.select import (
    DeLonghiSelect, SELECT_DESCRIPTIONS, HeaterBrightness, DehumidifierModeSelect,
)
from custom_components.delonghi_comfort.sensor import (
    DeLonghiSensor, SENSOR_DESCRIPTIONS, DehumidifierSensor,
    DEHUMIDIFIER_SENSOR_DESCRIPTIONS, HeaterTemperature,
)
from custom_components.delonghi_comfort.switch import (
    DeLonghiSwitch, SWITCH_DESCRIPTIONS, HeaterSwitch, HEATER_DESCRIPTIONS,
    DehumidifierSwitch, DEHUMIDIFIER_SWITCH_DESCRIPTIONS,
)

pytestmark = pytest.mark.asyncio

INITIAL = {
    "get_device_status": 1, "get_device_mode": 1, "room_temp": 220,
    "temp_setpoint": 24, "room_hum": 50, "get_int_fan_speed": 1,
    "device_status": 1, "device_mode": 1, "current_humidity": 50,
    "humidity_setpoint": 60, "temperature_setpoint": 24, "current_power_level": 1,
    "MDH_Resources": 1, "alarm_state": 0, "current_brightness": 1,
    "get_eco": 0, "set_eco": 0,
}
UPDATED = {
    **INITIAL, "get_device_status": 2, "get_device_mode": 2, "room_temp": 230, "temp_setpoint": 25,
    "device_status": 2, "device_mode": 2, "current_humidity": 55,
    "alarm_state": 2, "current_brightness": 2, "get_eco": 1, "set_eco": 1,
}


@pytest.mark.parametrize("factory, attribute, before, after", [
    (DeLonghiClimate, "hvac_mode", HVACMode.COOL, HVACMode.OFF),
    (DeLonghiClimate, "native_current_temperature", 220, 230),
    (DeLonghiClimate, "native_target_temperature", 24, 25),
    (DeLonghiHeater, "hvac_mode", HVACMode.HEAT, HVACMode.OFF),
    (DeLonghiHeater, "preset_mode", "Day mode", "Night mode"),
    (DeLonghiHeater, "native_current_temperature", 220, 230),
    (DeLonghiDehumidifier, "current_humidity", 50, 55),
    (DeLonghiDehumidifier, "is_on", True, False),
    (lambda c: DehumidifierBinarySensor(c, DEHUMIDIFIER_BINARY_SENSOR_DESCRIPTIONS[0]), "is_on", False, True),
    (lambda c: DeLonghiNumber(c, NUMBER_DESCRIPTIONS[0]), "native_value", 24, 25),
    (lambda c: DeLonghiSelect(c, SELECT_DESCRIPTIONS[0]), "current_option", "cooling", "dehumidification"),
    (HeaterBrightness, "current_option", "Level 1", "Level 2"),
    (DehumidifierModeSelect, "current_option", "dehumidify", "dry"),
    (lambda c: DeLonghiSensor(c, SENSOR_DESCRIPTIONS[0]), "native_value", 220, 230),
    (lambda c: DehumidifierSensor(c, DEHUMIDIFIER_SENSOR_DESCRIPTIONS[1]), "native_value", 22, 23),
    (HeaterTemperature, "native_value", 220, 230),
    (lambda c: DeLonghiSwitch(c, SWITCH_DESCRIPTIONS[0]), "is_on", True, False),
    (lambda c: HeaterSwitch(c, HEATER_DESCRIPTIONS[0]), "is_on", False, True),
    (lambda c: DehumidifierSwitch(c, DEHUMIDIFIER_SWITCH_DESCRIPTIONS[0]), "is_on", False, True),
])
async def test_entity_refresh_invalidates_cached_state(hass, entry, factory, attribute, before, after):
    coordinator = DeLonghiCoordinator(hass, MagicMock(spec=DeLonghiAPI), "test", {}, entry)
    coordinator.async_set_updated_data(dict(INITIAL))
    entity = factory(coordinator)
    assert getattr(entity, attribute) == before  # Populate HA's property cache.
    assert entity.available
    with patch.object(entity, "async_write_ha_state") as write:
        remove_listener = coordinator.async_add_listener(entity._handle_coordinator_update)
        try:
            coordinator.async_set_updated_data(dict(UPDATED))
            assert getattr(entity, attribute) == after
            write.assert_called_once()
            coordinator.async_set_update_error(RuntimeError("offline"))
            assert not entity.available
            assert getattr(entity, attribute) == after  # Retain the last snapshot.
        finally:
            remove_listener()


async def test_reauth_without_entry_id_aborts(hass):
    flow = DelonghiComfortConfigFlow()
    flow.hass = hass
    flow.context = {"source": "reauth"}
    result = await flow.async_step_reauth({})
    assert result.get("reason") == "unknown"


@pytest.mark.parametrize("power, brightness", [(-1, 0), (6, 4), (None, None)])
async def test_unknown_heater_indices_do_not_crash(hass, entry, power, brightness):
    coordinator = DeLonghiCoordinator(hass, MagicMock(spec=DeLonghiAPI), "test", {}, entry)
    coordinator.data = {"current_power_level": power, "current_brightness": brightness}
    assert DeLonghiHeater(coordinator).fan_mode is None
    assert HeaterBrightness(coordinator).current_option is None


async def test_unknown_switch_key_does_not_write(hass, entry):
    api = MagicMock(spec=DeLonghiAPI)
    coordinator = DeLonghiCoordinator(hass, api, "test", {}, entry)
    entity = DeLonghiSwitch(coordinator, SwitchEntityDescription(key="unknown"))
    with pytest.raises(ServiceValidationError):
        await entity.async_turn_on()
    with pytest.raises(ServiceValidationError):
        await entity.async_turn_off()
    api.set_device_status.assert_not_called()
    api.set_silent_mode.assert_not_called()


@pytest.mark.parametrize("factory, method, arguments, api_method", [
    (DeLonghiClimate, "async_turn_on", (), "set_device_status"),
    (DeLonghiHeater, "async_turn_on", (), "set_device_property"),
    (DeLonghiDehumidifier, "async_turn_on", (), "set_device_property"),
    (lambda c: DeLonghiNumber(c, NUMBER_DESCRIPTIONS[0]), "async_set_native_value", (23,), "set_temperature_setpoint"),
    (lambda c: DeLonghiSelect(c, SELECT_DESCRIPTIONS[0]), "async_select_option", ("cooling",), "set_device_mode"),
    (HeaterBrightness, "async_select_option", ("Level 2",), "set_device_property"),
    (DehumidifierModeSelect, "async_select_option", ("dry",), "set_device_property"),
    (lambda c: DeLonghiSwitch(c, SWITCH_DESCRIPTIONS[0]), "async_turn_on", (), "set_device_status"),
    (lambda c: HeaterSwitch(c, HEATER_DESCRIPTIONS[0]), "async_turn_on", (), "set_device_property"),
    (lambda c: DehumidifierSwitch(c, DEHUMIDIFIER_SWITCH_DESCRIPTIONS[0]), "async_turn_on", (), "set_device_property"),
])
@pytest.mark.parametrize("auth_failure", [False, True])
async def test_commands_report_errors_to_ha(hass, entry, factory, method, arguments, api_method, auth_failure):
    from homeassistant.exceptions import HomeAssistantError
    from custom_components.delonghi_comfort.exceptions import DeLonghiAuthError, DeLonghiConnectionError

    api = MagicMock(spec=DeLonghiAPI)
    api.access_token = "old-token"
    error = DeLonghiAuthError("rejected") if auth_failure else DeLonghiConnectionError("offline")
    getattr(api, api_method).side_effect = error
    coordinator = DeLonghiCoordinator(hass, api, "test", {}, entry)
    entity = factory(coordinator)
    with patch.object(type(entry), "async_start_reauth") as reauth, patch.object(coordinator, "async_request_refresh") as refresh:
        with pytest.raises(HomeAssistantError):
            await getattr(entity, method)(*arguments)
        assert reauth.call_count == int(auth_failure)
        refresh.assert_not_called()
    if auth_failure:
        assert api.access_token is None
