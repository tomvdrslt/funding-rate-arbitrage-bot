import logging
import threading
import time
from typing import Callable

import psutil

from config import ORCA_PROCESS_NAMES, PROCESS_POLL_INTERVAL

logger = logging.getLogger(__name__)


class ProcessMonitor:
    """Watches for OrcaSlicer to open/close and fires callbacks."""

    def __init__(self, on_open: Callable[[], None], on_close: Callable[[], None]):
        self._on_open = on_open
        self._on_close = on_close
        self._running = False
        self._orca_running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ProcessMonitor", daemon=True)
        self._thread.start()
        logger.info("Process monitor started (watching for: %s).", ", ".join(ORCA_PROCESS_NAMES))

    def stop(self) -> None:
        self._running = False

    def _is_orca_running(self) -> bool:
        names_lower = {n.lower() for n in ORCA_PROCESS_NAMES}
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info.get("name") or ""
                if name.lower() in names_lower:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False

    def _loop(self) -> None:
        while self._running:
            try:
                is_running = self._is_orca_running()
                if is_running and not self._orca_running:
                    self._orca_running = True
                    logger.info("OrcaSlicer opened — starting sync engine.")
                    self._on_open()
                elif not is_running and self._orca_running:
                    self._orca_running = False
                    logger.info("OrcaSlicer closed — stopping sync engine.")
                    self._on_close()
            except Exception as e:
                logger.error("Process monitor error: %s", e)
            time.sleep(PROCESS_POLL_INTERVAL)
