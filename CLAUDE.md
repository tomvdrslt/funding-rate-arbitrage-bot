# Funding Rate Arbitrage Bot

Build a delta-neutral crypto trading bot that collects perpetual futures funding payments. The bot holds equal-value long spot and short perpetual positions simultaneously — price moves cancel out, and P&L comes purely from funding payments paid every 8 hours.

## What to build

Build the entire project from scratch. Every file listed below needs to be created and functional. Work through the steps in order — each has a test checkpoint before moving on.

---

## Project structure

```
funding-arb/
├── CLAUDE.md
├── requirements.txt
├── .gitignore
├── config/
│   ├── settings.py          # All config loaded from .env via dataclasses
│   └── .env.example         # Template — never commit the real .env
├── src/
│   ├── bot.py               # Main loop — orchestrates everything
│   ├── data/
│   │   ├── feed.py          # Live funding rate + price feed via CCXT
│   │   └── history.py       # Historical funding rate downloader for backtesting
│   ├── strategy/
│   │   ├── funding_arb.py   # Signal logic: ENTER / HOLD / EXIT / NO_TRADE
│   │   └── sizing.py        # Position sizing
│   ├── risk/
│   │   └── manager.py       # All circuit breakers and risk state
│   ├── execution/
│   │   ├── orders.py        # Order placement with paper mode
│   │   └── rebalancer.py    # Delta hedge rebalancer
│   └── monitoring/
│       ├── logger.py        # SQLite trade log
│       ├── alerts.py        # Telegram alerts (optional)
│       └── dashboard.py     # Rich CLI dashboard
├── scripts/
│   └── backtest.py          # Historical backtest runner
└── tests/
    ├── test_strategy.py
    ├── test_risk.py
    ├── test_sizing.py
    └── test_orders.py
```

---

## Step 1 — Scaffold

Create all directories. Create these files:

**requirements.txt**
```
ccxt>=4.3.0
pandas>=2.0.0
numpy>=1.26.0
python-dotenv>=1.0.0
requests>=2.31.0
pytest>=8.0.0
rich>=13.0.0
```

**.gitignore**
```
config/.env
data/
*.db
*.log
__pycache__/
.pytest_cache/
*.pyc
```

**config/.env.example**
```
EXCHANGE=binance
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
USE_TESTNET=true

ASSETS=BTC

MAX_POSITION_PCT=0.20
MAX_EXCHANGE_EXPOSURE_PCT=0.50
MIN_FUNDING_ENTRY_APR=5.0
MIN_FUNDING_EXIT_APR=3.0
DAILY_LOSS_LIMIT_PCT=3.0
TOTAL_DRAWDOWN_LIMIT_PCT=15.0
DELTA_REBALANCE_THRESHOLD=2.0

FUNDING_POLL_INTERVAL_S=3600
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**config/settings.py** — load all config from .env using dataclasses. Fields: ExchangeConfig (name, api_key, api_secret, testnet), RiskConfig (all thresholds), BotConfig (exchange, risk, assets list, poll interval, paper_mode). Expose a `load_config(paper_mode: bool) -> BotConfig` function.

---

## Step 2 — Data layer

**src/data/history.py**

Download historical 8h funding rates from Binance public API (no auth required):
`GET https://fapi.binance.com/fapi/v1/fundingRate`

- Accept params: symbol, startTime, endTime, limit (max 1000)
- Paginate until full date range is covered
- Return a pandas DataFrame: [timestamp, symbol, fundingRate, annualized_apr]
- annualized_apr = fundingRate * 3 * 365 * 100
- Save to `data/{ASSET}_funding_history.csv`
- Expose: `fetch_funding_history(asset, days, save_csv) -> DataFrame`

**src/data/feed.py**

- `FundingSnapshot` dataclass: asset, timestamp, funding_rate_8h, annualized_apr, next_funding_time, spot_price, perp_price, basis_pct
- `MarketFeed` class using CCXT: `get_funding_snapshot(asset) -> FundingSnapshot`
- `build_exchange(config) -> ccxt.Exchange` factory: reads config, supports testnet, sets `defaultType: future`
- Spot symbol format: `BTC/USDT`. Perp format: `BTC/USDT:USDT`

**Test checkpoint:** Run `python src/data/history.py` standalone and verify the CSV downloads with real data. Mean annualized_apr for BTC should be roughly 5–20% over the past 2 years.

---

## Step 3 — Strategy logic

**src/strategy/funding_arb.py**

Signal enum: `ENTER`, `HOLD`, `EXIT`, `NO_TRADE`

`StrategyDecision` dataclass: signal, asset, annualized_apr, reason

`FundingArbStrategy` class, initialized with `min_entry_apr` and `min_exit_apr`:

