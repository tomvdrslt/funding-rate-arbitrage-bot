import logging
import os
import sys
import threading

from config import LOG_FILE
from process_monitor import ProcessMonitor
from sync_engine import SyncEngine
from tray import TrayApp

# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("OrcaSlicer Profile Sync starting...")

    engine = SyncEngine()

    def on_orca_open():
        tray.set_status("syncing")
        threading.Thread(target=engine.start, name="SyncEngine", daemon=True).start()

    def on_orca_close():
        engine.stop()
        tray.set_status("waiting")

    monitor = ProcessMonitor(on_open=on_orca_open, on_close=on_orca_close)

    tray = TrayApp(
        on_sync_now=lambda: engine.sync_now() if engine.is_running() else None,
        on_quit=_make_quit_handler(engine, monitor),
    )

    # Wire tray status updates from the engine
    engine._on_status = tray.set_status  # type: ignore[attr-defined]

    monitor.start()
    tray.set_status("waiting")

    try:
        tray.run()
        if not tray._icon:          # pystray unavailable — keep alive
            logger.info("No tray available; running headless. Press Ctrl+C to quit.")
            threading.Event().wait()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
    finally:
        monitor.stop()
        engine.stop()
        logger.info("OrcaSlicer Profile Sync stopped.")


def _make_quit_handler(engine: SyncEngine, monitor: ProcessMonitor):
    def _quit():
        logger.info("Quit requested from tray.")
        monitor.stop()
        engine.stop()
        os._exit(0)
    return _quit


if __name__ == "__main__":
    main()
