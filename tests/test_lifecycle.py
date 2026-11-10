"""Exercise HA's actual config-entry and entity-platform lifecycle offline."""

import asyncio
from pathlib import Path
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry
from homeassistant.setup import async_setup_component

from custom_components.delonghi_comfort.api import DeLonghiAPI
from custom_components.delonghi_comfort.const import DOMAIN, OEM_MODEL_HEATER, OEM_MODEL_DEHUMIDIFIER
from custom_components.delonghi_comfort.exceptions import DeLonghiConnectionError

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("initial_failure", [False, True])
async def test_setup_update_and_unload_real_platforms(hass, entry, initial_failure, caplog):
    source = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
    shutil.copytree(source, Path(hass.config.path("custom_components")) / DOMAIN, ignore=shutil.ignore_patterns("__pycache__"))
    loader.async_setup(hass)
    assert await async_load_base_functionality(hass)
    api = MagicMock(spec=DeLonghiAPI)
    api.access_token = "test-token"
    api.authenticate = AsyncMock(return_value=True)
    api.get_devices = AsyncMock(return_value=[
        {"device": {"dsn": "ac", "product_name": "Air conditioner", "oem_model": "ac"}},
        {"device": {"dsn": "heater", "product_name": "Heater", "oem_model": OEM_MODEL_HEATER}},
        {"device": {"dsn": "dehumidifier", "product_name": "Dehumidifier", "oem_model": OEM_MODEL_DEHUMIDIFIER}},
    ])
    api.get_device_properties = AsyncMock(return_value=[
        {"property": {"name": "room_temp", "value": 22}},
        {"property": {"name": "device_status", "value": 1}},
        {"property": {"name": "get_device_status", "value": 1}},
        {"property": {"name": "device_mode", "value": 1}},
        {"property": {"name": "alarm_state", "value": 0}},
    ])
    if initial_failure:
        api.get_device_properties.side_effect = DeLonghiConnectionError("offline")
    with patch("custom_components.delonghi_comfort.DeLonghiAPI", return_value=api):
        assert await async_setup_component(hass, "homeassistant", {})
        hass.config_entries._entries[entry.entry_id] = entry
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        platforms = {state.domain for state in hass.states.async_all()}
        assert {p.value for p in (Platform.CLIMATE, Platform.HUMIDIFIER, Platform.SENSOR, Platform.SWITCH, Platform.SELECT, Platform.NUMBER, Platform.BINARY_SENSOR)} <= platforms
        coordinator = hass.data[DOMAIN][entry.entry_id]["heater_coordinators"][0]
        assert coordinator._listeners
        registry = entity_registry.async_get(hass)
        sensor_id = registry.async_get_entity_id("sensor", DOMAIN, "delonghi_heater_heater_temperature")
        climate_id = registry.async_get_entity_id("climate", DOMAIN, "delonghi_heater_heater")
        assert sensor_id is not None and climate_id is not None
        state = hass.states.get(sensor_id)
        assert state is not None
        if initial_failure:
            assert state.state == "unavailable"
        else:
            assert float(state.state) == 22
        coordinator.async_set_updated_data({"room_temp": 23, "device_status": 2})
        await hass.async_block_till_done()
        state = hass.states.get(sensor_id)
        assert state is not None and float(state.state) == 23
        api.set_device_property.side_effect = DeLonghiConnectionError("offline")
        with pytest.raises(HomeAssistantError, match="Unable to communicate"):
            await hass.services.async_call("climate", "turn_on", {"entity_id": climate_id}, blocking=True)
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert entry.entry_id not in hass.data[DOMAIN]
        assert not coordinator._listeners
        errors = [record for record in caplog.records if record.levelname == "ERROR"]
        assert len(errors) == (3 if initial_failure else 0)
        assert all(record.name == "custom_components.delonghi_comfort.coordinator" and record.getMessage().endswith(": offline") for record in errors)
