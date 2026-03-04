"""Switch platform for Plex Preview Monitor (pause/resume)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PlexPreviewApiClient
from .const import CONF_URL, DATA_COORDINATOR, DOMAIN
from .coordinator import PlexPreviewCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: PlexPreviewApiClient = data["client"]
    coordinator: PlexPreviewCoordinator = data[DATA_COORDINATOR]
    async_add_entities([PlexPreviewPausedSwitch(client, coordinator, entry)])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Plex Preview Generator",
        manufacturer="stevezau",
        model="Plex Preview Generator",
        configuration_url=entry.data[CONF_URL],
    )


class PlexPreviewPausedSwitch(CoordinatorEntity[PlexPreviewCoordinator], SwitchEntity):
    """Switch to pause/resume processing."""

    _attr_has_entity_name = True
    _attr_name = "Processing Paused"
    _attr_icon = "mdi:pause-circle-outline"

    def __init__(
        self,
        client: PlexPreviewApiClient,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_processing_paused"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data.paused)

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.pause()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.resume()
        await self.coordinator.async_request_refresh()
