"""Delade fixtures för Badtemperatur-testerna."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.badtemperatur.api import (
    DATASETS_BY_KEY,
    MeasurementPoint,
    SeaTemperature,
)
from custom_components.badtemperatur.const import (
    CONF_DATASET,
    CONF_MAX_SEARCH_RADIUS,
    CONF_MEASUREMENT_LATITUDE,
    CONF_MEASUREMENT_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"

BALTIC = DATASETS_BY_KEY["baltic"]

MEASUREMENT_POINT = MeasurementPoint(
    dataset=BALTIC,
    latitude=56.64,
    longitude=12.72,
    distance_km=1.23,
)

SEA_TEMPERATURE = SeaTemperature(
    temperature=18.26,
    observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    latitude=56.64,
    longitude=12.72,
    dataset=BALTIC,
    distance_km=1.23,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Aktivera anpassade integrationer i alla tester."""
    return


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Ersätt Copernicus-klienten med en mock."""
    with (
        patch(
            "custom_components.badtemperatur.CopernicusMarineClient",
            autospec=True,
        ) as mock,
        patch(
            "custom_components.badtemperatur.config_flow.CopernicusMarineClient",
            new=mock,
        ),
    ):
        client = mock.return_value
        client.async_find_measurement_point.return_value = MEASUREMENT_POINT
        client.async_get_temperature.return_value = SEA_TEMPERATURE
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Skapa en konfigurerad post."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Tylösand",
        unique_id="56.6500,12.7200",
        data={
            CONF_LATITUDE: 56.65,
            CONF_LONGITUDE: 12.72,
            CONF_MAX_SEARCH_RADIUS: 5.0,
            CONF_DATASET: "baltic",
            CONF_MEASUREMENT_LATITUDE: 56.64,
            CONF_MEASUREMENT_LONGITUDE: 12.72,
        },
        options={CONF_UPDATE_INTERVAL: 60},
    )
