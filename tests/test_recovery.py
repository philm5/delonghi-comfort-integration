"""Regression coverage for credential recovery and unavailable-state loading."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.data_entry_flow import AbortFlow

from custom_components.delonghi_comfort import async_setup_entry
from custom_components.delonghi_comfort.api import DeLonghiAPI
from custom_components.delonghi_comfort.climate import DeLonghiClimate, DeLonghiHeater
from custom_components.delonghi_comfort.config_flow import DelonghiComfortConfigFlow
from custom_components.delonghi_comfort.const import DOMAIN
from custom_components.delonghi_comfort.coordinator import DeLonghiCoordinator
from custom_components.delonghi_comfort.exceptions import (
    DeLonghiAuthError,
    DeLonghiConnectionError,
)
from custom_components.delonghi_comfort.humidifier import DeLonghiDehumidifier
from custom_components.delonghi_comfort.sensor import DeLonghiSensor, SENSOR_DESCRIPTIONS

pytestmark = pytest.mark.asyncio


async def test_reauth_updates_same_entry(hass, entry):
    flow = DelonghiComfortConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.flow_id = "test-flow"
    flow.context = {"entry_id": entry.entry_id, "source": "reauth"}
    initial = await flow.async_step_reauth(entry.data)
    assert initial["step_id"] == "reauth_confirm"
    assert initial["data_schema"]({"password": "new"}) == {"password": "new"}

    with (
        patch("custom_components.delonghi_comfort.config_flow.DeLonghiAPI") as client,
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        client.return_value.authenticate = AsyncMock(return_value=True)
        client.return_value.get_devices = AsyncMock(return_value=[{"device": {"dsn": "test"}}])
        result = await flow.async_step_reauth_confirm({"password": "new"})

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert entry.data == {"username": "test@example.com", "password": "new", "language": "it"}
    assert entry.options == {"scan_interval": 15}
    assert entry.unique_id == "test@example.com"
    reload.assert_called_once_with(entry.entry_id)
    assert client.call_args.args[:2] == ("test@example.com", "new")
    assert client.call_args.args[3] == "it"


@pytest.mark.parametrize("failure, expected", [
    (DeLonghiAuthError("rejected"), "invalid_auth"),
    (DeLonghiConnectionError("offline"), "cannot_connect"),
])
async def test_reauth_failure_keeps_password(hass, entry, failure, expected):
    flow = DelonghiComfortConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.flow_id = "test-flow"
    flow.context = {"entry_id": entry.entry_id, "source": "reauth"}
    await flow.async_step_reauth(entry.data)
    with (
        patch("custom_components.delonghi_comfort.config_flow.DeLonghiAPI") as client,
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        client.return_value.authenticate = AsyncMock(side_effect=failure)
        result = await flow.async_step_reauth_confirm({"password": "new"})
    assert result["errors"] == {"base": expected}
    assert entry.data["password"] == "old"
    reload.assert_not_called()


async def test_duplicate_account_still_aborts(hass, entry):
    flow = DelonghiComfortConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.flow_id = "test-flow"
    flow.context = {"source": "user"}
    with patch.object(flow, "_validate_credentials", AsyncMock(return_value=None)):
        with pytest.raises(AbortFlow, match="already_configured"):
            await flow.async_step_user(dict(entry.data))


async def test_first_poll_failure_and_recovery(hass, entry):
    api = DeLonghiAPI("test", "test", None)
    api.access_token = "token"
    api.get_device_properties = AsyncMock(side_effect=[
        DeLonghiConnectionError("offline"),
        [{"property": {"name": "room_temp", "value": 22}}],
        DeLonghiConnectionError("offline again"),
    ])
    coordinator = DeLonghiCoordinator(hass, api, "test", {}, entry)
    await coordinator.async_refresh()
    assert coordinator.data == {}
    assert not coordinator.last_update_success

    sensor = DeLonghiSensor(coordinator, SENSOR_DESCRIPTIONS[0])
    assert sensor.native_value is None
    assert not sensor.available
    for entity in (DeLonghiClimate(coordinator), DeLonghiHeater(coordinator), DeLonghiDehumidifier(coordinator)):
        assert not entity.available
        assert entity.device_info is not None
    heater = DeLonghiHeater(coordinator)
    assert heater.extra_state_attributes == {}
    assert heater.preset_mode is None
    assert heater.current_temperature is None
    assert DeLonghiDehumidifier(coordinator).current_humidity is None

    await coordinator.async_refresh()
    assert sensor.available
    assert sensor.native_value == 22
    await coordinator.async_refresh()
    assert not sensor.available
    assert coordinator.data == {"room_temp": 22}


@pytest.mark.parametrize("missing_token", [False, True])
async def test_auth_failure_starts_reauth(hass, entry, missing_token):
    api = DeLonghiAPI("test", "test", None)
    api.access_token = None if missing_token else "expired"
    api.authenticate = AsyncMock(side_effect=DeLonghiAuthError("rejected"))
    api.get_device_properties = AsyncMock(side_effect=DeLonghiAuthError("rejected"))
    coordinator = DeLonghiCoordinator(hass, api, "test", {}, entry)
    with patch.object(type(entry), "async_start_reauth") as reauth:
        await coordinator.async_refresh()
    assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)
    assert not coordinator.last_update_success
    reauth.assert_called_once_with(hass, None, None)


async def test_setup_does_not_load_platforms_after_auth_failure(hass, entry):
    api = DeLonghiAPI("test", "test", None)
    api.access_token = "token"
    api.authenticate = AsyncMock(return_value=True)
    api.get_devices = AsyncMock(return_value=[{"device": {"dsn": "test"}}])
    api.get_device_properties = AsyncMock(side_effect=DeLonghiAuthError("rejected"))
    with (
        patch("custom_components.delonghi_comfort.DeLonghiAPI", return_value=api),
        patch.object(type(entry), "async_start_reauth"),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()) as forward,
    ):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
    forward.assert_not_awaited()


async def test_setup_loads_unavailable_entities_on_connection_failure(hass, entry):
    api = DeLonghiAPI("test", "test", None)
    api.access_token = "token"
    api.authenticate = AsyncMock(return_value=True)
    api.get_devices = AsyncMock(return_value=[{"device": {"dsn": "test"}}])
    api.get_device_properties = AsyncMock(side_effect=DeLonghiConnectionError("offline"))
    with (
        patch("custom_components.delonghi_comfort.DeLonghiAPI", return_value=api),
        patch("custom_components.delonghi_comfort.async_load_integrations", AsyncMock()),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()) as forward,
    ):
        assert await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]["airconditioner_coordinators"][0]
    assert coordinator.data == {}
    assert not coordinator.last_update_success
    forward.assert_awaited_once()
