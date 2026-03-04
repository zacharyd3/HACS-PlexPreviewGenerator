# Plex Preview Monitor — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A HACS custom integration that connects [Plex Preview Generator](https://github.com/stevezau/plex_generate_vid_previews) to Home Assistant. Get real-time sensors, pause/resume buttons, job completion notifications, and a service to trigger scans from automations.

---

## Installation via HACS

1. Open HACS in your Home Assistant instance.
2. Click **⋮ → Custom repositories**.
3. Add this repository URL and select category **Integration**.
4. Search for **Plex Preview Monitor** and click **Download**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & Services → Add Integration** and search for **Plex Preview Monitor**.
7. Enter your Plex Preview Generator URL and optional API token.

---

## Configuration

The integration is fully configured through the UI — no `yaml` required.

| Field | Default | Description |
|---|---|---|
| URL | — | Full URL to your Plex Preview Generator (e.g. `http://192.168.1.100:8080`) |
| API Token | *(blank)* | Leave empty if auth is disabled |
| Poll interval | `30` | Seconds between status updates (10–300) |

Options (token and poll interval) can be changed any time via **Settings → Devices & Services → Plex Preview Monitor → Configure**.

---

## Entities Created

### Sensors

| Entity | Description |
|---|---|
| `sensor.plex_preview_generator_status` | `idle` / `queued` / `processing` |
| `sensor.plex_preview_generator_jobs_running` | Jobs currently running |
| `sensor.plex_preview_generator_jobs_queued` | Jobs waiting in queue |
| `sensor.plex_preview_generator_jobs_completed` | Lifetime completed count |
| `sensor.plex_preview_generator_jobs_failed` | Lifetime failed count |
| `sensor.plex_preview_generator_active_job` | Title of the currently processing item |
| `sensor.plex_preview_generator_active_job_progress` | Progress % of active job |
| `sensor.plex_preview_generator_worker_count` | Number of workers |
| `sensor.plex_preview_generator_worker_N_status` | Status of worker N |
| `sensor.plex_preview_generator_worker_N_gpu` | GPU utilisation % for worker N |
| `sensor.plex_preview_generator_worker_N_cpu` | CPU utilisation % for worker N |

All sensors become `unavailable` automatically when Plex Preview Generator cannot be reached.

### Buttons

| Entity | Description |
|---|---|
| `button.plex_preview_generator_pause_processing` | Pause the job queue |
| `button.plex_preview_generator_resume_processing` | Resume the job queue |

---

## Service: `plex_preview_monitor.trigger_job`

Trigger a preview generation scan from any automation or script.

```yaml
service: plex_preview_monitor.trigger_job
data:
  library: "TV Shows"
  force: false   # set true to regenerate existing previews
```

### Fields

| Field | Required | Description |
|---|---|---|
| `library` | ✅ | Plex library name to scan |
| `force` | ❌ | Re-generate even if previews already exist (default: `false`) |

---

## Events

The integration fires HA events on state transitions — use these in automations for custom notifications.

| Event | Data | Description |
|---|---|---|
| `plex_preview_monitor_jobs_completed` | `count`, `total_completed` | Fired when jobs complete |
| `plex_preview_monitor_jobs_failed` | `count`, `total_failed` | Fired when jobs fail |

---

## Example Automations

### Notify on mobile when a job fails

```yaml
automation:
  - alias: "Plex Preview — Notify on failure"
    trigger:
      - platform: event
        event_type: plex_preview_monitor_jobs_failed
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Plex Preview Failed"
          message: >
            {{ trigger.event.data.count }} preview job(s) failed.
            Total failed: {{ trigger.event.data.total_failed }}.
```

### Trigger a scan after Sonarr downloads an episode

```yaml
automation:
  - alias: "Plex Preview — Scan after Sonarr download"
    trigger:
      - platform: webhook
        webhook_id: sonarr_on_download
    action:
      - service: plex_preview_monitor.trigger_job
        data:
          library: "TV Shows"
```

### Pause during peak hours

```yaml
automation:
  - alias: "Plex Preview — Pause at 6pm"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.plex_preview_generator_pause_processing

  - alias: "Plex Preview — Resume at 11pm"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.plex_preview_generator_resume_processing
```

### Dashboard card

```yaml
type: markdown
content: |
  ## Plex Preview Generator
  **Status:** {{ states('sensor.plex_preview_generator_status') | title }}
  **Active:** {{ states('sensor.plex_preview_generator_active_job') }}
  **Progress:** {{ states('sensor.plex_preview_generator_active_job_progress') }}%
  **Queued:** {{ states('sensor.plex_preview_generator_jobs_queued') }}
  **Completed:** {{ states('sensor.plex_preview_generator_jobs_completed') }}
  **Failed:** {{ states('sensor.plex_preview_generator_jobs_failed') }}
```

---

## Troubleshooting

**Entities show `unavailable`**
- Confirm the URL is reachable from your HA host (try opening it in a browser)
- Check HA logs under **Settings → System → Logs** and filter by `plex_preview_monitor`

**Service `trigger_job` has no effect**
- Verify the library name matches exactly what appears in Plex
- Check Plex Preview Generator logs for the incoming request

**Worker GPU/CPU sensors not appearing**
- These only show up if your Plex Preview Generator version exposes `/api/workers` with utilisation data
