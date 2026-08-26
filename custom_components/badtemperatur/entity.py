"""Gemensam entitetsbas för Badtemperatur."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import BadtemperaturCoordinator


class BadtemperaturEntity(CoordinatorEntity[BadtemperaturCoordinator]):
    """Basklass som knyter entiteter till platsens serviceenhet."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: BadtemperaturCoordinator, key: str) -> None:
        """Initiera entiteten."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Copernicus Marine Service",
            model=coordinator.point.dataset.name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://data.marine.copernicus.eu/viewer",
        )
