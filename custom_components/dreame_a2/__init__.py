"""The Dreame A2 Mower integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DreameApi, DreameAuthError, DreameError
from .const import CONF_DID, CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from .coordinator import DreameCoordinator

PLATFORMS: list[Platform] = [
    Platform.LAWN_MOWER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.CAMERA,
]

type DreameConfigEntry = ConfigEntry[DreameCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DreameConfigEntry) -> bool:
    """Set up Dreame A2 from a config entry."""
    session = async_get_clientsession(hass)
    api = DreameApi(
        session,
        email=entry.data[CONF_EMAIL],
        pw_hash=entry.data[CONF_PASSWORD],  # stored as a hash, never plaintext
        region=entry.data.get(CONF_REGION, "eu"),
        did=entry.data.get(CONF_DID),
    )
    try:
        await api.login()
    except DreameAuthError as err:
        from homeassistant.exceptions import ConfigEntryAuthFailed

        raise ConfigEntryAuthFailed(str(err)) from err
    except DreameError as err:
        from homeassistant.exceptions import ConfigEntryNotReady

        raise ConfigEntryNotReady(str(err)) from err

    coordinator = DreameCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DreameConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
