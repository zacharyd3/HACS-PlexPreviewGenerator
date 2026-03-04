"""API client for Plex Preview Generator."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

import aiohttp

from .const import (
    API_JOBS,
    API_LIBRARIES,
    API_PAUSE,
    API_PROCESSING_STATE,
    API_RESUME,
    API_SCHEDULES,
    API_STATS,
    API_SYSTEM_STATUS,
    API_WORKERS,
)

_LOGGER = logging.getLogger(__name__)


class PlexPreviewApiError(Exception):
    """Raised when the API returns an error."""


class PlexPreviewCannotConnectError(PlexPreviewApiError):
    """Raised when we cannot connect to the API."""


class PlexPreviewAuthError(PlexPreviewApiError):
    """Raised when authentication fails."""


class PlexPreviewApiClient:
    """Client for the Plex Preview Generator REST API."""

    def __init__(
        self,
        url: str,
        token: str | None,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base_url = url.rstrip("/")
        self._token = token or None
        self._session = session

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            # Upstream supports both Authorization: Bearer and X-Auth-Token. Bearer is fine.
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                json=data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (401, 403):
                    raise PlexPreviewAuthError("Invalid/unauthorized API token")
                resp.raise_for_status()
                # Some endpoints may return empty body
                if resp.content_length == 0:
                    return {}
                return await resp.json()
        except PlexPreviewApiError:
            raise
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as err:
            raise PlexPreviewCannotConnectError(
                f"Cannot connect to {self._base_url}: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise PlexPreviewApiError(f"API error: {err}") from err

    @staticmethod
    def _as_list(result: Any, key: str) -> list[dict]:
        if isinstance(result, list):
            return [x for x in result if isinstance(x, dict)]
        if isinstance(result, dict):
            items = result.get(key, [])
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
        return []

    async def get_stats(self) -> dict:
        return await self._request("GET", API_STATS)

    async def get_system_status(self) -> dict:
        try:
            return await self._request("GET", API_SYSTEM_STATUS)
        except PlexPreviewApiError:
            return {}

    async def get_processing_state(self) -> dict:
        try:
            return await self._request("GET", API_PROCESSING_STATE)
        except PlexPreviewApiError:
            return {}
            
    async def get_jobs(self) -> list[dict]:
        """Return the current jobs list from /api/jobs."""
        try:
            result = await self._request("GET", API_JOBS)
            return self._as_list(result, "jobs")
        except PlexPreviewApiError:
            return []

    async def get_active_job(self) -> dict | None:
        """Prefer system status 'running_job'; fallback to scanning jobs list."""
        try:
            system = await self.get_system_status()
            running = system.get("running_job")
            if isinstance(running, dict) and running:
                return running
        except Exception:  # noqa: BLE001
            pass

        try:
            result = await self._request("GET", API_JOBS)
            jobs = self._as_list(result, "jobs")
            for j in jobs:
                if str(j.get("status", "")).lower() == "running":
                    return j
        except PlexPreviewApiError:
            return None
        return None

    async def get_workers(self) -> list[dict]:
        try:
            result = await self._request("GET", API_WORKERS)
            return self._as_list(result, "workers")
        except PlexPreviewApiError:
            return []

    async def get_libraries(self) -> list[dict]:
        """Return available Plex libraries with id/name/type/count."""
        try:
            result = await self._request("GET", API_LIBRARIES)
            return self._as_list(result, "libraries")
        except PlexPreviewApiError:
            return []

    async def get_schedules(self) -> list[dict]:
        try:
            result = await self._request("GET", API_SCHEDULES)
            return self._as_list(result, "schedules")
        except PlexPreviewApiError:
            return []

    async def run_schedule(self, schedule_id: str) -> dict:
        return await self._request("POST", f"{API_SCHEDULES}/{schedule_id}/run")

    async def enable_schedule(self, schedule_id: str) -> dict:
        return await self._request("POST", f"{API_SCHEDULES}/{schedule_id}/enable")

    async def disable_schedule(self, schedule_id: str) -> dict:
        return await self._request("POST", f"{API_SCHEDULES}/{schedule_id}/disable")

    async def trigger_job(
        self,
        library_id: str | None = None,
        library_name: str | None = None,
        force: bool = False,
    ) -> dict:
        """Queue a preview generation job.

        Upstream accepts library identifiers; we support either id or name.
        """
        payload: dict[str, Any] = {"force": force}
        if library_id:
            payload["library_id"] = library_id
        if library_name:
            payload["library"] = library_name  # legacy / convenience
            payload["library_name"] = library_name
        return await self._request("POST", API_JOBS, payload)

    async def delete_job(self, job_id: str) -> dict:
        return await self._request("DELETE", f"{API_JOBS}/{job_id}")

    async def reprocess_job(self, job_id: str) -> dict:
        return await self._request("POST", f"{API_JOBS}/{job_id}/reprocess")

    async def clear_jobs(self, statuses: Iterable[str] | None = None) -> dict:
        payload: dict[str, Any] = {}
        if statuses:
            payload["statuses"] = list(statuses)
        return await self._request("POST", f"{API_JOBS}/clear", payload or None)

    async def pause(self) -> None:
        await self._request("POST", API_PAUSE)

    async def resume(self) -> None:
        await self._request("POST", API_RESUME)

    async def async_validate_connection(self) -> bool:
        """Test connectivity and auth. Raises on failure."""
        await self.get_stats()
        return True
