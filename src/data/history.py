"""Download historical 8h funding rates — supports multiple exchanges via CCXT."""
import requests
import pandas as pd
import os
import time
import ccxt
from datetime import datetime, timedelta


# Binance has a free public REST API with deep history — use it directly when available
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

# Bybit public REST API
BYBIT_FUNDING_URL = "https://api.bybit.com/v5/market/funding/history"

# OKX public REST API
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate-history"


def _fetch_binance(symbol: str, start_ms: int, end_ms: int) -> list:
    records = []
    current_start = start_ms
    while current_start < end_ms:
        params = {"symbol": symbol, "startTime": current_start, "endTime": end_ms, "limit": 1000}
        resp = requests.get(BINANCE_FUNDING_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        records.extend(data)
        last_time = data[-1]["fundingTime"]
        current_start = last_time + 1
        if len(data) < 1000:
            break
        time.sleep(0.2)
    return [
        {"timestamp": r["fundingTime"], "fundingRate": float(r["fundingRate"])}
        for r in records
    ]


def _fetch_bybit(symbol: str, start_ms: int, end_ms: int) -> list:
    records = []
    current_end = end_ms
    while True:
        params = {
            "category": "linear",
            "symbol": symbol,
            "startTime": start_ms,
            "endTime": current_end,
            "limit": 200,
        }
        resp = requests.get(BYBIT_FUNDING_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("result", {}).get("list", [])
        if not rows:
            break
        records.extend(rows)
        # Bybit returns newest first
        oldest_ts = int(rows[-1]["fundingRateTimestamp"])
        if oldest_ts <= start_ms or len(rows) < 200:
            break
        current_end = oldest_ts - 1
        time.sleep(0.2)
    return [
        {"timestamp": int(r["fundingRateTimestamp"]), "fundingRate": float(r["fundingRate"])}
        for r in records
    ]


def _fetch_okx(symbol: str, start_ms: int, end_ms: int) -> list:
    # OKX instId format: BTC-USDT-SWAP
    records = []
    current_end = end_ms
    while True:
        params = {
            "instId": symbol,
            "before": start_ms,
            "after": current_end,
            "limit": 100,
        }
        resp = requests.get(OKX_FUNDING_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", [])
        if not rows:
            break
        records.extend(rows)
        oldest_ts = int(rows[-1]["fundingTime"])
        if oldest_ts <= start_ms or len(rows) < 100:
            break
        current_end = oldest_ts - 1
        time.sleep(0.2)
    return [
        {"timestamp": int(r["fundingTime"]), "fundingRate": float(r["fundingRate"])}
        for r in records
    ]


def _fetch_ccxt_generic(exchange_name: str, symbol: str, start_ms: int, end_ms: int) -> list:
    """Fallback: use CCXT fetch_funding_rate_history for any supported exchange."""
    exchange_cls = getattr(ccxt, exchange_name)
    exchange = exchange_cls({'enableRateLimit': True})
    records = []
    current_start = start_ms
    while current_start < end_ms:
        try:
            rows = exchange.fetch_funding_rate_history(symbol, since=current_start, limit=100)
        except Exception as e:
            print(f"  CCXT fetch error: {e}")
            break
        if not rows:
            break
        records.extend(rows)
        last_ts = rows[-1]['timestamp']
        if last_ts <= current_start or len(rows) < 100:
            break
        current_start = last_ts + 1
        time.sleep(0.3)
    return [
        {"timestamp": r["timestamp"], "fundingRate": float(r["fundingRate"])}
        for r in records
    ]


def fetch_funding_history(
    asset: str,
    days: int = 365,
    save_csv: bool = True,
    exchange: str = "binance",
) -> pd.DataFrame:
    """
    Fetch historical funding rates for an asset from the specified exchange.

    Supported exchanges: binance, bybit, okx, bitget, gate, and any CCXT exchange
    with fetch_funding_rate_history support.

    Returns:
        DataFrame with columns: timestamp, symbol, fundingRate, annualized_apr
    """
    exchange = exchange.lower()
    end_ms = int(datetime.utcnow().timestamp() * 1000)
    start_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)

    print(f"Fetching {days}d funding history for {asset} from {exchange}...")

    if exchange == "binance":
        symbol = f"{asset}USDT"
        records = _fetch_binance(symbol, start_ms, end_ms)
    elif exchange == "bybit":
        symbol = f"{asset}USDT"
        records = _fetch_bybit(symbol, start_ms, end_ms)
    elif exchange == "okx":
        symbol = f"{asset}-USDT-SWAP"
        records = _fetch_okx(symbol, start_ms, end_ms)
    else:
        # Generic CCXT fallback — works for bitget, gate, kraken, etc.
        ccxt_symbol = f"{asset}/USDT:USDT"
        records = _fetch_ccxt_generic(exchange, ccxt_symbol, start_ms, end_ms)

    if not records:
        print("No data returned.")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["symbol"] = f"{asset}/USDT:USDT"
    df["fundingRate"] = df["fundingRate"].astype(float)
    df["annualized_apr"] = df["fundingRate"] * 3 * 365 * 100
    df = df[["timestamp", "symbol", "fundingRate", "annualized_apr"]].sort_values("timestamp").reset_index(drop=True)

    if save_csv:
        os.makedirs("data", exist_ok=True)
        csv_path = f"data/{asset}_{exchange}_funding_history.csv"
        df.to_csv(csv_path, index=False)
        print(f"Saved to {csv_path}")

    print(f"\nSummary: {len(df)} records | Mean APR: {df['annualized_apr'].mean():.2f}% | "
          f"Min: {df['annualized_apr'].min():.2f}% | Max: {df['annualized_apr'].max():.2f}%")

    return df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", default="BTC")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--exchange", default="binance")
    args = parser.parse_args()
    df = fetch_funding_history(args.asset, days=args.days, save_csv=True, exchange=args.exchange)
    print(df.tail(10))
