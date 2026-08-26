"""Badtemperatur - havsytetemperatur fran Copernicus Marine (Sentinel-3)."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CopernicusMarineClient
from .coordinator import BadtemperaturConfigEntry, BadtemperaturCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: BadtemperaturConfigEntry
) -> bool:
    """Sätt upp Badtemperatur från en konfigurationspost."""
    client = CopernicusMarineClient(async_get_clientsession(hass))
    coordinator = BadtemperaturCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BadtemperaturConfigEntry
) -> bool:
    """Ta bort en konfigurationspost."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
