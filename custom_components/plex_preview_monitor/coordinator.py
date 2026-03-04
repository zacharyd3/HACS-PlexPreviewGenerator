"""DataUpdateCoordinator for Plex Preview Monitor."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PlexPreviewApiClient, PlexPreviewCannotConnectError, PlexPreviewApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class PlexPreviewData:
    """Holds the latest polled data from Plex Preview Generator."""

    stats: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    processing: dict = field(default_factory=dict)
    active_job: dict | None = None
    workers: list[dict] = field(default_factory=list)
    libraries: list[dict] = field(default_factory=list)
    schedules: list[dict] = field(default_factory=list)

    @property
    def paused(self) -> bool:
        return bool(self.processing.get("paused", False))

    @property
    def overall_status(self) -> str:
        if self.paused:
            return "paused"
        if self.active_job:
            return "processing"
        if self.stats.get("queued", 0) > 0 or self.system.get("pending_jobs", 0) > 0:
            return "queued"
        return "idle"

    @property
    def active_job_title(self) -> str:
        if not self.active_job:
            return "none"
        return (
            self.active_job.get("title")
            or self.active_job.get("media_title")
            or self.active_job.get("id", "Unknown")
        )

    @property
    def active_job_progress(self) -> int:
        if not self.active_job:
            return 0

        # The upstream API has evolved; "progress" may be numeric, a string,
        # or a dict (e.g. {"current": x, "total": y} or {"percent": z}).
        def _to_int_percent(value) -> int | None:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(round(float(value)))
            if isinstance(value, str):
                try:
                    return int(round(float(value.strip())))
                except ValueError:
                    return None
            if isinstance(value, dict):
                for k in ("percent_complete", "percent", "progress", "value", "utilization"):
                    if k in value:
                        return _to_int_percent(value.get(k))
                cur = value.get("current")
                total = value.get("total")
                if isinstance(cur, (int, float)) and isinstance(total, (int, float)) and total:
                    return int(round((float(cur) / float(total)) * 100.0))
            return None

        for candidate in (
            self.active_job.get("percent_complete"),
            self.active_job.get("progress"),
            self.active_job.get("percent"),
        ):
            parsed = _to_int_percent(candidate)
            if parsed is not None:
                return max(0, min(100, parsed))

        return 0


class PlexPreviewCoordinator(DataUpdateCoordinator[PlexPreviewData]):
    """Coordinator that polls the Plex Preview Generator API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PlexPreviewApiClient,
        scan_interval: int,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.entry = entry
        self._prev_completed: int | None = None
        self._prev_failed: int | None = None

    async def _async_update_data(self) -> PlexPreviewData:
        try:
            stats = await self.client.get_stats()
        except PlexPreviewCannotConnectError as err:
            raise UpdateFailed(f"Cannot reach Plex Preview Generator: {err}") from err
        except PlexPreviewApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        system = await self.client.get_system_status()
        processing = await self.client.get_processing_state()
        active_job = await self.client.get_active_job()
        workers = await self.client.get_workers()

        # These are lightweight and make HA UX much nicer; treat failures as empty.
        libraries = await self.client.get_libraries()
        schedules = await self.client.get_schedules()

        data = PlexPreviewData(
            stats=stats,
            system=system,
            processing=processing,
            active_job=active_job,
            workers=workers,
            libraries=libraries,
            schedules=schedules,
        )

        self._check_notifications(data)
        return data

    def _check_notifications(self, data: PlexPreviewData) -> None:
        """Fire HA events on job completion or failure transitions."""
        completed = data.stats.get("completed", 0)
        failed = data.stats.get("failed", 0)

        # Seed on first successful poll
        if self._prev_completed is None:
            self._prev_completed = completed
            self._prev_failed = failed
            return

        if completed > (self._prev_completed or 0):
            delta = completed - (self._prev_completed or 0)
            self.hass.bus.async_fire(
                f"{DOMAIN}_jobs_completed",
                {"count": delta, "total_completed": completed},
            )
            _LOGGER.info("%d preview job(s) completed", delta)

        if failed > (self._prev_failed or 0):
            delta = failed - (self._prev_failed or 0)
            self.hass.bus.async_fire(
                f"{DOMAIN}_jobs_failed",
                {"count": delta, "total_failed": failed},
            )
            _LOGGER.warning("%d preview job(s) failed", delta)

        self._prev_completed = completed
        self._prev_failed = failed
