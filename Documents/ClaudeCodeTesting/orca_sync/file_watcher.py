import logging
import os
import threading
from typing import Callable

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from config import PROFILE_DIRS, WATCH_EXTENSIONS, DEBOUNCE_DELAY

logger = logging.getLogger(__name__)


class _DebounceHandler(FileSystemEventHandler):
    """Debounces rapid file-change events (e.g. editor save-then-rename patterns)."""

    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self._callback = callback
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext not in WATCH_EXTENSIONS:
            return

        with self._lock:
            existing = self._timers.get(path)
            if existing:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_DELAY, self._fire, args=[path])
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)
        if os.path.isfile(path):
            logger.debug("Local change detected: %s", path)
            self._callback(path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.dest_path)


class FileWatcher:
    def __init__(self, callback: Callable[[str], None]):
        self._callback = callback
        self._observer = Observer()
        self._handler = _DebounceHandler(callback)

    def start(self) -> None:
        for directory in PROFILE_DIRS:
            os.makedirs(directory, exist_ok=True)
            self._observer.schedule(self._handler, directory, recursive=True)
            logger.debug("Watching directory: %s", directory)
        self._observer.start()
        logger.info("File watcher started.")

    def stop(self) -> None:
        self._observer.stop()
        if self._observer.is_alive():
            self._observer.join()
        logger.info("File watcher stopped.")
