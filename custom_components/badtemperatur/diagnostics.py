"""Diagnostik för Badtemperatur."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import CONF_MEASUREMENT_LATITUDE, CONF_MEASUREMENT_LONGITUDE
from .coordinator import BadtemperaturConfigEntry

TO_REDACT = {
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MEASUREMENT_LATITUDE,
    CONF_MEASUREMENT_LONGITUDE,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BadtemperaturConfigEntry
) -> dict[str, Any]:
    """Returnera diagnostikdata för en konfigurationspost."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "dataset": {
            "key": coordinator.point.dataset.key,
            "layer": coordinator.point.dataset.layer,
            "resolution": coordinator.point.dataset.resolution,
        },
        "last_update_success": coordinator.last_update_success,
        "measurement": {
            "temperature": data.temperature,
            "observed_at": data.observed_at.isoformat(),
            "distance_km": round(data.distance_km, 3),
        }
        if data is not None
        else None,
    }
