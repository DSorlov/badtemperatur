"""Tester för Copernicus Marine-klienten."""

from datetime import UTC, datetime
import re

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.badtemperatur.api import (
    DATASETS_BY_KEY,
    CopernicusConnectionError,
    CopernicusMarineClient,
    MeasurementPoint,
    NoSeaDataError,
    _parse_feature_info,
    haversine_km,
    tile_indices,
)

ANY_REQUEST = re.compile(r"^https://wmts\.marine\.copernicus\.eu/teroWmts.*$")
BALTIC = DATASETS_BY_KEY["baltic"]

POINT = MeasurementPoint(
    dataset=BALTIC, latitude=56.64, longitude=12.72, distance_km=0.0
)


def _request_for_day(day: str) -> re.Pattern[str]:
    return re.compile(rf"^https://wmts\.marine\.copernicus\.eu/teroWmts.*time={day}.*$")


def _feature(value: float | None, lat: float = 56.64, lon: float = 12.72) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "lat": lat if value is not None else None,
                    "lon": lon if value is not None else None,
                    "variableId": "analysed_sst",
                    "value": value,
                    "units": "kelvin",
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (0.0, 0.0, (1024, 512)),
        (90.0, -180.0, (0, 0)),
        (-90.0, 180.0, (2047, 1023)),
        (56.65, 12.72, (1096, 189)),
    ],
)
def test_tile_indices(latitude, longitude, expected) -> None:
    column, row, pixel_i, pixel_j = tile_indices(latitude, longitude)
    assert (column, row) == expected
    assert 0 <= pixel_i < 256
    assert 0 <= pixel_j < 256


def test_tile_indices_matches_documented_example() -> None:
    """Västra Australien ligger i kolumn 6, rad 2 på nivå 2 enligt Copernicus."""
    column, row, _, _ = tile_indices(-25.0, 115.0)
    scale = 2 ** (10 - 2)
    assert (column // scale, row // scale) == (6, 2)


def test_haversine_km() -> None:
    assert haversine_km(56.65, 12.72, 56.65, 12.72) == 0
    assert 1.0 < haversine_km(56.65, 12.72, 56.64, 12.72) < 1.3


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"features": []},
        {"features": [{"properties": {"value": None, "lat": 1.0, "lon": 1.0}}]},
        {"features": [{"properties": {"value": 5.0, "lat": 1.0, "lon": 1.0}}]},
        {"features": [{"properties": {"value": True, "lat": 1.0, "lon": 1.0}}]},
    ],
)
def test_parse_feature_info_rejects_invalid(payload) -> None:
    assert _parse_feature_info(payload) is None


def test_parse_feature_info_accepts_valid() -> None:
    assert _parse_feature_info(_feature(291.41)) == (291.41, 56.64, 12.72)


async def test_get_temperature_converts_kelvin(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(ANY_REQUEST, json=_feature(291.41))
    client = CopernicusMarineClient(async_get_clientsession(hass))

    result = await client.async_get_temperature(
        POINT, now=datetime(2026, 8, 26, 9, tzinfo=UTC)
    )

    assert result.temperature == pytest.approx(18.26)
    assert result.observed_at == datetime(2026, 8, 26, tzinfo=UTC)
    assert result.dataset is BALTIC


async def test_get_temperature_falls_back_to_previous_day(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(_request_for_day("2026-08-26"), json=_feature(None))
    aioclient_mock.get(_request_for_day("2026-08-25"), json=_feature(290.15))
    client = CopernicusMarineClient(async_get_clientsession(hass))

    result = await client.async_get_temperature(
        POINT, now=datetime(2026, 8, 26, 1, tzinfo=UTC)
    )

    assert result.observed_at == datetime(2026, 8, 25, tzinfo=UTC)
    assert result.temperature == pytest.approx(17.0)


async def test_get_temperature_without_data_raises(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(ANY_REQUEST, json=_feature(None))
    client = CopernicusMarineClient(async_get_clientsession(hass))

    with pytest.raises(NoSeaDataError):
        await client.async_get_temperature(POINT)


async def test_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(ANY_REQUEST, exc=ClientError)
    client = CopernicusMarineClient(async_get_clientsession(hass))

    with pytest.raises(CopernicusConnectionError):
        await client.async_get_temperature(POINT)


async def test_find_measurement_point_hits_first_probe(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(ANY_REQUEST, json=_feature(291.41))
    client = CopernicusMarineClient(async_get_clientsession(hass))

    point = await client.async_find_measurement_point(56.65, 12.72, 5.0)

    assert point.dataset is BALTIC
    assert point.latitude == 56.64
    assert point.distance_km < 2
    assert aioclient_mock.call_count == 1


async def test_find_measurement_point_searches_outwards(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Landmaskerade rutor ska få sökningen att expandera utåt."""
    aioclient_mock.get(ANY_REQUEST, json=_feature(None))
    client = CopernicusMarineClient(async_get_clientsession(hass))

    with pytest.raises(NoSeaDataError):
        await client.async_find_measurement_point(56.65, 12.72, 2.0)

    # Mittpunkten plus minst en ring av grannrutor ska ha efterfrågats.
    assert aioclient_mock.call_count > 1


async def test_find_measurement_point_unknown_dataset(hass: HomeAssistant) -> None:
    client = CopernicusMarineClient(async_get_clientsession(hass))

    with pytest.raises(NoSeaDataError):
        await client.async_find_measurement_point(56.65, 12.72, 0.0, "mars")
