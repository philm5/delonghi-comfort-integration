"""The De'Longhi Comfort integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.translation import async_load_integrations

from .api import DeLonghiAPI
from .const import (
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_LANGUAGE,
    DOMAIN,
    OEM_MODEL_DEHUMIDIFIER,
    OEM_MODEL_HEATER,
)
from .coordinator import DeLonghiCoordinator
from .exceptions import DeLonghiAuthError, DeLonghiConnectionError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Authenticate once; let HA retry startup failures and manage reauthentication."""
    api = DeLonghiAPI(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        async_get_clientsession(hass),
        entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
    )
    try:
        await api.authenticate()
        devices = await api.get_devices()
    except DeLonghiAuthError as err:
        raise ConfigEntryAuthFailed("De'Longhi credentials were rejected") from err
    except DeLonghiConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    if not devices:
        raise ConfigEntryNotReady("No De'Longhi devices returned by the account")

    # ------------------------------------------------------------------
    # Phase 2: Build one coordinator per device.
    #
    # We deliberately use async_refresh() instead of
    # async_config_entry_first_refresh() so that a transient polling failure
    # loads entities in *unavailable* state rather than aborting setup.
    # The coordinator will recover automatically on the next poll cycle.
    # ------------------------------------------------------------------
    airconditioner_coordinators: list[DeLonghiCoordinator] = []
    heater_coordinators: list[DeLonghiCoordinator] = []
    dehumidifier_coordinators: list[DeLonghiCoordinator] = []

    for device in devices:
        device_info = device["device"]
        dsn = device_info["dsn"]

        coordinator = DeLonghiCoordinator(hass, api, dsn, device_info, entry)

        # Degraded-state loading: populate data if possible, but don't block
        # the entire setup if the first poll fails (e.g. server blip).
        await coordinator.async_refresh()
        if isinstance(coordinator.last_exception, ConfigEntryAuthFailed):
            raise coordinator.last_exception
        if coordinator.last_exception:
            _LOGGER.warning(
                "Initial data fetch for device %s failed (%s). "
                "Entities will be unavailable until the next successful poll.",
                dsn,
                coordinator.last_exception,
            )

        oem_model = device_info.get("oem_model", "")
        if oem_model == OEM_MODEL_HEATER:
            heater_coordinators.append(coordinator)
        elif oem_model == OEM_MODEL_DEHUMIDIFIER:
            dehumidifier_coordinators.append(coordinator)
        else:
            airconditioner_coordinators.append(coordinator)

    # ------------------------------------------------------------------
    # Phase 3: Store state and forward to platform setup.
    # ------------------------------------------------------------------
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "devices": devices,
        "airconditioner_coordinators": airconditioner_coordinators,
        "heater_coordinators": heater_coordinators,
        "dehumidifier_coordinators": dehumidifier_coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Pre-load translation strings so the frontend can serve entity.* keys for
    # custom integrations that aren't always loaded before the first UI fetch.
    await async_load_integrations(hass, {DOMAIN})

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the De'Longhi Comfort integration (YAML config unsupported)."""
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
