"""Konfigurationsflöde för Badtemperatur."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .api import (
    DATASETS,
    CopernicusConnectionError,
    CopernicusMarineClient,
    MeasurementPoint,
    NoSeaDataError,
)
from .const import (
    CONF_DATASET,
    CONF_MAX_SEARCH_RADIUS,
    CONF_MEASUREMENT_LATITUDE,
    CONF_MEASUREMENT_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DATASET_AUTO,
    DEFAULT_MAX_SEARCH_RADIUS_KM,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SEARCH_RADIUS_KM,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_SEARCH_RADIUS_KM,
    MIN_UPDATE_INTERVAL_MINUTES,
)
from .coordinator import BadtemperaturConfigEntry

_LOGGER = logging.getLogger(__name__)

DATASET_OPTIONS = [DATASET_AUTO, *(dataset.key for dataset in DATASETS)]


def _location_schema(
    latitude: float,
    longitude: float,
    radius_km: float,
    dataset: str,
) -> vol.Schema:
    """Bygg schemat för plats, sökradie och datakälla."""
    return vol.Schema(
        {
            vol.Required(
                CONF_LOCATION,
                default={CONF_LATITUDE: latitude, CONF_LONGITUDE: longitude},
            ): LocationSelector(LocationSelectorConfig(radius=False)),
            vol.Required(CONF_MAX_SEARCH_RADIUS, default=radius_km): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SEARCH_RADIUS_KM,
                    max=MAX_SEARCH_RADIUS_KM,
                    step=0.5,
                    unit_of_measurement="km",
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(CONF_DATASET, default=dataset): SelectSelector(
                SelectSelectorConfig(
                    options=DATASET_OPTIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="dataset",
                )
            ),
        }
    )


class BadtemperaturConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hanterar konfiguration av en badplats via gränssnittet."""

    VERSION = 1

    async def _async_resolve(
        self, user_input: dict[str, Any]
    ) -> tuple[MeasurementPoint | None, dict[str, str]]:
        """Slå upp närmaste mätpunkt med havsdata."""
        client = CopernicusMarineClient(async_get_clientsession(self.hass))
        dataset = user_input[CONF_DATASET]
        try:
            point = await client.async_find_measurement_point(
                user_input[CONF_LOCATION][CONF_LATITUDE],
                user_input[CONF_LOCATION][CONF_LONGITUDE],
                float(user_input[CONF_MAX_SEARCH_RADIUS]),
                None if dataset == DATASET_AUTO else dataset,
            )
        except CopernicusConnectionError:
            return None, {"base": "cannot_connect"}
        except NoSeaDataError:
            return None, {"base": "no_sea_nearby"}
        except Exception:
            _LOGGER.exception("Oväntat fel vid uppslag av mätpunkt")
            return None, {"base": "unknown"}
        return point, {}

    @staticmethod
    def _entry_data(
        user_input: dict[str, Any], point: MeasurementPoint
    ) -> dict[str, Any]:
        """Bygg konfigurationsdata för posten."""
        return {
            CONF_LATITUDE: user_input[CONF_LOCATION][CONF_LATITUDE],
            CONF_LONGITUDE: user_input[CONF_LOCATION][CONF_LONGITUDE],
            CONF_MAX_SEARCH_RADIUS: float(user_input[CONF_MAX_SEARCH_RADIUS]),
            CONF_DATASET: point.dataset.key,
            CONF_MEASUREMENT_LATITUDE: point.latitude,
            CONF_MEASUREMENT_LONGITUDE: point.longitude,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Lägg till en ny badplats."""
        errors: dict[str, str] = {}

        if user_input is not None:
            latitude = user_input[CONF_LOCATION][CONF_LATITUDE]
            longitude = user_input[CONF_LOCATION][CONF_LONGITUDE]
            await self.async_set_unique_id(f"{latitude:.4f},{longitude:.4f}")
            self._abort_if_unique_id_configured()

            point, errors = await self._async_resolve(user_input)
            if point is not None:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=self._entry_data(user_input, point),
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES},
                )

        suggested = user_input or {}
        location = suggested.get(CONF_LOCATION, {})
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=suggested.get(CONF_NAME, "")
                ): TextSelector(),
            }
        ).extend(
            _location_schema(
                location.get(CONF_LATITUDE, self.hass.config.latitude),
                location.get(CONF_LONGITUDE, self.hass.config.longitude),
                suggested.get(CONF_MAX_SEARCH_RADIUS, DEFAULT_MAX_SEARCH_RADIUS_KM),
                suggested.get(CONF_DATASET, DATASET_AUTO),
            ).schema
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ändra plats, sökradie eller datakälla för en befintlig badplats."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            point, errors = await self._async_resolve(user_input)
            if point is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._entry_data(user_input, point)
                )

        location = (user_input or {}).get(CONF_LOCATION, {})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_location_schema(
                location.get(CONF_LATITUDE, entry.data[CONF_LATITUDE]),
                location.get(CONF_LONGITUDE, entry.data[CONF_LONGITUDE]),
                entry.data.get(CONF_MAX_SEARCH_RADIUS, DEFAULT_MAX_SEARCH_RADIUS_KM),
                entry.data.get(CONF_DATASET, DATASET_AUTO),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: BadtemperaturConfigEntry,
    ) -> BadtemperaturOptionsFlow:
        """Returnera flödet för inställningar."""
        return BadtemperaturOptionsFlow()


class BadtemperaturOptionsFlow(OptionsFlowWithReload):
    """Inställningar som kan ändras utan att slå upp mätpunkten på nytt."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Hantera uppdateringsintervallet."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL])}
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_UPDATE_INTERVAL_MINUTES,
                            max=MAX_UPDATE_INTERVAL_MINUTES,
                            step=15,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
