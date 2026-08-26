"""DataUpdateCoordinator för Badtemperatur."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DATASETS_BY_KEY,
    CopernicusConnectionError,
    CopernicusMarineClient,
    MeasurementPoint,
    NoSeaDataError,
    SeaTemperature,
    haversine_km,
)
from .const import (
    CONF_DATASET,
    CONF_MEASUREMENT_LATITUDE,
    CONF_MEASUREMENT_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type BadtemperaturConfigEntry = ConfigEntry[BadtemperaturCoordinator]


class BadtemperaturCoordinator(DataUpdateCoordinator[SeaTemperature]):
    """Hämtar havsytetemperatur från Copernicus Marine med jämna mellanrum."""

    config_entry: BadtemperaturConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: BadtemperaturConfigEntry,
        client: CopernicusMarineClient,
    ) -> None:
        """Initiera coordinatorn utifrån konfigurationsposten."""
        interval = config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=config_entry.title,
            update_interval=timedelta(minutes=interval),
        )
        self._client = client

        dataset = DATASETS_BY_KEY.get(config_entry.data[CONF_DATASET])
        if dataset is None:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="unknown_dataset",
                translation_placeholders={"dataset": config_entry.data[CONF_DATASET]},
            )

        self.point = MeasurementPoint(
            dataset=dataset,
            latitude=config_entry.data[CONF_MEASUREMENT_LATITUDE],
            longitude=config_entry.data[CONF_MEASUREMENT_LONGITUDE],
            distance_km=haversine_km(
                config_entry.data[CONF_LATITUDE],
                config_entry.data[CONF_LONGITUDE],
                config_entry.data[CONF_MEASUREMENT_LATITUDE],
                config_entry.data[CONF_MEASUREMENT_LONGITUDE],
            ),
        )

    async def _async_update_data(self) -> SeaTemperature:
        """Hämta senaste värdet."""
        try:
            return await self._client.async_get_temperature(self.point)
        except CopernicusConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except NoSeaDataError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="no_recent_data",
            ) from err
