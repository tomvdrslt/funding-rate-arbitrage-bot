"""Historical backtest runner for funding rate arbitrage strategy."""
import argparse
import os
import sys

import numpy as np
import pandas as pd

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.history import fetch_funding_history


ENTRY_FEE_PCT = 0.0014   # (maker+taker)*2 legs = (0.0002+0.0005)*2
EXIT_FEE_PCT = 0.0014


def run_backtest(
    asset: str,
    days: int,
    capital: float,
    position_pct: float,
    min_entry_apr: float,
    min_exit_apr: float,
    exchange: str = "binance",
) -> None:
    csv_path = f"data/{asset}_{exchange}_funding_history.csv"
    legacy_path = f"data/{asset}_funding_history.csv"

    # Fall back to legacy path if exchange-specific file doesn't exist
    if not os.path.exists(csv_path) and os.path.exists(legacy_path):
        csv_path = legacy_path

    if os.path.exists(csv_path):
        print(f"Loading cached history from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    else:
        print(f"Fetching history for {asset} from {exchange}...")
        df = fetch_funding_history(asset, days=days, save_csv=True, exchange=exchange)

    if df.empty:
        print("No data available.")
        return

    # Trim to requested days
    cutoff = df["timestamp"].max() - pd.Timedelta(days=days)
    df = df[df["timestamp"] >= cutoff].reset_index(drop=True)
    print(f"Using {len(df)} periods over {days} days")

    equity = capital
    position_notional = capital * position_pct
    in_position = False
    equities = [capital]
    total_funding = 0.0
    total_fees = 0.0
    trade_count = 0
    daily_equities = {}

    for _, row in df.iterrows():
        apr = row["annualized_apr"]
        funding_rate_8h = row["fundingRate"]

        # Strategy logic (mirrors funding_arb.py)
        if in_position:
            if funding_rate_8h < 0 or apr < min_exit_apr:
                # EXIT
                fee = position_notional * EXIT_FEE_PCT
                equity -= fee
                total_fees += fee
                in_position = False
                trade_count += 1
        else:
            if funding_rate_8h >= 0 and apr >= min_entry_apr:
                # ENTER
                fee = position_notional * ENTRY_FEE_PCT
                equity -= fee
                total_fees += fee
                in_position = True
                trade_count += 1

        # Collect funding if in position
        if in_position:
            payment = position_notional * funding_rate_8h
            equity += payment
            total_funding += payment

        equities.append(equity)

        # Track daily equity for Sharpe
        ts = row["timestamp"]
        day_key = ts.date() if hasattr(ts, 'date') else str(ts)[:10]
        daily_equities[day_key] = equity

    equity_series = pd.Series(list(daily_equities.values()))
    daily_returns = equity_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(365)) if daily_returns.std() > 0 else 0.0

    eq_arr = np.array(equities)
    peak = np.maximum.accumulate(eq_arr)
    drawdown = (peak - eq_arr) / peak
    max_drawdown = drawdown.max() * 100

    total_return_pct = (equity - capital) / capital * 100
    annualized_return_pct = total_return_pct / days * 365

    print("\n" + "=" * 50)
    print(f"BACKTEST RESULTS — {asset} ({days} days)")
    print("=" * 50)
    print(f"Starting capital:      ${capital:,.2f}")
    print(f"Final equity:          ${equity:,.2f}")
    print(f"Total return:          {total_return_pct:.2f}%")
    print(f"Annualized return:     {annualized_return_pct:.2f}%")
    print(f"Max drawdown:          {max_drawdown:.2f}%")
    print(f"Sharpe ratio:          {sharpe:.2f}")
    print(f"Total trades:          {trade_count}")
    print(f"Total funding:         ${total_funding:,.2f}")
    print(f"Total fees:            ${total_fees:,.2f}")
    print("=" * 50)

    # Warnings
    if annualized_return_pct <= 5:
        print("WARNING: Annualized return <= 5%. Strategy may not be profitable in this period.")
    if sharpe <= 1.0:
        print("WARNING: Sharpe ratio <= 1.0. Risk-adjusted returns are below target.")
    if max_drawdown >= 15:
        print("WARNING: Max drawdown >= 15%. Exceeds risk threshold.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Funding rate arbitrage backtest")
    parser.add_argument("--asset", default="BTC")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--position-pct", type=float, default=0.20)
    parser.add_argument("--min-entry-apr", type=float, default=5.0)
    parser.add_argument("--min-exit-apr", type=float, default=3.0)
    args = parser.parse_args()

    run_backtest(
        asset=args.asset,
        days=args.days,
        capital=args.capital,
        position_pct=args.position_pct,
        min_entry_apr=args.min_entry_apr,
        min_exit_apr=args.min_exit_apr,
    )
