import os
import platform

# OrcaSlicer process names per platform
_SYSTEM = platform.system()
ORCA_PROCESS_NAMES: list[str] = {
    "Windows": ["orca-slicer.exe", "OrcaSlicer.exe"],
    "Darwin":  ["OrcaSlicer"],
    "Linux":   ["orca-slicer", "OrcaSlicer"],
}.get(_SYSTEM, ["orca-slicer", "OrcaSlicer"])

# How often to check whether OrcaSlicer is running (seconds)
PROCESS_POLL_INTERVAL = 3


def _orca_base() -> str:
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "OrcaSlicer")
    elif system == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "OrcaSlicer")
    else:  # Linux and others
        return os.path.join(os.path.expanduser("~"), ".config", "OrcaSlicer")


_BASE = _orca_base()

PROFILE_DIRS = [
    os.path.join(_BASE, "system", "Custom", "filament"),
    os.path.join(_BASE, "system", "Custom", "machine"),
    os.path.join(_BASE, "system", "Custom", "process"),
    os.path.join(_BASE, "user", "default", "filament"),
    os.path.join(_BASE, "user", "default", "machine"),
    os.path.join(_BASE, "user", "default", "process"),
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
