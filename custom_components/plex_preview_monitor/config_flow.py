"""Config flow for Plex Preview Monitor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PlexPreviewApiClient, PlexPreviewAuthError, PlexPreviewCannotConnectError
from .const import (
    CONF_DEFAULT_LIBRARY_ID,
    CONF_DEFAULT_LIBRARY_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, description={"suggested_value": "http://192.168.1.x:8080"}): str,
        vol.Optional(CONF_TOKEN, default=""): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=300)
        ),
    }
)


class PlexPreviewConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            token = user_input.get(CONF_TOKEN, "")

            try:
                session = async_get_clientsession(self.hass)
                client = PlexPreviewApiClient(url=url, token=token, session=session)
                await client.async_validate_connection()
            except PlexPreviewAuthError:
                errors["base"] = "invalid_auth"
            except PlexPreviewCannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Plex Preview ({url})",
                    data={
                        CONF_URL: url,
                        CONF_TOKEN: token,
                        CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    },
                )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PlexPreviewOptionsFlow(config_entry)


class PlexPreviewOptionsFlow(OptionsFlow):
    """Handle options (scan interval / token / defaults)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        self._libraries: list[dict] = []

    async def _fetch_libraries(self, url: str, token: str) -> None:
        try:
            session = async_get_clientsession(self.hass)
            client = PlexPreviewApiClient(url=url, token=token, session=session)
            self._libraries = await client.get_libraries()
        except Exception:  # noqa: BLE001
            self._libraries = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self.config_entry.options or self.config_entry.data
        url = current.get(CONF_URL, "")
        token = (user_input or {}).get(CONF_TOKEN, current.get(CONF_TOKEN, ""))

        if user_input is not None:
            # Map selected name -> id if we can
            selected_name = user_input.get(CONF_DEFAULT_LIBRARY_NAME)
            if selected_name and self._libraries:
                for lib in self._libraries:
                    if lib.get("name") == selected_name:
                        user_input[CONF_DEFAULT_LIBRARY_ID] = str(lib.get("id"))
                        user_input[CONF_DEFAULT_LIBRARY_NAME] = selected_name
                        break
            return self.async_create_entry(title="", data=user_input)

        await self._fetch_libraries(url=url, token=token)

        lib_names = [lib.get("name") for lib in self._libraries if lib.get("name")]
        lib_names = sorted(set(lib_names))

        schema_dict: dict[Any, Any] = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            vol.Optional(
                CONF_TOKEN,
                default=current.get(CONF_TOKEN, ""),
            ): str,
        }

        if lib_names:
            schema_dict[vol.Optional(
                CONF_DEFAULT_LIBRARY_NAME,
                default=current.get(CONF_DEFAULT_LIBRARY_NAME, lib_names[0]),
            )] = vol.In(lib_names)

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))
