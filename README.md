# Plex Preview Monitor — Home Assistant Integration

[![hacs\_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant integration that connects to
[Plex Preview Generator](https://github.com/stevezau/plex_generate_vid_previews) and exposes its status, jobs, and worker activity as Home Assistant entities.

The integration enables monitoring and automation of preview generation directly from Home Assistant dashboards and automations.

---

# Features

* Real-time sensors for queue status and job progress
* Per-worker sensors (progress, speed, ETA, title, status)
* Active job monitoring with detailed attributes
* Pause and resume processing buttons
* Trigger preview generation jobs from automations
* Job completion and failure events for notifications
* Dynamic worker discovery (entities auto-created)

---

# Installation via HACS

1. Open **HACS → Integrations**
2. Click **⋮ → Custom repositories**
3. Add this repository URL
   Category: **Integration**
4. Search for **Plex Preview Monitor**
5. Click **Download**
6. Restart Home Assistant
7. Go to **Settings → Devices & Services**
8. Click **Add Integration**
9. Search for **Plex Preview Monitor**

---

# Configuration

All configuration is done through the UI.

| Field         | Default      | Description                                                                    |
| ------------- | ------------ | ------------------------------------------------------------------------------ |
| URL           | —            | Base URL of your Plex Preview Generator (example: `http://192.168.1.100:8082`) |
| API Token     | *(optional)* | Leave blank if authentication is disabled                                      |
| Poll Interval | `30s`        | Update interval (10–300 seconds)                                               |

Options can be modified later through:

**Settings → Devices & Services → Plex Preview Monitor → Configure**

---

# Entities Created

## Status Sensors

| Entity                                            | Description                                    |
| ------------------------------------------------- | ---------------------------------------------- |
| `sensor.plex_preview_generator_status`            | Overall state (`idle`, `queued`, `processing`) |
| `sensor.plex_preview_generator_processing_paused` | Whether processing is paused                   |
| `sensor.plex_preview_generator_pending_jobs`      | Jobs waiting in queue                          |
| `sensor.plex_preview_generator_jobs_running`      | Currently running jobs                         |
| `sensor.plex_preview_generator_jobs_queued`       | Jobs queued                                    |
| `sensor.plex_preview_generator_jobs_completed`    | Completed job count                            |
| `sensor.plex_preview_generator_jobs_failed`       | Failed job count                               |
| `sensor.plex_preview_generator_gpu_count`         | Number of GPU workers                          |
| `sensor.plex_preview_generator_worker_count`      | Total worker count                             |

---

## Active Job Sensors

| Entity                                              | Description                          |
| --------------------------------------------------- | ------------------------------------ |
| `sensor.plex_preview_generator_active_job`          | Title of the active job              |
| `sensor.plex_preview_generator_active_job_progress` | Percent completion of the active job |

Active job sensor attributes include:

* `job_id`
* `status`
* `library_name`
* `created_at`
* `started_at`
* `processed_items`
* `total_items`
* `current_item`
* `speed`
* `paused`
* `error`

---

## Worker Sensors

Worker sensors are created dynamically based on detected workers.

Example entities:

| Entity                                                 | Description                     |
| ------------------------------------------------------ | ------------------------------- |
| `sensor.plex_preview_generator_worker_0_status`        | Worker processing state         |
| `sensor.plex_preview_generator_worker_0_progress`      | Percent progress                |
| `sensor.plex_preview_generator_worker_0_speed`         | Processing speed                |
| `sensor.plex_preview_generator_worker_0_eta`           | Estimated completion time       |
| `sensor.plex_preview_generator_worker_0_current_title` | Title currently being processed |

Workers are automatically discovered from the API and new sensors appear automatically if additional workers are detected.

---

# Buttons

| Entity                                            | Description      |
| ------------------------------------------------- | ---------------- |
| `button.plex_preview_generator_pause_processing`  | Pause job queue  |
| `button.plex_preview_generator_resume_processing` | Resume job queue |

---

# Service: `plex_preview_monitor.trigger_job`

Start a preview generation job from an automation.

```yaml
service: plex_preview_monitor.trigger_job
data:
  library: "TV Shows"
  force: false
```

## Parameters

| Field     | Required | Description                                    |
| --------- | -------- | ---------------------------------------------- |
| `library` | ✅        | Plex library name                              |
| `force`   | ❌        | Regenerate previews even if they already exist |

---

# Events

The integration emits Home Assistant events when jobs complete or fail.

| Event                                 | Data                       | Description            |
| ------------------------------------- | -------------------------- | ---------------------- |
| `plex_preview_monitor_jobs_completed` | `count`, `total_completed` | Fired when jobs finish |
| `plex_preview_monitor_jobs_failed`    | `count`, `total_failed`    | Fired when jobs fail   |

These events can be used to trigger notifications or automations.

---

# Example Automations

## Notify when preview generation fails

```yaml
automation:
  - alias: Plex Preview — Notify Failure
    trigger:
      - platform: event
        event_type: plex_preview_monitor_jobs_failed
    action:
      - service: notify.mobile_app_phone
        data:
          title: Plex Preview Failed
          message: >
            {{ trigger.event.data.count }} preview job(s) failed.
```

---

## Trigger preview generation after Sonarr download

```yaml
automation:
  - alias: Plex Preview — Scan After Sonarr
    trigger:
      - platform: webhook
        webhook_id: sonarr_download
    action:
      - service: plex_preview_monitor.trigger_job
        data:
          library: "TV Shows"
```

---

## Pause preview generation during peak hours

```yaml
automation:
  - alias: Pause Preview Generation
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.plex_preview_generator_pause_processing
```

---

# Example Dashboard Card

```yaml
type: markdown
content: |
  ## Plex Preview Generator

  **Status:** {{ states('sensor.plex_preview_generator_status') }}

  **Active Job:** {{ states('sensor.plex_preview_generator_active_job') }}

  **Progress:** {{ states('sensor.plex_preview_generator_active_job_progress') }}%

  **Queued:** {{ states('sensor.plex_preview_generator_jobs_queued') }}

  **Workers:** {{ states('sensor.plex_preview_generator_worker_count') }}
```

---

# Troubleshooting

### Entities show `unavailable`

* Verify the URL is reachable from Home Assistant
* Confirm the API endpoint works in a browser
* Check logs under **Settings → System → Logs**

Search for:

```
plex_preview_monitor
```

---

### Worker sensors do not appear

Worker sensors appear only if the API exposes:

```
/api/jobs/workers
```

Make sure your Plex Preview Generator version supports this endpoint.

---

### Job trigger service does nothing

* Confirm the library name matches Plex exactly
* Check Plex Preview Generator logs for API errors

---

# License

MIT License
