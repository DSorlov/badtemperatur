"""Klient mot Copernicus Marine WMTS för havsytetemperatur (SST).

Data kommer från Copernicus Marine Service L4-produkter som bland annat bygger på
Sentinel-3 SLSTR. Värdena hämtas punktvis med WMTS-operationen ``GetFeatureInfo``,
vilket gör att integrationen klarar sig med enkla HTTP-anrop utan tunga beroenden.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import logging
import math
from typing import Any, Final

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

WMTS_ENDPOINT: Final = "https://wmts.marine.copernicus.eu/teroWmts"
TILE_MATRIX_SET: Final = "EPSG:4326"
TILE_MATRIX: Final = 10
TILE_SIZE: Final = 256

KELVIN_OFFSET: Final = 273.15
MIN_PLAUSIBLE_KELVIN: Final = 250.0
MAX_PLAUSIBLE_KELVIN: Final = 330.0

MIN_LATITUDE: Final = -90.0
MAX_LATITUDE: Final = 90.0

EARTH_RADIUS_KM: Final = 6371.0088
DEGREE_KM: Final = 111.32

REQUEST_TIMEOUT: Final = ClientTimeout(total=30)
NO_DATA_STATUSES: Final = frozenset({400, 404})
MAX_SEARCH_RINGS: Final = 5
MAX_LOOKBACK_DAYS: Final = 5
CONCURRENT_PROBES: Final = 6


class BadtemperaturError(Exception):
    """Basfel för Copernicus-klienten."""


class CopernicusConnectionError(BadtemperaturError):
    """Kommunikationen med Copernicus Marine misslyckades."""


class NoSeaDataError(BadtemperaturError):
    """Ingen giltig havsdata hittades för positionen."""


@dataclass(frozen=True, kw_only=True, slots=True)
class Dataset:
    """Beskriver ett SST-lager i Copernicus Marine-katalogen."""

    key: str
    name: str
    layer: str
    resolution: float
    """Rutnätets upplösning i grader."""
    bbox: tuple[float, float, float, float]
    """Täckning som (min_lon, min_lat, max_lon, max_lat)."""

    def covers(self, latitude: float, longitude: float) -> bool:
        """Returnera True om positionen ligger inom datasetets täckning."""
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon


# Ordnade efter prioritet: regionala högupplösta produkter före den globala.
DATASETS: Final[tuple[Dataset, ...]] = (
    Dataset(
        key="baltic",
        name="Baltic Sea SST L4 NRT (DMI)",
        layer=(
            "SST_BAL_SST_L4_NRT_OBSERVATIONS_010_007_b/"
            "DMI-BALTIC-SST-L4-NRT-OBS_FULL_TIME_SERIE_202511/analysed_sst"
        ),
        resolution=0.02,
        # Produkten publiceras över -10..30 E / 48..66 N, men är avsedd för
        # Östersjön, Kattegatt och Skagerrak. Övriga hav täcks bättre av
        # regionala produkter med högre upplösning.
        bbox=(7.0, 53.0, 30.0, 66.0),
    ),
    Dataset(
        key="atlantic",
        name="North Atlantic & European Seas SST L4 NRT (IFREMER)",
        layer=(
            "SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/"
            "IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE_201904/analysed_sst"
        ),
        resolution=0.01,
        bbox=(-21.0, 9.0, 13.0, 62.0),
    ),
    Dataset(
        key="mediterranean",
        name="Mediterranean Sea SST L4 NRT",
        layer=(
            "SST_MED_SST_L4_NRT_OBSERVATIONS_010_004/"
            "SST_MED_SST_L4_NRT_OBSERVATIONS_010_004_a_V2_202311/analysed_sst"
        ),
        resolution=0.01,
        bbox=(-18.125, 30.25, 36.25, 46.0),
    ),
    Dataset(
        key="black_sea",
        name="Black Sea SST L4 NRT",
        layer=(
            "SST_BS_SST_L4_NRT_OBSERVATIONS_010_006/"
            "SST_BS_SST_L4_NRT_OBSERVATIONS_010_006_a_V2_202311/analysed_sst"
        ),
        resolution=0.01,
        bbox=(26.375, 38.75, 42.375, 48.8125),
    ),
    Dataset(
        key="global",
        name="Global Ocean SST L4 NRT (OSTIA)",
        layer=(
            "SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001/"
            "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2/analysed_sst"
        ),
        resolution=0.05,
        bbox=(-180.0, -90.0, 180.0, 90.0),
    ),
)

DATASETS_BY_KEY: Final[dict[str, Dataset]] = {
    dataset.key: dataset for dataset in DATASETS
}


@dataclass(frozen=True, kw_only=True, slots=True)
class MeasurementPoint:
    """En upplöst mätpunkt i ett datasets rutnät."""

    dataset: Dataset
    latitude: float
    longitude: float
    distance_km: float


@dataclass(frozen=True, kw_only=True, slots=True)
class SeaTemperature:
    """Ett avläst temperaturvärde."""

    temperature: float
    """Havsytetemperatur i grader Celsius."""
    observed_at: datetime
    latitude: float
    longitude: float
    dataset: Dataset
    distance_km: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Beräkna storcirkelavståndet mellan två punkter i kilometer."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def tile_indices(latitude: float, longitude: float) -> tuple[int, int, int, int]:
    """Konvertera WGS84-koordinater till WMTS-index ``(col, row, i, j)``.

    Copernicus WMTS använder rutnätet WorldCRS84Quad för ``EPSG:4326``, där nivå
    ``z`` har ``2**(z+1)`` kolumner och ``2**z`` rader med origo i övre vänstra
    hörnet (-180, 90).
    """
    columns = 2 ** (TILE_MATRIX + 1)
    rows = 2**TILE_MATRIX
    x = (longitude + 180.0) / 360.0 * columns
    y = (90.0 - latitude) / 180.0 * rows
    column = min(max(int(x), 0), columns - 1)
    row = min(max(int(y), 0), rows - 1)
    pixel_i = min(max(int((x - column) * TILE_SIZE), 0), TILE_SIZE - 1)
    pixel_j = min(max(int((y - row) * TILE_SIZE), 0), TILE_SIZE - 1)
    return column, row, pixel_i, pixel_j


def _ring_offsets(ring: int) -> Iterator[tuple[int, int]]:
    """Ge alla heltalsoffset som ligger på en kvadratisk ring runt origo."""
    if ring == 0:
        yield (0, 0)
        return
    for delta_y in range(-ring, ring + 1):
        for delta_x in range(-ring, ring + 1):
            if max(abs(delta_x), abs(delta_y)) == ring:
                yield (delta_x, delta_y)


def _parse_feature_info(payload: Any) -> tuple[float, float, float] | None:
    """Plocka ut ``(kelvin, lat, lon)`` ur ett GetFeatureInfo-svar."""
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        return None
    feature = features[0]
    properties = feature.get("properties") if isinstance(feature, dict) else None
    if not isinstance(properties, dict):
        return None

    numbers = (
        properties.get("value"),
        properties.get("lat"),
        properties.get("lon"),
    )
    if any(
        isinstance(number, bool) or not isinstance(number, (int, float))
        for number in numbers
    ):
        return None

    value, latitude, longitude = (float(number) for number in numbers)
    if not MIN_PLAUSIBLE_KELVIN <= value <= MAX_PLAUSIBLE_KELVIN:
        _LOGGER.debug("Ignorerar orimligt SST-värde: %s K", value)
        return None
    return value, latitude, longitude


class CopernicusMarineClient:
    """Läser punktvärden ur Copernicus Marine WMTS."""

    def __init__(self, session: ClientSession) -> None:
        """Initiera klienten med en delad aiohttp-session."""
        self._session = session
        self._semaphore = asyncio.Semaphore(CONCURRENT_PROBES)

    async def _async_feature_info(
        self,
        dataset: Dataset,
        latitude: float,
        longitude: float,
        day: date | None = None,
    ) -> tuple[float, float, float] | None:
        """Utför en GetFeatureInfo-förfrågan för en enskild punkt."""
        column, row, pixel_i, pixel_j = tile_indices(latitude, longitude)
        params: dict[str, str] = {
            "service": "WMTS",
            "version": "1.0.0",
            "request": "GetFeatureInfo",
            "layer": dataset.layer,
            "tilematrixset": TILE_MATRIX_SET,
            "tilematrix": str(TILE_MATRIX),
            "tilerow": str(row),
            "tilecol": str(column),
            "i": str(pixel_i),
            "j": str(pixel_j),
            "INFOFORMAT": "application/json",
        }
        if day is not None:
            params["time"] = f"{day.isoformat()}T00:00:00.000Z"

        async with self._semaphore:
            try:
                async with self._session.get(
                    WMTS_ENDPOINT,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                    raise_for_status=True,
                ) as response:
                    payload = await response.json(content_type=None)
            except ClientResponseError as err:
                # WMTS svarar 400/404 när ett lager saknar det efterfrågade
                # datumet, vilket inte är ett anslutningsfel.
                if err.status in NO_DATA_STATUSES:
                    _LOGGER.debug(
                        "Ingen data för %s (%s): HTTP %s",
                        dataset.key,
                        day,
                        err.status,
                    )
                    return None
                raise CopernicusConnectionError(
                    f"Copernicus Marine WMTS svarade med HTTP {err.status}"
                ) from err
            except (ClientError, TimeoutError) as err:
                raise CopernicusConnectionError(
                    f"Kunde inte nå Copernicus Marine WMTS: {err}"
                ) from err
            except ValueError as err:
                raise CopernicusConnectionError(
                    "Copernicus Marine WMTS returnerade ett ogiltigt svar"
                ) from err

        return _parse_feature_info(payload)

    async def async_find_measurement_point(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        dataset_key: str | None = None,
    ) -> MeasurementPoint:
        """Hitta närmaste rutnätspunkt med havsdata.

        Positioner nära stranden hamnar ofta på en landmaskerad ruta. Därför söks
        omgivningen av i ringar tills en ruta med giltigt värde hittas.
        """
        if dataset_key is not None:
            dataset = DATASETS_BY_KEY.get(dataset_key)
            if dataset is None:
                raise NoSeaDataError(f"Okänt dataset: {dataset_key}")
            candidates: tuple[Dataset, ...] = (dataset,)
        else:
            candidates = tuple(
                dataset for dataset in DATASETS if dataset.covers(latitude, longitude)
            )

        for dataset in candidates:
            point = await self._async_search_dataset(
                dataset, latitude, longitude, radius_km
            )
            if point is not None:
                return point

        raise NoSeaDataError(
            f"Hittade ingen havsdata inom {radius_km:.1f} km från "
            f"{latitude:.4f}, {longitude:.4f}"
        )

    async def _async_search_dataset(
        self,
        dataset: Dataset,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> MeasurementPoint | None:
        """Sök ring för ring i ett dataset efter närmaste giltiga ruta."""
        # Stegar minst en rutnätscell, men grovare för stora sökradier så att
        # antalet förfrågningar hålls nere.
        step_deg = max(dataset.resolution, radius_km / DEGREE_KM / MAX_SEARCH_RINGS)
        lat_km_per_step = step_deg * DEGREE_KM
        max_ring = (
            0
            if radius_km <= 0
            else min(math.ceil(radius_km / lat_km_per_step), MAX_SEARCH_RINGS)
        )
        cos_lat = max(math.cos(math.radians(latitude)), 0.01)

        for ring in range(max_ring + 1):
            probes: list[tuple[float, float]] = []
            for delta_x, delta_y in _ring_offsets(ring):
                probe_lat = latitude + delta_y * step_deg
                probe_lon = longitude + delta_x * step_deg / cos_lat
                if not MIN_LATITUDE <= probe_lat <= MAX_LATITUDE:
                    continue
                probe_lon = (probe_lon + 180.0) % 360.0 - 180.0
                distance = haversine_km(latitude, longitude, probe_lat, probe_lon)
                if ring and distance > radius_km:
                    continue
                probes.append((probe_lat, probe_lon))

            if not probes:
                continue

            results = await asyncio.gather(
                *(
                    self._async_feature_info(dataset, probe_lat, probe_lon)
                    for probe_lat, probe_lon in probes
                )
            )

            best: MeasurementPoint | None = None
            for result in results:
                if result is None:
                    continue
                _, found_lat, found_lon = result
                distance = haversine_km(latitude, longitude, found_lat, found_lon)
                if best is None or distance < best.distance_km:
                    best = MeasurementPoint(
                        dataset=dataset,
                        latitude=found_lat,
                        longitude=found_lon,
                        distance_km=distance,
                    )
            if best is not None:
                return best

        return None

    async def async_get_temperature(
        self,
        point: MeasurementPoint,
        *,
        now: datetime | None = None,
    ) -> SeaTemperature:
        """Hämta senaste tillgängliga temperatur för en upplöst mätpunkt.

        L4-produkterna publiceras dygnsvis. Dagens fil kan saknas beroende på när
        på dygnet anropet görs, så några dygn bakåt provas innan det ger upp.
        """
        today = (now or datetime.now(UTC)).astimezone(UTC).date()

        for offset in range(MAX_LOOKBACK_DAYS):
            day = today - timedelta(days=offset)
            result = await self._async_feature_info(
                point.dataset, point.latitude, point.longitude, day
            )
            if result is None:
                continue
            kelvin, found_lat, found_lon = result
            return SeaTemperature(
                temperature=round(kelvin - KELVIN_OFFSET, 2),
                observed_at=datetime.combine(day, time.min, tzinfo=UTC),
                latitude=found_lat,
                longitude=found_lon,
                dataset=point.dataset,
                distance_km=point.distance_km,
            )

        raise NoSeaDataError(
            f"Ingen data de senaste {MAX_LOOKBACK_DAYS} dygnen för "
            f"{point.latitude:.4f}, {point.longitude:.4f}"
        )
