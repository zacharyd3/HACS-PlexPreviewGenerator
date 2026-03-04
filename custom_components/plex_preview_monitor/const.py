"""Constants for the Plex Preview Monitor integration."""

DOMAIN = "plex_preview_monitor"
PLATFORMS = ["sensor", "button", "switch"]

# Config entry keys
CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEFAULT_LIBRARY_ID = "default_library_id"
CONF_DEFAULT_LIBRARY_NAME = "default_library_name"

# Defaults
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_NAME = "Plex Preview"

# API paths (Plex Preview Generator)
API_STATS = "/api/jobs/stats"
API_SYSTEM_STATUS = "/api/system/status"
API_JOBS = "/api/jobs"
API_WORKERS = "/api/jobs/workers"

API_PROCESSING_STATE = "/api/processing/state"
API_PAUSE = "/api/processing/pause"
API_RESUME = "/api/processing/resume"

API_LIBRARIES = "/api/libraries"
API_SCHEDULES = "/api/schedules"

# Coordinator key
DATA_COORDINATOR = "coordinator"

