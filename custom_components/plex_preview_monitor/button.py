"""Button platform for Plex Preview Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PlexPreviewApiClient
from .const import CONF_URL, DATA_COORDINATOR, DOMAIN
from .coordinator import PlexPreviewCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: PlexPreviewApiClient = data["client"]
    coordinator: PlexPreviewCoordinator = data[DATA_COORDINATOR]

    entities: list[ButtonEntity] = [
        PlexPreviewPauseButton(client, coordinator, entry),
        PlexPreviewResumeButton(client, coordinator, entry),
        PlexPreviewClearCompletedFailedButton(client, coordinator, entry),
    ]

    def add_dynamic() -> list[ButtonEntity]:
        dynamic: list[ButtonEntity] = []
        if not coordinator.data:
            return dynamic

        # Libraries
        for lib in coordinator.data.libraries or []:
            lib_id = str(lib.get("id", ""))
            lib_name = lib.get("name") or lib_id or "Library"
            if lib_id:
                dynamic.append(PlexPreviewLibraryButton(client, coordinator, entry, lib_id, lib_name))

        # Schedules
        for sched in coordinator.data.schedules or []:
            sid = str(sched.get("id", ""))
            sname = sched.get("name") or sid or "Schedule"
            if sid:
                dynamic.append(PlexPreviewRunScheduleButton(client, coordinator, entry, sid, sname))

        return dynamic

    # Add whatever we already know
    dynamic_entities = add_dynamic()
    entities.extend(dynamic_entities)
    async_add_entities(entities)

    known_library_ids: set[str] = set()
    known_schedule_ids: set[str] = set()

    if coordinator.data:
        known_library_ids = {str(l.get("id")) for l in (coordinator.data.libraries or []) if l.get("id") is not None}
        known_schedule_ids = {str(s.get("id")) for s in (coordinator.data.schedules or []) if s.get("id") is not None}

    def _handle_coordinator_update() -> None:
        if not coordinator.data:
            return
        new_entities: list[ButtonEntity] = []

        for lib in coordinator.data.libraries or []:
            if lib.get("id") is None:
                continue
            lib_id = str(lib.get("id"))
            if lib_id in known_library_ids:
                continue
            known_library_ids.add(lib_id)
            lib_name = lib.get("name") or lib_id
            new_entities.append(PlexPreviewLibraryButton(client, coordinator, entry, lib_id, lib_name))

        for sched in coordinator.data.schedules or []:
            if sched.get("id") is None:
                continue
            sid = str(sched.get("id"))
            if sid in known_schedule_ids:
                continue
            known_schedule_ids.add(sid)
            sname = sched.get("name") or sid
            new_entities.append(PlexPreviewRunScheduleButton(client, coordinator, entry, sid, sname))

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Plex Preview Generator",
        manufacturer="stevezau",
        model="Plex Preview Generator",
        configuration_url=entry.data[CONF_URL],
    )


class PlexPreviewPauseButton(ButtonEntity):
    """Button to pause the Plex Preview Generator queue."""

    _attr_has_entity_name = True
    _attr_name = "Pause Processing"
    _attr_icon = "mdi:pause-circle-outline"

    def __init__(
        self,
        client: PlexPreviewApiClient,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_pause"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self._client.pause()
        await self._coordinator.async_request_refresh()


class PlexPreviewResumeButton(ButtonEntity):
    """Button to resume the Plex Preview Generator queue."""

    _attr_has_entity_name = True
    _attr_name = "Resume Processing"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(
        self,
        client: PlexPreviewApiClient,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_resume"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self._client.resume()
        await self._coordinator.async_request_refresh()


class PlexPreviewLibraryButton(ButtonEntity):
    """Button to trigger previews for a specific library."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:movie-cog"

    def __init__(
        self,
        client: PlexPreviewApiClient,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
        library_id: str,
        library_name: str,
    ) -> None:
        self._client = client
        self._coordinator = coordinator
        self._library_id = library_id
        self._library_name = library_name
        self._attr_unique_id = f"{entry.entry_id}_library_{library_id}_run"
        self._attr_name = f"Generate Previews: {library_name}"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self._client.trigger_job(library_id=self._library_id, library_name=self._library_name, force=False)
        await self._coordinator.async_request_refresh()


class PlexPreviewRunScheduleButton(ButtonEntity):
    """Button to run a configured schedule immediately."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-play"

    def __init__(
        self,
        client: PlexPreviewApiClient,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
        schedule_id: str,
        schedule_name: str,
    ) -> None:
        self._client = client
        self._coordinator = coordinator
        self._schedule_id = schedule_id
        self._attr_unique_id = f"{entry.entry_id}_schedule_{schedule_id}_run"
        self._attr_name = f"Run Schedule: {schedule_name}"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self._client.run_schedule(self._schedule_id)
        await self._coordinator.async_request_refresh()


class PlexPreviewClearCompletedFailedButton(ButtonEntity):
    """Button to clear completed/failed jobs (handy when the UI gets noisy)."""

    _attr_has_entity_name = True
    _attr_name = "Clear Completed/Failed Jobs"
    _attr_icon = "mdi:broom"

    def __init__(
        self,
        client: PlexPreviewApiClient,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_clear_completed_failed"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self._client.clear_jobs(statuses=["completed", "failed"])
        await self._coordinator.async_request_refresh()
