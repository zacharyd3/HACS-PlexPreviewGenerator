"""Plex Preview Monitor integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Iterable

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PlexPreviewApiClient, PlexPreviewCannotConnectError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_URL,
    DATA_COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import PlexPreviewCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH]

SERVICE_TRIGGER_JOB = "trigger_job"
SERVICE_RUN_SCHEDULE = "run_schedule"
SERVICE_CLEAR_JOBS = "clear_jobs"
SERVICE_REPROCESS_JOB = "reprocess_job"
SERVICE_DELETE_JOB = "delete_job"
SERVICE_PAUSE = "pause_processing"
SERVICE_RESUME = "resume_processing"

TRIGGER_JOB_SCHEMA = vol.Schema(
    {
        vol.Optional("library_id"): cv.string,
        vol.Optional("library"): cv.string,  # legacy name
        vol.Optional("library_name"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    }
)

RUN_SCHEDULE_SCHEMA = vol.Schema({vol.Required("schedule_id"): cv.string})

CLEAR_JOBS_SCHEMA = vol.Schema(
    {vol.Optional("statuses"): vol.All(cv.ensure_list, [cv.string])}
)

REPROCESS_JOB_SCHEMA = vol.Schema({vol.Required("job_id"): cv.string})
DELETE_JOB_SCHEMA = vol.Schema({vol.Required("job_id"): cv.string})
EMPTY_SCHEMA = vol.Schema({})


def _first_entry_client(hass: HomeAssistant) -> tuple[PlexPreviewApiClient, PlexPreviewCoordinator] | None:
    """Return (client, coordinator) for the first configured entry."""
    entries = hass.data.get(DOMAIN, {})
    for entry_data in entries.values():
        return entry_data["client"], entry_data[DATA_COORDINATOR]
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plex Preview Monitor from a config entry."""
    session = async_get_clientsession(hass)
    client = PlexPreviewApiClient(
        url=entry.data[CONF_URL],
        token=entry.data.get(CONF_TOKEN, ""),
        session=session,
    )

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    coordinator = PlexPreviewCoordinator(
        hass=hass,
        client=client,
        scan_interval=scan_interval,
        entry=entry,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except PlexPreviewCannotConnectError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to Plex Preview Generator at {entry.data[CONF_URL]}: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_TRIGGER_JOB):
        return

    async def handle_trigger_job(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        library_id = call.data.get("library_id")
        library_name = call.data.get("library_name") or call.data.get("library")
        await client.trigger_job(library_id=library_id, library_name=library_name, force=call.data.get("force", False))
        await coord.async_request_refresh()

    async def handle_run_schedule(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        await client.run_schedule(call.data["schedule_id"])
        await coord.async_request_refresh()

    async def handle_clear_jobs(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        statuses = call.data.get("statuses")
        await client.clear_jobs(statuses=statuses)
        await coord.async_request_refresh()

    async def handle_reprocess_job(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        await client.reprocess_job(call.data["job_id"])
        await coord.async_request_refresh()

    async def handle_delete_job(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        await client.delete_job(call.data["job_id"])
        await coord.async_request_refresh()

    async def handle_pause(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        await client.pause()
        await coord.async_request_refresh()

    async def handle_resume(call: ServiceCall) -> None:
        res = _first_entry_client(hass)
        if not res:
            return
        client, coord = res
        await client.resume()
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_TRIGGER_JOB, handle_trigger_job, schema=TRIGGER_JOB_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RUN_SCHEDULE, handle_run_schedule, schema=RUN_SCHEDULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_JOBS, handle_clear_jobs, schema=CLEAR_JOBS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REPROCESS_JOB, handle_reprocess_job, schema=REPROCESS_JOB_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_JOB, handle_delete_job, schema=DELETE_JOB_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PAUSE, handle_pause, schema=EMPTY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESUME, handle_resume, schema=EMPTY_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload to apply new scan interval."""
    await hass.config_entries.async_reload(entry.entry_id)
