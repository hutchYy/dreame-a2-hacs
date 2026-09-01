"""Config flow for Dreame A2."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DreameApi, DreameAuthError, DreameError, hash_password
from .const import (
    CONF_DID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DEFAULT_REGION,
    DOMAIN,
    REGIONS,
)


class DreameConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup: email + password + region."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            pw_hash = hash_password(user_input[CONF_PASSWORD])
            api = DreameApi(
                session,
                email=user_input[CONF_EMAIL],
                pw_hash=pw_hash,
                region=user_input[CONF_REGION],
            )
            try:
                await api.login()
                did = await api.get_did()
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except DreameError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(did))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Dreame A2 ({user_input[CONF_EMAIL]})",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: pw_hash,  # store the hash, not the plaintext
                        CONF_REGION: user_input[CONF_REGION],
                        CONF_DID: did,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(REGIONS),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
