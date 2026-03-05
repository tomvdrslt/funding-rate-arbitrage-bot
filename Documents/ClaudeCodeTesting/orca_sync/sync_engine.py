import datetime
import logging
import os
import threading
import time
from typing import Callable, Optional

from drive_client import DriveClient
from file_watcher import FileWatcher
from config import PROFILE_DIRS, POLL_INTERVAL, WATCH_EXTENSIONS

logger = logging.getLogger(__name__)

# How long (seconds) to suppress re-uploading a file after we downloaded it
ECHO_SUPPRESS_TTL = 10.0


class SyncEngine:
    def __init__(self, on_status: Optional[Callable[[str], None]] = None):
        """
        on_status: callback(status) where status is "synced" | "syncing" | "error"
        """
        self._on_status = on_status or (lambda s: None)
        self._stop_event = threading.Event()
        self._recently_downloaded: dict[str, float] = {}
        self._echo_lock = threading.Lock()
        self._drive: Optional[DriveClient] = None
        self._watcher: Optional[FileWatcher] = None
        self._page_token: Optional[str] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop_event.clear()
        self._running = True
        with self._echo_lock:
            self._recently_downloaded.clear()

        self._drive = DriveClient()
        self._watcher = FileWatcher(self._on_local_change)
        self._page_token = self._drive.get_start_page_token()

        # Pull any Drive changes that happened while OrcaSlicer was closed
        self._catch_up()

        self._watcher.start()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="DrivePoller", daemon=True
        )
        self._poll_thread.start()
        logger.info("Sync engine started.")
        self._on_status("synced")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._watcher:
            self._watcher.stop()
        logger.info("Sync engine stopped.")

    def sync_now(self) -> None:
        """Force an immediate poll cycle."""
        logger.info("Manual sync triggered.")
        self._poll_once()

    # ------------------------------------------------------------------
    # Catch-up sync (Drive → local, run once on engine start)
    # ------------------------------------------------------------------

    def _catch_up(self) -> None:
        """Download any Drive files that are newer than local copies."""
        logger.info("Running catch-up sync from Drive...")
        self._on_status("syncing")
        try:
            all_files = self._drive.list_all_files()
            downloaded = 0
            for file_id, rel_path, modified_time_str in all_files:
                ext = os.path.splitext(rel_path)[1].lower()
                if ext not in WATCH_EXTENSIONS:
                    continue
                local_path = self._rel_to_local(rel_path)
                if local_path is None:
                    continue
                if not os.path.isfile(local_path):
                    logger.info("Catch-up: downloading missing file %s", rel_path)
                    self._drive.download(file_id, local_path)
                    self._suppress_echo(local_path)
                    downloaded += 1
                elif modified_time_str:
                    drive_dt = datetime.datetime.fromisoformat(
                        modified_time_str.replace("Z", "+00:00")
                    )
                    local_dt = datetime.datetime.fromtimestamp(
                        os.path.getmtime(local_path), tz=datetime.timezone.utc
                    )
                    if drive_dt > local_dt:
                        logger.info("Catch-up: downloading updated file %s", rel_path)
                        self._drive.download(file_id, local_path)
                        self._suppress_echo(local_path)
                        downloaded += 1
            logger.info("Catch-up complete — %d file(s) updated.", downloaded)
        except Exception as e:
            logger.error("Catch-up sync error: %s", e)
            self._on_status("error")

    # ------------------------------------------------------------------
    # Local → Drive
    # ------------------------------------------------------------------

    def _on_local_change(self, local_path: str) -> None:
        with self._echo_lock:
            suppress_until = self._recently_downloaded.get(local_path, 0)
            if time.time() < suppress_until:
                logger.debug("Skipping upload (echo suppression): %s", local_path)
                return

        rel_path = self._local_to_rel(local_path)
        if rel_path is None:
            logger.warning("Could not compute rel_path for %s — skipping upload", local_path)
            return

        self._on_status("syncing")
        try:
            self._drive.upload(local_path, rel_path)
            self._on_status("synced")
        except Exception as e:
            logger.error("Upload error for %s: %s", local_path, e)
            self._on_status("error")

    # ------------------------------------------------------------------
    # Drive → Local
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as e:
                logger.error("Poll error: %s", e)
                self._on_status("error")
            self._stop_event.wait(timeout=POLL_INTERVAL)

    def _poll_once(self) -> None:
        if self._page_token is None:
            return

        changed_files, new_token = self._drive.poll_changes(self._page_token)
        self._page_token = new_token

        if not changed_files:
            return

        self._on_status("syncing")
        any_error = False

        for file_meta in changed_files:
            try:
                self._process_remote_change(file_meta)
            except Exception as e:
                logger.error("Error processing remote change for %s: %s", file_meta.get("name"), e)
                any_error = True

        self._on_status("error" if any_error else "synced")

    def _process_remote_change(self, file_meta: dict) -> None:
        file_id = file_meta["id"]
        rel_path = self._drive.resolve_path(file_id)
        if rel_path is None:
            logger.debug("File %s is not under OrcaSlicerSync — ignoring", file_meta.get("name"))
            return

        local_path = self._rel_to_local(rel_path)
        if local_path is None:
            logger.debug("rel_path %s does not map to a watched directory — ignoring", rel_path)
            return

        drive_mtime_str = file_meta.get("modifiedTime", "")
        if drive_mtime_str and os.path.isfile(local_path):
            drive_dt = datetime.datetime.fromisoformat(drive_mtime_str.replace("Z", "+00:00"))
            local_dt = datetime.datetime.fromtimestamp(
                os.path.getmtime(local_path), tz=datetime.timezone.utc
            )
            if local_dt >= drive_dt:
                logger.debug("Local copy is newer or equal for %s — skipping download", rel_path)
                return

        logger.info("Downloading updated file: %s", rel_path)
        self._drive.download(file_id, local_path)
        self._suppress_echo(local_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _suppress_echo(self, local_path: str) -> None:
        with self._echo_lock:
            self._recently_downloaded[local_path] = time.time() + ECHO_SUPPRESS_TTL

    def _local_to_rel(self, local_path: str) -> Optional[str]:
        norm = os.path.normpath(local_path)
        for watch_dir in PROFILE_DIRS:
            norm_dir = os.path.normpath(watch_dir)
            dir_basename = os.path.basename(norm_dir)
            if norm.startswith(norm_dir + os.sep) or norm == norm_dir:
                tail = os.path.relpath(norm, norm_dir)
                return os.path.join(dir_basename, tail)
        return None

    def _rel_to_local(self, rel_path: str) -> Optional[str]:
        parts = rel_path.replace("\\", "/").split("/", 1)
        dir_basename = parts[0]
        tail = parts[1] if len(parts) > 1 else ""
        for watch_dir in PROFILE_DIRS:
            if os.path.basename(os.path.normpath(watch_dir)) == dir_basename:
                return os.path.join(watch_dir, tail) if tail else watch_dir
        return None
