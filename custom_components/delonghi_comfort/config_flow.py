import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import logging

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_LANGUAGE,
    LANGUAGES,
    DEFAULT_LANGUAGE,
    CONF_SCAN_INTERVAL,
)
from .api import DeLonghiAPI

_LOGGER = logging.getLogger(__name__)


class DelonghiComfortConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for De'Longhi Comfort integration."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._username = None
        self._password = None
        self._language = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._language = user_input.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

            # Test the credentials
            session = async_get_clientsession(self.hass)
            api = DeLonghiAPI(self._username, self._password, session, self._language)
            try:
                if await api.authenticate():
                    devices = await api.get_devices()
                    if devices:
                        # Create a unique ID based on username
                        await self.async_set_unique_id(self._username)
                        self._abort_if_unique_id_configured()

                        return self.async_create_entry(
                            title=f"De'Longhi Comfort ({self._username})",
                            data={
                                CONF_USERNAME: self._username,
                                CONF_PASSWORD: self._password,
                                CONF_LANGUAGE: self._language,
                            },
                        )
                    else:
                        errors["base"] = "no_devices"
                else:
                    errors["base"] = "invalid_auth"
            except Exception as e:
                _LOGGER.error("Unexpected error during authentication: %s", e)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=self._get_schema(), errors=errors
        )

    @callback
    def _get_schema(self):
        """Return the schema for the user input form."""
        return vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): vol.In(
                    list(LANGUAGES.keys())
                ),
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return DelonghiComfortOptionsFlow(config_entry)


class DelonghiComfortOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for De'Longhi Comfort integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, 15),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
        )
