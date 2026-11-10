"""Data update coordinator for De'Longhi Comfort integration."""

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeLonghiAPI
from .const import CONF_SCAN_INTERVAL, DOMAIN, SCAN_INTERVAL
from .exceptions import DeLonghiAuthError, DeLonghiConnectionError

_LOGGER = logging.getLogger(__name__)

# Minimum time to wait between re-authentication attempts inside the
# coordinator.  With a 15-second poll interval this prevents hammering the
# Gigya endpoint if the access token keeps disappearing.
_MIN_REAUTH_INTERVAL: timedelta = timedelta(seconds=120)


class DeLonghiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage polling data updates for a single De'Longhi device."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DeLonghiAPI,
        dsn: str,
        device_info: dict[str, Any],
        config_entry,
    ) -> None:
        """Initialize the coordinator."""
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"delonghi_comfort_{dsn}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        # Entity properties can be read even while the first refresh has failed.
        self.data = {}
        self.api = api
        self.dsn = dsn
        self.device_name = device_info.get("product_name", f"De'Longhi {dsn}")
        self.device_model = device_info.get("model", "Unknown")
        self.device_version = device_info.get("sw_version")

        # Tracks when we last *attempted* re-authentication so we don't
        # bombard the Gigya auth endpoints on every poll cycle when the token
        # is missing and the network is unavailable.
        self._last_auth_attempt: datetime | None = None

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest property snapshot from the Ayla Networks API.

        Recovery flow
        -------------
        If ``api.access_token`` is absent, this method attempts a full
        re-authentication *before* fetching device properties.  Re-auth is
        rate-limited to at most once every ``_MIN_REAUTH_INTERVAL`` so that a
        prolonged outage doesn't spam the Gigya endpoint on every poll cycle.

        Connection failures mark entities unavailable and keep polling.
        Rejected credentials start Home Assistant's reauthentication flow.
        """
        # ── Step 1: ensure we have a valid access token ──────────────
        if not self.api.access_token:
            await self._maybe_reauthenticate()
            # _maybe_reauthenticate raises UpdateFailed if it can't auth.

        # ── Step 2: fetch device properties ──────────────────────────
        try:
            properties = await self.api.get_device_properties(self.dsn)
        except DeLonghiConnectionError as err:
            # Transient network error – mark unavailable, retry next cycle.
            raise UpdateFailed(
                f"Connection error while fetching properties for {self.dsn}: {err}"
            ) from err
        except DeLonghiAuthError as err:
            # Hand rejected credentials to HA's credential recovery flow.
            self.api.access_token = None
            raise ConfigEntryAuthFailed(
                f"Authentication error fetching properties for {self.dsn}: {err}"
            ) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(
                f"Unexpected error fetching properties for {self.dsn}: {err}"
            ) from err

        # ── Step 3: flatten the property list into a plain dict ───────
        data: dict[str, Any] = {}
        for prop in properties:
            if "property" in prop:
                prop_info = prop["property"]
                data[prop_info["name"]] = prop_info["value"]

        return data

    async def _maybe_reauthenticate(self) -> None:
        """Attempt a full re-authentication if the cooldown has elapsed.

        Raise UpdateFailed on connection failure, or ConfigEntryAuthFailed
        when the user needs to replace their credentials.
        """
        now = datetime.now()

        if (
            self._last_auth_attempt is not None
            and now - self._last_auth_attempt < _MIN_REAUTH_INTERVAL
        ):
            remaining = int(
                (_MIN_REAUTH_INTERVAL - (now - self._last_auth_attempt)).total_seconds()
            )
            _LOGGER.debug(
                "Skipping re-authentication for %s – cooldown active (%ds remaining).",
                self.dsn,
                remaining,
            )
            raise UpdateFailed(
                f"Access token missing for {self.dsn}; "
                f"next re-auth attempt in ~{remaining} s."
            )

        self._last_auth_attempt = now
        _LOGGER.info(
            "Access token missing for device %s – attempting re-authentication.", self.dsn
        )

        try:
            await self.api.authenticate()
            _LOGGER.info(
                "Re-authentication successful for device %s – resuming data updates.",
                self.dsn,
            )
        except DeLonghiAuthError as err:
            _LOGGER.error(
                "Re-authentication failed for %s (invalid credentials): %s",
                self.dsn,
                err,
            )
            raise ConfigEntryAuthFailed(
                f"Re-authentication rejected for {self.dsn}: {err}"
            ) from err
        except DeLonghiConnectionError as err:
            _LOGGER.warning(
                "Re-authentication for %s failed due to a connection error "
                "(will retry after cooldown): %s",
                self.dsn,
                err,
            )
            raise UpdateFailed(
                f"Re-authentication connection error for {self.dsn}: {err}"
            ) from err
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Unexpected error during re-authentication for %s: %s", self.dsn, err
            )
            raise UpdateFailed(
                f"Re-authentication unexpected error for {self.dsn}: {err}"
            ) from err

    # ------------------------------------------------------------------
    # Device-info helper (used by platform entities)
    # ------------------------------------------------------------------

    def get_device_info(self) -> DeviceInfo:
        """Return HA device-registry information for this coordinator's device."""
        data = self.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.dsn)},
            manufacturer="De'Longhi",
            model=data.get("appliance_model"),
            name=self.device_name,
            hw_version=data.get("hardware_version"),
            sw_version=(
                f"Firmware MDH:{data.get('firmware_version')} "
                f"/ Wi-Fi Module:{data.get('mcu_host_version')}"
            ),
        )
