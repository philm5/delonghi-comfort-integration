"""The De'Longhi Comfort integration."""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
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

# ---------------------------------------------------------------------------
# Retry schedule for transient connection failures during startup.
#
# The first len(_RETRY_DELAYS) attempts use the fixed sequence below.
# Every attempt after that waits _STEADY_STATE_DELAY seconds and retries
# indefinitely – setup_entry never gives up on a connection error.
#
# Timeline (wall-clock seconds from first failure):
#   attempt 1 → wait   1 s  (total   1 s elapsed)
#   attempt 2 → wait   5 s  (total   6 s)
#   attempt 3 → wait  30 s  (total  36 s)
#   attempt 4 → wait  60 s  (total  96 s)
#   attempt 5 → wait 300 s  (total 396 s  ≈  6.6 min)
#   attempt 6+ → wait 600 s each  (perpetual)
# ---------------------------------------------------------------------------
_RETRY_DELAYS: list[int] = [1, 5, 30, 60, 300]
_STEADY_STATE_DELAY: int = 600


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up De'Longhi Comfort from a config entry.

    Strategy
    --------
    1.  Attempt authentication + device list with a fixed back-off sequence
        (1 s, 5 s, 30 s, 60 s, 300 s) for transient connection errors
        (DeLonghiConnectionError), then retry every 600 s perpetually.
        This coroutine never returns False and never raises ConfigEntryNotReady
        for connection failures – it keeps the setup task alive and retrying
        until the network is available, at which point it proceeds normally.
    2.  A credential failure (DeLonghiAuthError) is the only hard stop:
        raise ConfigEntryAuthFailed so HA starts credential recovery.
    3.  Coordinator first-refresh uses async_refresh() (not
        async_config_entry_first_refresh()) so a transient polling failure
        during startup loads entities in *unavailable* state rather than
        aborting the entire entry setup.
    """
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    language = entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

    session = async_get_clientsession(hass)
    api = DeLonghiAPI(username, password, session, language)

    # ------------------------------------------------------------------
    # Phase 1: Authenticate and retrieve the device list.
    # Retry forever on transient errors; fail-fast on credential errors.
    # ------------------------------------------------------------------
    devices: list = []
    attempt = 0
    while True:
        delay = (
            _RETRY_DELAYS[attempt]
            if attempt < len(_RETRY_DELAYS)
            else _STEADY_STATE_DELAY
        )

        try:
            await api.authenticate()
            devices = await api.get_devices()
        except DeLonghiAuthError as err:
            # Invalid credentials – request a replacement password. Never retry.
            _LOGGER.error(
                "Authentication rejected by De'Longhi API (invalid credentials). "
                "Please reauthenticate the integration: %s",
                err,
            )
            raise ConfigEntryAuthFailed(
                "De'Longhi API rejected the credentials. "
                "Please re-enter your password."
            ) from err
        except DeLonghiConnectionError as err:
            _LOGGER.warning(
                "De'Longhi API connection error (attempt %d) – "
                "retrying in %d s: %s",
                attempt + 1,
                delay,
                err,
            )
            attempt += 1
            await asyncio.sleep(delay)
            continue

        if not devices:
            _LOGGER.warning(
                "Authentication succeeded but no De'Longhi devices were returned "
                "by the API (attempt %d) – retrying in %d s.",
                attempt + 1,
                delay,
            )
            attempt += 1
            await asyncio.sleep(delay)
            continue

        break  # ── auth succeeded and devices found ────────────────

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
