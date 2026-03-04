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

    # Raw endpoint payloads / derived structures
    jobs: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    processing: dict = field(default_factory=dict)

    # Derived from jobs (preferred) or fallback endpoint
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
        if self.stats.get("queued", 0) > 0:
            return "queued"
        return "idle"

    @property
    def active_job_title(self) -> str:
        if not self.active_job:
            return "none"
        return (
            self.active_job.get("library_name")
            or self.active_job.get("title")
            or self.active_job.get("media_title")
            or self.active_job.get("id", "Unknown")
        )

    @property
    def active_job_progress(self) -> int:
        """Percent 0..100 based on /api/jobs progress.percent."""
        job = self.active_job
        if not job:
            return 0
        prog = job.get("progress") or {}
        pct = prog.get("percent")
        if isinstance(pct, (int, float)):
            return max(0, min(100, int(round(float(pct)))))
        return 0

    @property
    def active_job_worker_count(self) -> int:
        job = self.active_job
        if not job:
            return 0
        prog = job.get("progress") or {}
        workers = prog.get("workers")
        if isinstance(workers, list):
            return len(workers)
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
            # /api/jobs is now primary
            jobs = await self.client.get_jobs()
        except PlexPreviewCannotConnectError as err:
            raise UpdateFailed(f"Cannot reach Plex Preview Generator: {err}") from err
        except PlexPreviewApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        # “nice to have” endpoints (don’t fail the whole update if they error)
        system = await self.client.get_system_status()
        processing = await self.client.get_processing_state()
        libraries = await self.client.get_libraries()
        schedules = await self.client.get_schedules()

        # derive active job from jobs list
        active_job = next(
            (j for j in jobs if str(j.get("status", "")).lower() == "running"),
            None,
        )

        # derive counts from jobs list
        def _is_completed(j: dict) -> bool:
            s = str(j.get("status", "")).lower()
            return s == "completed" or j.get("completed_at") is not None

        def _is_failed(j: dict) -> bool:
            s = str(j.get("status", "")).lower()
            return s == "failed" or j.get("error") is not None

        running = sum(1 for j in jobs if str(j.get("status", "")).lower() == "running")
        queued = sum(
            1
            for j in jobs
            if str(j.get("status", "")).lower() in ("pending", "queued")
        )
        completed = sum(1 for j in jobs if _is_completed(j))
        failed = sum(1 for j in jobs if _is_failed(j))

        stats = {
            "running": running,
            "queued": queued,
            "completed": completed,
            "failed": failed,
            "total": len(jobs),
        }

        # Prefer workers embedded in active job progress, else fallback to /api/jobs/workers
        workers_from_job: list[dict] = []
        if active_job:
            prog = active_job.get("progress") or {}
            w = prog.get("workers")
            if isinstance(w, list):
                workers_from_job = [x for x in w if isinstance(x, dict)]

        workers = workers_from_job
        if not workers:
            workers = await self.client.get_workers()

        data = PlexPreviewData(
            jobs=jobs,
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