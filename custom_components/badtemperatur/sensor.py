"""Sensorer för Badtemperatur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import SeaTemperature
from .const import (
    ATTR_DATASET,
    ATTR_DATASET_NAME,
    ATTR_DISTANCE_KM,
    ATTR_MEASUREMENT_LATITUDE,
    ATTR_MEASUREMENT_LONGITUDE,
)
from .coordinator import BadtemperaturConfigEntry, BadtemperaturCoordinator
from .entity import BadtemperaturEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BadtemperaturSensorEntityDescription(SensorEntityDescription):
    """Beskrivning av en Badtemperatur-sensor."""

    value_fn: Callable[[SeaTemperature], StateType | datetime]


SENSORS: tuple[BadtemperaturSensorEntityDescription, ...] = (
    BadtemperaturSensorEntityDescription(
        key="water_temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda data: data.temperature,
    ),
    BadtemperaturSensorEntityDescription(
        key="observed_at",
        translation_key="observed_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.observed_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BadtemperaturConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sätt upp sensorer för en konfigurationspost."""
    async_add_entities(
        BadtemperaturSensor(entry.runtime_data, description) for description in SENSORS
    )


class BadtemperaturSensor(BadtemperaturEntity, SensorEntity):
    """Sensor som visar värden från Copernicus Marine."""

    entity_description: BadtemperaturSensorEntityDescription

    def __init__(
        self,
        coordinator: BadtemperaturCoordinator,
        description: BadtemperaturSensorEntityDescription,
    ) -> None:
        """Initiera sensorn."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Returnera sensorns värde."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Returnera information om mätpunkten."""
        if self.entity_description.key != "water_temperature":
            return None
        data = self.coordinator.data
        return {
            ATTR_DATASET: data.dataset.key,
            ATTR_DATASET_NAME: data.dataset.name,
            ATTR_MEASUREMENT_LATITUDE: round(data.latitude, 4),
            ATTR_MEASUREMENT_LONGITUDE: round(data.longitude, 4),
            ATTR_DISTANCE_KM: round(data.distance_km, 2),
        }
