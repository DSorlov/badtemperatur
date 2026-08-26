"""Tester för uppsättning och sensorer."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.badtemperatur.api import (
    CopernicusConnectionError,
    NoSeaDataError,
)
from custom_components.badtemperatur.const import CONF_DATASET, DOMAIN


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.tylosand_water_temperature")
    assert state is not None
    assert float(state.state) == pytest.approx(18.26)
    assert state.attributes["dataset"] == "baltic"
    assert state.attributes["distance_km"] == 1.23

    observed = hass.states.get("sensor.tylosand_observation_date")
    assert observed is not None
    assert observed.state == "2026-08-26T00:00:00+00:00"

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, mock_config_entry.entry_id)}
    )
    assert device is not None
    assert device.name == "Tylösand"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize("side_effect", [CopernicusConnectionError, NoSeaDataError])
async def test_setup_retries_on_error(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    side_effect: type[Exception],
) -> None:
    mock_client.async_get_temperature.side_effect = side_effect

    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unknown_dataset_fails_setup(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okänd",
        data={
            "latitude": 56.65,
            "longitude": 12.72,
            "max_search_radius": 5.0,
            CONF_DATASET: "mars",
            "measurement_latitude": 56.64,
            "measurement_longitude": 12.72,
        },
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_sensor_becomes_unavailable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry.runtime_data
    mock_client.async_get_temperature.side_effect = CopernicusConnectionError
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    entity_ids = hass.states.async_entity_ids("sensor")
    assert entity_ids
    assert all(
        hass.states.get(entity_id).state == STATE_UNAVAILABLE
        for entity_id in entity_ids
    )
