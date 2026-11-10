"""Configuration and credential recovery for De'Longhi Comfort."""

import logging

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DeLonghiAPI
from .const import (
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_LANGUAGE,
    DOMAIN,
    LANGUAGES,
)
from .exceptions import DeLonghiAuthError, DeLonghiConnectionError

_LOGGER = logging.getLogger(__name__)


class DelonghiComfortConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for De'Longhi Comfort integration."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._username = None
        self._password = None
        self._language = None
        self._reauth_entry = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._language = user_input.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

            error = await self._validate_credentials(
                self._username, self._password, self._language
            )
            if error:
                errors["base"] = error
            else:
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

        return self.async_show_form(
            step_id="user", data_schema=self._get_schema(), errors=errors
        )

    async def _validate_credentials(self, username, password, language):
        """Validate credentials without changing an existing config entry."""
        api = DeLonghiAPI(
            username, password, async_get_clientsession(self.hass), language
        )
        try:
            await api.authenticate()
            devices = await api.get_devices()
        except DeLonghiAuthError as err:
            _LOGGER.warning("De'Longhi credential check failed: %s", err)
            return "invalid_auth"
        except DeLonghiConnectionError as err:
            _LOGGER.warning("De'Longhi connection check failed: %s", err)
            return "cannot_connect"
        except Exception as err:
            _LOGGER.error("Unexpected De'Longhi credential check failure: %s", type(err).__name__)
            return "unknown"
        return None if devices else "no_devices"

    async def async_step_reauth(self, entry_data):
        """Start credential recovery for the existing account."""
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="unknown")
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            entry_id
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Validate a replacement password, then reload the same entry."""
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")

        errors = {}
        if user_input is not None:
            error = await self._validate_credentials(
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
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
        return DelonghiComfortOptionsFlow()


class DelonghiComfortOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for De'Longhi Comfort integration."""

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
