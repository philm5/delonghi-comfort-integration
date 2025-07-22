"""Data update coordinator for De'Longhi Comfort integration."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeLonghiAPI
from .const import SCAN_INTERVAL, CONF_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class DeLonghiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates for De'Longhi devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DeLonghiAPI,
        dsn: str,
        device_info: dict[str, Any],
        config_entry,
    ) -> None:
        """Initialize the coordinator."""
        # Get scan interval from options, fallback to default
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"delonghi_comfort_{dsn}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.dsn = dsn
        self.device_name = device_info.get("product_name", f"De'Longhi {dsn}")
        self.device_model = device_info.get("model", "Unknown")
        self.device_version = device_info.get("sw_version")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API."""
        try:
            properties = await self.api.get_device_properties(self.dsn)

            # Parse properties into a more usable format
            data = {}
            for prop in properties:
                if "property" in prop:
                    prop_info = prop["property"]
                    data[prop_info["name"]] = prop_info["value"]

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            return data
