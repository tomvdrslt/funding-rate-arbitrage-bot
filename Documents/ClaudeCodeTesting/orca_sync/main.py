import logging
import os
import sys
import threading

from config import LOG_FILE
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
    tray = TrayApp(
        on_sync_now=engine.sync_now,
        on_quit=_make_quit_handler(engine),
    )

    # Wire tray status updates from the engine
    engine._on_status = tray.set_status  # type: ignore[attr-defined]

    # Start the sync engine in a background thread
    sync_thread = threading.Thread(target=engine.start, name="SyncEngine", daemon=True)
    sync_thread.start()

    # Run tray on the main thread (required by pystray on Windows)
    try:
        tray.run()
        if not tray._icon:          # pystray unavailable — keep alive
            logger.info("No tray available; running headless. Press Ctrl+C to quit.")
            threading.Event().wait()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
    finally:
        engine.stop()
        logger.info("OrcaSlicer Profile Sync stopped.")


def _make_quit_handler(engine: SyncEngine):
    def _quit():
        logger.info("Quit requested from tray.")
        engine.stop()
        os._exit(0)
    return _quit


if __name__ == "__main__":
    main()