```
evaluate(snapshot: FundingSnapshot, currently_in_position: bool) -> StrategyDecision

Logic:
  if funding < 0 and in_position  → EXIT  (would start paying)
  if funding < 0 and not in_position → NO_TRADE
  if in_position and apr < min_exit_apr → EXIT
  if not in_position and apr >= min_entry_apr → ENTER
  if in_position and apr >= min_exit_apr → HOLD
  else → NO_TRADE
```

**src/strategy/sizing.py**

`PositionSize` dataclass: asset, spot_qty, perp_qty, notional_usdt, spot_symbol, perp_symbol

`calculate_position_size(asset, portfolio_usdt, spot_price, max_position_pct, min_order_size=10.0) -> PositionSize | None`

- notional = portfolio_usdt * max_position_pct
- qty = notional / spot_price, rounded to exchange precision (BTC: 5dp, ETH: 4dp)
- Return None if actual_notional < min_order_size

---

## Step 4 — Risk management

**src/risk/manager.py**

This is the most important file. None of these rules are ever softened.

`BotStatus` enum: `RUNNING`, `HALTED_DAILY_LOSS`, `HALTED_DRAWDOWN`, `HALTED_MANUAL`

`RiskState` dataclass: starting_equity, peak_equity, current_equity, daily_start_equity, daily_start_date, status, halt_reason, total_pnl, total_funding_collected, trade_count

`RiskManager` class:

- `initialize(starting_equity)` — sets up state
- `update_equity(current_equity)` — updates state, resets daily tracking on new day, updates peak, runs circuit breaker checks
- `_check_daily_loss()` — halt if (current - daily_start) / daily_start < -daily_loss_limit_pct / 100
- `_check_total_drawdown()` — halt if (peak - current) / peak > total_drawdown_limit_pct / 100
- `_halt(status, reason)` — sets halted state, logs at CRITICAL level
- `is_halted` property
- `check_pre_trade(notional_usdt, portfolio_usdt, exchange_exposure_usdt) -> (bool, str)` — returns (False, reason) if halted, position too large, or exchange exposure would exceed limit
- `record_funding_payment(amount_usdt)` — adds to total_funding_collected
- `summary() -> dict` — returns all key metrics

**Test checkpoint:** Write `tests/test_risk.py` now. Test:
- Daily loss breach triggers HALTED_DAILY_LOSS
- Total drawdown breach triggers HALTED_DRAWDOWN  
- Halted state blocks pre-trade checks
- Within-limit updates don't halt
- Peak equity tracked correctly
All tests must pass before continuing.

---

## Step 5 — Execution layer

**src/execution/orders.py**

`OrderResult` dataclass: success, symbol, side, qty, fill_price, fee_usdt, order_id, timestamp, paper, error

`OrderExecutor` class, initialized with `exchange` and `paper_mode`:

- `buy_spot(symbol, qty, price) -> OrderResult`
- `sell_spot(symbol, qty, price) -> OrderResult`
- `short_perp(symbol, qty, price) -> OrderResult`
- `close_perp_short(symbol, qty, price) -> OrderResult`

Paper mode: fill at price ± 0.05% slippage, deduct 0.05% taker fee, generate a fake order ID.

Live mode: place limit orders slightly aggressive (0.05% inside market) to get fills while targeting maker fee (0.02%). Use CCXT `create_order`. Wrap in try/except — return OrderResult with success=False and error string on failure, never raise.

**src/execution/rebalancer.py**

`Rebalancer` class: given current spot notional and perp notional, if drift > threshold, place corrective orders to bring back to equal notional.

---

## Step 6 — Monitoring

**src/monitoring/logger.py**

SQLite database at `data/trades.db`. Initialize with `init_db()`.

Three tables:
- `trades`: id, timestamp, asset, action (ENTER/EXIT), spot_qty, spot_price, perp_price, funding_rate_8h, annualized_apr, notional_usdt, fees_usdt, paper
- `funding_payments`: id, timestamp, asset, funding_rate_8h, position_notional, payment_usdt, paper
- `bot_events`: id, timestamp, event_type (STARTED/HALTED/STOPPED/ERROR), message

Expose: `log_trade(...)`, `log_funding_payment(...)`, `log_event(...)`

**src/monitoring/alerts.py**

Telegram integration using Bot API. All functions are no-ops if TELEGRAM_BOT_TOKEN is not set. Expose: `send_alert(message)`. Bot must run fine without Telegram configured.

**src/monitoring/dashboard.py**

Rich CLI dashboard that prints current status: bot mode, positions open, current APR per asset, total P&L, funding collected, equity, drawdown from peak. Refresh on demand (called from main loop).

---

## Step 7 — Backtest

**scripts/backtest.py**

