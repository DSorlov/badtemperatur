"""Konstanter för Badtemperatur."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "badtemperatur"

CONF_DATASET: Final = "dataset"
CONF_MAX_SEARCH_RADIUS: Final = "max_search_radius"
CONF_MEASUREMENT_LATITUDE: Final = "measurement_latitude"
CONF_MEASUREMENT_LONGITUDE: Final = "measurement_longitude"
CONF_UPDATE_INTERVAL: Final = "update_interval"

DATASET_AUTO: Final = "auto"

DEFAULT_MAX_SEARCH_RADIUS_KM: Final = 5.0
MIN_SEARCH_RADIUS_KM: Final = 0.0
MAX_SEARCH_RADIUS_KM: Final = 25.0

DEFAULT_UPDATE_INTERVAL_MINUTES: Final = 60
MIN_UPDATE_INTERVAL_MINUTES: Final = 15
MAX_UPDATE_INTERVAL_MINUTES: Final = 1440

ATTRIBUTION: Final = "E.U. Copernicus Marine Service Information"

ATTR_DATASET: Final = "dataset"
ATTR_DATASET_NAME: Final = "dataset_name"
ATTR_DISTANCE_KM: Final = "distance_km"
ATTR_MEASUREMENT_LATITUDE: Final = "measurement_latitude"
ATTR_MEASUREMENT_LONGITUDE: Final = "measurement_longitude"
