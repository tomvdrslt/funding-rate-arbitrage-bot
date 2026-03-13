"""SQLite trade logger."""
import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "data/trades.db"


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize the SQLite database and create tables."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            asset TEXT NOT NULL,
            action TEXT NOT NULL,
            spot_qty REAL,
            spot_price REAL,
            perp_price REAL,
            funding_rate_8h REAL,
            annualized_apr REAL,
            notional_usdt REAL,
            fees_usdt REAL,
            paper INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS funding_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            asset TEXT NOT NULL,
            funding_rate_8h REAL,
            position_notional REAL,
            payment_usdt REAL,
            paper INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT
        )
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {db_path}")


def log_trade(
    asset: str,
    action: str,
    spot_qty: float,
    spot_price: float,
    perp_price: float,
    funding_rate_8h: float,
    annualized_apr: float,
    notional_usdt: float,
    fees_usdt: float,
    paper: bool,
    db_path: str = DB_PATH,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO trades
           (timestamp, asset, action, spot_qty, spot_price, perp_price,
            funding_rate_8h, annualized_apr, notional_usdt, fees_usdt, paper)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.utcnow().isoformat(),
            asset, action, spot_qty, spot_price, perp_price,
            funding_rate_8h, annualized_apr, notional_usdt, fees_usdt, int(paper),
        ),
    )
    conn.commit()
    conn.close()


def log_funding_payment(
    asset: str,
    funding_rate_8h: float,
    position_notional: float,
    payment_usdt: float,
    paper: bool,
    db_path: str = DB_PATH,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO funding_payments
           (timestamp, asset, funding_rate_8h, position_notional, payment_usdt, paper)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            datetime.utcnow().isoformat(),
            asset, funding_rate_8h, position_notional, payment_usdt, int(paper),
        ),
    )
    conn.commit()
    conn.close()


def log_event(
    event_type: str,
    message: str,
    db_path: str = DB_PATH,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO bot_events (timestamp, event_type, message) VALUES (?, ?, ?)",
        (datetime.utcnow().isoformat(), event_type, message),
    )
    conn.commit()
    conn.close()