CLI args: `--asset BTC`, `--days 365`, `--capital 10000`, `--position-pct 0.20`, `--min-entry-apr 5.0`, `--min-exit-apr 3.0`

Load or fetch the funding history CSV. Simulate the strategy period by period:
- Entry fee: (maker + taker) * 2 legs = (0.0002 + 0.0005) * 2 = 0.14% of notional
- Exit fee: same
- On each 8h period where in_position: equity += position_notional * funding_rate_8h
- Apply entry/exit logic matching funding_arb.py exactly

Print results:
```
Final equity, Total return %, Annualized return %, Max drawdown %, Sharpe ratio, Total trades, Total funding collected
```

Sharpe = (mean daily return / std daily return) * sqrt(365)

**Test checkpoint:** Run `python scripts/backtest.py --asset BTC --days 730`. You should see annualized return > 5%, Sharpe > 1.0, max drawdown < 15%. If not, print a warning but do not change the thresholds — report back for instructions.

---

## Step 8 — Main bot loop

**src/bot.py**

CLI: `--paper` (default) or `--live`. Live mode requires typing `YES` to confirm.

Logging: stdout + `data/bot.log`, format: `timestamp | level | module | message`

Startup sequence:
1. Load config
2. init_db()
3. build_exchange(config)
4. Fetch starting USDT balance (paper mode: use 10000.0 as mock)
5. Initialize RiskManager
6. Log STARTED event

Main loop (runs forever until halted or SIGTERM):
```
for each asset in config.assets:
    snapshot = feed.get_funding_snapshot(asset)
    decision = strategy.evaluate(snapshot, asset in open_positions)
    
    if ENTER:
        size = calculate_position_size(...)
        if size is None: continue
        allowed, reason = risk.check_pre_trade(...)
        if not allowed: log warning, continue
        spot_order = executor.buy_spot(...)
        perp_order = executor.short_perp(...)
        if either fails: close the surviving leg, log ERROR, continue
        open_positions[asset] = {qty, entry_spot, notional}
        log_trade(action=ENTER, ...)
    
    if EXIT and in_position:
        spot_order = executor.sell_spot(...)
        perp_order = executor.close_perp_short(...)
        retry failed legs up to 3 times
        if still failing: send_alert, halt bot
        log_trade(action=EXIT, ...)
        del open_positions[asset]

risk.update_equity(current_equity)
if risk.is_halted: close all positions, log event, sys.exit(1)

sleep(config.funding_poll_interval_s)
```

Handle SIGINT/SIGTERM: close all open positions gracefully, log STOPPED event, exit cleanly.

---

## Step 9 — Full test suite

Write all tests. All must pass before any live capital is used.

**tests/test_strategy.py** — test every signal combination:
- APR above threshold, not in position → ENTER
- APR below threshold, not in position → NO_TRADE  
- In position, APR above exit threshold → HOLD
- In position, APR below exit threshold → EXIT
- Negative funding, not in position → NO_TRADE
- Negative funding, in position → EXIT
- Exactly at entry threshold → ENTER
- Exactly at exit threshold → HOLD (not exit)

**tests/test_risk.py** — already written in Step 4. Verify all pass.

**tests/test_sizing.py**:
- Correct notional calculation
- Correct quantity rounding per asset
- Returns None when below minimum order size

**tests/test_orders.py**:
- Paper mode applies correct slippage direction per side
- Paper mode deducts fees
- Live mode failure returns OrderResult with success=False, not an exception

Run: `pytest tests/ -v`

---

## Non-negotiable rules (never change these without explicit instruction)

1. API keys must have TRADE permission only — never withdrawal
2. Daily loss circuit breaker: halt if daily P&L < -3% of portfolio
3. Total drawdown circuit breaker: halt if equity < 85% of peak
4. Max position size: 20% of portfolio per asset
5. Max exchange exposure: 50% of total portfolio on exchange at once
6. Only enter when annualized APR > 5% — below this, fees eat the edge
7. Exit when APR drops below 3% or goes negative
8. If either leg of an entry fails, immediately close the other leg — never hold a naked position

Do not soften, remove, or make these runtime-configurable.

---

## How funding arbitrage works (context for implementation decisions)

Perpetual futures use a funding rate to keep the perp price anchored to spot. Every 8 hours, if perp > spot (positive funding), longs pay shorts. By holding long spot + short perp in equal notional, we are always delta-neutral (price moves cancel) and always on the receiving side when funding is positive.

Annualized APR = funding_rate_8h × 3 × 365 × 100

Historically BTC/ETH have averaged 0.01–0.03% per 8h period (~11–33% APR), with higher spikes in bull markets and occasional negative periods. The bot sits out negative periods.

Exchange: Binance (primary). Testnet: testnet.binancefuture.com. CCXT identifier: `binance`. Set `sandbox=True` for testnet.
