"""Isolated Home Assistant objects; tests never use a real account."""

from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.delonghi_comfort.const import DOMAIN


@pytest_asyncio.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    with (
        patch("custom_components.delonghi_comfort.async_get_clientsession", return_value=MagicMock()),
        patch("custom_components.delonghi_comfort.config_flow.async_get_clientsession", return_value=MagicMock()),
    ):
        yield instance
    await instance.async_stop(force=True)


@pytest.fixture
def entry(hass):
    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test account",
        data={"username": "test@example.com", "password": "old", "language": "it"},
        options={"scan_interval": 15},
        source="user",
        unique_id="test@example.com",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    hass.config_entries._entries[config_entry.entry_id] = config_entry
    return config_entry
