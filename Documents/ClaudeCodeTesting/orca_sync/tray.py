import logging
import os
import subprocess
import sys
import threading
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None  # type: ignore

from config import LOG_FILE

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "waiting": (156, 163, 175),  # gray  — OrcaSlicer not running
    "synced":  (34, 197, 94),    # green
    "syncing": (234, 179, 8),    # yellow
    "error":   (239, 68, 68),    # red
}


def _make_icon_image(color: tuple[int, int, int]) -> "Image.Image":
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color + (255,))
    return img


class TrayApp:
    def __init__(
        self,
        on_sync_now: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self._on_sync_now = on_sync_now
        self._on_quit = on_quit
        self._icon: Optional["pystray.Icon"] = None
        self._status = "synced"

    def set_status(self, status: str) -> None:
        """Update tray icon color. status: 'synced' | 'syncing' | 'error'"""
        self._status = status
        if self._icon:
            color = _STATUS_COLORS.get(status, _STATUS_COLORS["error"])
            self._icon.icon = _make_icon_image(color)
            self._icon.title = f"OrcaSync — {status}"

    def run(self) -> None:
        if pystray is None:
            logger.warning("pystray not available — running without tray icon.")
            return

        color = _STATUS_COLORS["synced"]
        image = _make_icon_image(color)

        menu = pystray.Menu(
            pystray.MenuItem("OrcaSlicer Profile Sync", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sync Now", self._handle_sync_now),
            pystray.MenuItem("Open Log", self._handle_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._handle_quit),
        )

        self._icon = pystray.Icon(
            name="orca_sync",
            icon=image,
            title="OrcaSync — synced",
            menu=menu,
        )
        logger.info("Starting system tray icon.")
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def _handle_sync_now(self, icon, item) -> None:
        threading.Thread(target=self._on_sync_now, daemon=True).start()

    def _handle_open_log(self, icon, item) -> None:
        if os.path.isfile(LOG_FILE):
            if sys.platform == "win32":
                os.startfile(LOG_FILE)
            else:
                subprocess.Popen(["xdg-open", LOG_FILE])
        else:
            logger.info("Log file not found: %s", LOG_FILE)

    def _handle_quit(self, icon, item) -> None:
        self.stop()
        self._on_quit()
