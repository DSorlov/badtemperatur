"""Tester för diagnostik."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.badtemperatur.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_coordinates(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["entry"]["data"]["latitude"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["measurement_longitude"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["dataset"] == "baltic"
    assert diagnostics["dataset"]["key"] == "baltic"
    assert diagnostics["last_update_success"] is True
    assert diagnostics["measurement"]["temperature"] == 18.26
