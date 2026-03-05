"""Sensor platform for Plex Preview Monitor."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_URL, DATA_COORDINATOR, DOMAIN
from .coordinator import PlexPreviewCoordinator, PlexPreviewData

_LOGGER = logging.getLogger(__name__)

def _parse_speed_x(value: Any) -> float | None:
    """Parse speed like '12.7x' into 12.7."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if s.endswith('x'):
        s = s[:-1].strip()
    try:
        return float(s)
    except ValueError:
        return None

def _parse_eta_seconds(value: Any) -> int | None:
    """Parse ETA into seconds. Accepts '123s', '5m 22s', '01:23', '1:02:03', '2h3m4s'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(float(value))
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s:
        return None
    # 123s
    if s.endswith('s') and s[:-1].strip().replace('.','',1).isdigit():
        try:
            return int(float(s[:-1].strip()))
        except ValueError:
            return None
    # tokenized 2h3m4s / 5m22s / 5m 22s
    import re
    m = re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", s)
    if m:
        total = 0.0
        for num, unit in m:
            try:
                n = float(num)
            except ValueError:
                return None
            if unit == 'h':
                total += n * 3600
            elif unit == 'm':
                total += n * 60
            else:
                total += n
        return int(total)
    # colon formats MM:SS or HH:MM:SS
    if ':' in s:
        parts = [p.strip() for p in s.split(':')]
        if all(p.isdigit() for p in parts) and 2 <= len(parts) <= 3:
            nums = [int(p) for p in parts]
            if len(nums) == 2:
                mm, ss = nums
                return mm * 60 + ss
            hh, mm, ss = nums
            return hh * 3600 + mm * 60 + ss
    return None


@dataclass(frozen=True)
class PlexPreviewSensorDescription(SensorEntityDescription):
    """Describe a Plex Preview sensor."""

    value_fn: Callable[[PlexPreviewData], Any] | None = None
    attributes_fn: Callable[[PlexPreviewData], dict[str, Any]] | None = None


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Plex Preview Generator",
        manufacturer="stevezau",
        model="Plex Preview Generator",
        configuration_url=entry.data[CONF_URL],
    )


def _worker_ident(worker: dict, index: int) -> str:
    """Return a stable worker identifier across upstream schema variants."""
    for k in ("worker_id", "id", "workerId"):
        v = worker.get(k)
        if v is not None and v != "":
            return str(v)
    for k in ("worker_name", "name", "hostname"):
        v = worker.get(k)
        if v is not None and v != "":
            return str(v)
    return str(index)


def _worker_display_name(worker: dict, worker_id: str) -> str:
    """Pretty label for a worker."""
    name = worker.get("worker_name") or worker.get("name") or worker.get("hostname")
    return name or f"Worker {worker_id}"


STATIC_SENSORS: tuple[PlexPreviewSensorDescription, ...] = (
    PlexPreviewSensorDescription(
        key="status",
        name="Status",
        icon="mdi:filmstrip-box-multiple",
        value_fn=lambda d: d.overall_status,
        attributes_fn=lambda d: {
            "paused": d.paused,
            "pending_jobs": d.system.get("pending_jobs"),
            "gpu_count_system": len(d.system.get("gpus") or []),
            "gpu_count_workers": sum(
                1
                for w in (d.workers or [])
                if str(w.get("worker_type", "")).upper() == "GPU"
            ),
        },
    ),
    PlexPreviewSensorDescription(
        key="paused",
        name="Processing Paused",
        icon="mdi:pause-circle-outline",
        value_fn=lambda d: d.paused,
    ),
    PlexPreviewSensorDescription(
        key="pending_jobs",
        name="Pending Jobs",
        icon="mdi:tray-full",
        native_unit_of_measurement="jobs",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.system.get("pending_jobs", d.stats.get("queued", 0)),
    ),
    PlexPreviewSensorDescription(
        key="gpu_count",
        name="GPU Count",
        icon="mdi:expansion-card",
        native_unit_of_measurement="gpus",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(
            len(d.system.get("gpus") or []),
            sum(
                1
                for w in (d.workers or [])
                if str(w.get("worker_type", "")).upper() == "GPU"
            ),
        ),
    ),
    PlexPreviewSensorDescription(
        key="jobs_running",
        name="Jobs Running",
        icon="mdi:play-circle-outline",
        native_unit_of_measurement="jobs",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.stats.get("running", 0),
    ),
    PlexPreviewSensorDescription(
        key="jobs_queued",
        name="Jobs Queued",
        icon="mdi:tray-full",
        native_unit_of_measurement="jobs",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.stats.get("queued", d.stats.get("queue_depth", 0)),
    ),
    PlexPreviewSensorDescription(
        key="jobs_completed",
        name="Jobs Completed",
        icon="mdi:check-circle-outline",
        native_unit_of_measurement="jobs",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.stats.get("completed", 0),
    ),
    PlexPreviewSensorDescription(
        key="jobs_failed",
        name="Jobs Failed",
        icon="mdi:close-circle-outline",
        native_unit_of_measurement="jobs",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.stats.get("failed", 0),
    ),
    PlexPreviewSensorDescription(
        key="active_job",
        name="Active Job",
        icon="mdi:movie-open-outline",
        value_fn=lambda d: d.active_job_title,
        attributes_fn=lambda d: {
            "job_id": d.active_job.get("id") if d.active_job else None,
            "status": d.active_job.get("status") if d.active_job else None,
            "library_name": d.active_job.get("library_name") if d.active_job else None,
            "created_at": d.active_job.get("created_at") if d.active_job else None,
            "started_at": d.active_job.get("started_at") if d.active_job else None,
            "processed_items": (d.active_job.get("progress") or {}).get("processed_items")
            if d.active_job
            else None,
            "total_items": (d.active_job.get("progress") or {}).get("total_items")
            if d.active_job
            else None,
            "current_item": (d.active_job.get("progress") or {}).get("current_item")
            if d.active_job
            else None,
            "speed": (d.active_job.get("progress") or {}).get("speed")
            if d.active_job
            else None,
            "paused": d.active_job.get("paused") if d.active_job else None,
            "error": d.active_job.get("error") if d.active_job else None,
        },
    ),
    PlexPreviewSensorDescription(
        key="active_job_progress",
        name="Active Job Progress",
        icon="mdi:progress-clock",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.active_job_progress,
    ),
    PlexPreviewSensorDescription(
        key="active_job_processed_items",
        name="Active Job Processed Items",
        icon="mdi:counter",
        native_unit_of_measurement="items",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.active_job.get("progress") or {}).get("processed_items") if d.active_job else None,
    ),
    PlexPreviewSensorDescription(
        key="active_job_total_items",
        name="Active Job Total Items",
        icon="mdi:counter",
        native_unit_of_measurement="items",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.active_job.get("progress") or {}).get("total_items") if d.active_job else None,
    ),
    PlexPreviewSensorDescription(
        key="worker_count",
        name="Worker Count",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement="workers",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.workers or []),
    ),
)


def _worker_sensors(
    coordinator: PlexPreviewCoordinator,
    entry: ConfigEntry,
    worker_id: str,
) -> list[SensorEntity]:
    # These metrics map to /api/jobs/workers:
    # - status
    # - progress_percent
    # - speed
    # - eta
    # - current_title
    return [
        PlexPreviewWorkerSensor(coordinator, entry, worker_id, "status", "mdi:server", None),
        PlexPreviewWorkerSensor(coordinator, entry, worker_id, "progress", "mdi:progress-clock", "%"),
        PlexPreviewWorkerSensor(coordinator, entry, worker_id, "speed", "mdi:speedometer", None),
        PlexPreviewWorkerSensor(coordinator, entry, worker_id, "eta", "mdi:timer-outline", None),
        PlexPreviewWorkerSensor(coordinator, entry, worker_id, "title", "mdi:movie-open-outline", None),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: PlexPreviewCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = [PlexPreviewStaticSensor(coordinator, entry, desc) for desc in STATIC_SENSORS]

    # Create worker sensors for workers we already know about
    if coordinator.data:
        for i, worker in enumerate(coordinator.data.workers or []):
            wid = _worker_ident(worker, i)
            entities.extend(_worker_sensors(coordinator, entry, wid))

    async_add_entities(entities)

    # Dynamically add sensors for newly discovered workers
    known_worker_ids: set[str] = set()
    if coordinator.data:
        known_worker_ids = {_worker_ident(w, i) for i, w in enumerate(coordinator.data.workers or [])}

    def _handle_coordinator_update() -> None:
        if not coordinator.data:
            return
        new_entities: list[SensorEntity] = []
        for i, worker in enumerate(coordinator.data.workers or []):
            wid = _worker_ident(worker, i)
            if wid not in known_worker_ids:
                known_worker_ids.add(wid)
                new_entities.extend(_worker_sensors(coordinator, entry, wid))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


class PlexPreviewStaticSensor(CoordinatorEntity[PlexPreviewCoordinator], SensorEntity):
    """A sensor backed by a static description + value_fn."""

    entity_description: PlexPreviewSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
        description: PlexPreviewSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not data or self.entity_description.value_fn is None:
            return None
        try:
            return self.entity_description.value_fn(data)
        except Exception:
            _LOGGER.exception("Error computing native_value for %s", self.entity_description.key)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data or self.entity_description.attributes_fn is None:
            return {}
        try:
            return self.entity_description.attributes_fn(data) or {}
        except Exception:
            _LOGGER.exception("Error computing attributes for %s", self.entity_description.key)
            return {}


class PlexPreviewWorkerSensor(CoordinatorEntity[PlexPreviewCoordinator], SensorEntity):
    """Sensor for a single worker metric based on /api/jobs/workers."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PlexPreviewCoordinator,
        entry: ConfigEntry,
        worker_id: str,
        metric: str,
        icon: str,
        unit: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._worker_id = str(worker_id)
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_worker_{self._worker_id}_{metric}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        if unit == "%":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if metric in ("speed", "eta"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if metric == "eta":
            self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_device_info = _device_info(entry)

    def _find_worker(self) -> dict | None:
        if not self.coordinator.data:
            return None
        for i, w in enumerate(self.coordinator.data.workers or []):
            if _worker_ident(w, i) == self._worker_id:
                return w
        return None

    @property
    def name(self) -> str | None:
        worker = self._find_worker()
        base = _worker_display_name(worker, self._worker_id) if worker else f"Worker {self._worker_id}"
        labels = {
            "status": "Status",
            "progress": "Progress",
            "speed": "Speed",
            "eta": "ETA",
            "title": "Current Title",
        }
        return f"{base} {labels.get(self._metric, self._metric)}"

    @property
    def native_value(self) -> Any:
        worker = self._find_worker()
        if worker is None:
            return None

        metric = self._metric

        if metric == "status":
            return worker.get("status") or None

        if metric == "progress":
            pct = worker.get("progress_percent")
            if isinstance(pct, (int, float)):
                return round(float(pct), 1)
            return None

        if metric == "speed":
            return _parse_speed_x(worker.get("speed"))

        if metric == "eta":
            return _parse_eta_seconds(worker.get("eta"))

        if metric == "title":
            return worker.get("current_title") or None

        return None
