import os

APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))

PROFILE_DIRS = [
    os.path.join(APPDATA, "OrcaSlicer", "system", "Custom", "filament"),
    os.path.join(APPDATA, "OrcaSlicer", "system", "Custom", "machine"),
    os.path.join(APPDATA, "OrcaSlicer", "system", "Custom", "process"),
    os.path.join(APPDATA, "OrcaSlicer", "user", "default", "filament"),
    os.path.join(APPDATA, "OrcaSlicer", "user", "default", "machine"),
    os.path.join(APPDATA, "OrcaSlicer", "user", "default", "process"),
]

DRIVE_FOLDER_NAME = "OrcaSlicerSync"

WATCH_EXTENSIONS = {".json", ".info"}

# Seconds between Drive change polls
POLL_INTERVAL = 5

# Debounce delay for local file changes (seconds)
DEBOUNCE_DELAY = 1.0

# Path to OAuth credentials file (place credentials.json from Google Cloud Console here)
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

# Token cache file
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")

# Log file
LOG_FILE = os.path.join(os.path.dirname(__file__), "orca_sync.log")
