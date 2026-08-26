"""Tester för konfigurationsflödet."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.badtemperatur.api import (
    CopernicusConnectionError,
    NoSeaDataError,
)
from custom_components.badtemperatur.const import (
    CONF_DATASET,
    CONF_MAX_SEARCH_RADIUS,
    CONF_MEASUREMENT_LATITUDE,
    CONF_UPDATE_INTERVAL,
    DATASET_AUTO,
    DOMAIN,
)

USER_INPUT = {
    CONF_NAME: "Tylösand",
    CONF_LOCATION: {CONF_LATITUDE: 56.65, CONF_LONGITUDE: 12.72},
    CONF_MAX_SEARCH_RADIUS: 5.0,
    CONF_DATASET: DATASET_AUTO,
}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tylösand"
    assert result["data"][CONF_DATASET] == "baltic"
    assert result["data"][CONF_MEASUREMENT_LATITUDE] == 56.64
    assert result["options"] == {CONF_UPDATE_INTERVAL: 60}
    assert result["result"].unique_id == "56.6500,12.7200"


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CopernicusConnectionError, "cannot_connect"),
        (NoSeaDataError, "no_sea_nearby"),
        (RuntimeError, "unknown"),
    ],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    side_effect: type[Exception],
    error: str,
) -> None:
    mock_client.async_find_measurement_point.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.async_find_measurement_point.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_location_aborts(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_multiple_locations(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Flera badplatser ska kunna läggas till."""
    for latitude in (56.65, 57.65):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                **USER_INPUT,
                CONF_LOCATION: {CONF_LATITUDE: latitude, CONF_LONGITUDE: 12.72},
            },
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY

    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCATION: {CONF_LATITUDE: 56.70, CONF_LONGITUDE: 12.70},
            CONF_MAX_SEARCH_RADIUS: 10.0,
            CONF_DATASET: "baltic",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_LATITUDE] == 56.70
    assert mock_config_entry.data[CONF_MAX_SEARCH_RADIUS] == 10.0


async def test_options_flow(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 180}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_UPDATE_INTERVAL] == 180
