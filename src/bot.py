"""Main bot loop — orchestrates everything."""
import argparse
import logging
import os
import signal
import sys
import time
from typing import Dict

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_config
from src.data.feed import MarketFeed, build_exchange, build_spot_exchange
from src.strategy.funding_arb import FundingArbStrategy, Signal
from src.strategy.sizing import calculate_position_size
from src.risk.manager import RiskManager, BotStatus
from src.execution.orders import OrderExecutor
from src.execution.rebalancer import Rebalancer
from src.monitoring.logger import init_db, log_trade, log_funding_payment, log_event
from src.monitoring.alerts import send_alert
from src.monitoring.dashboard import render_dashboard


def setup_logging(paper_mode: bool) -> None:
    os.makedirs("data", exist_ok=True)
    log_file = "data/bot.log"
    fmt = "%(asctime)s | %(levelname)s | %(module)s | %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def main() -> None:
    parser = argparse.ArgumentParser(description="Funding Rate Arbitrage Bot")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--paper", action="store_true", default=True, help="Paper trading (default)")
    mode_group.add_argument("--live", action="store_true", help="Live trading")
    args = parser.parse_args()

    paper_mode = not args.live

    if args.live:
        confirm = input("You are about to run in LIVE mode with real money. Type YES to confirm: ")
        if confirm.strip() != "YES":
            print("Aborted.")
            sys.exit(0)
        paper_mode = False

    setup_logging(paper_mode)
    log = logging.getLogger(__name__)

    log.info(f"Starting bot in {'PAPER' if paper_mode else 'LIVE'} mode")

    # 1. Load config
    config = load_config(paper_mode=paper_mode)

    # 2. Init DB
    init_db()

    # 3. Build exchange
    exchange = build_exchange(config)
    spot_exchange = build_spot_exchange(config)

    # 4. Get starting equity
    if paper_mode:
        starting_equity = 10000.0
        log.info("Paper mode: using mock equity of $10,000")
    else:
        # For split exchanges (Kraken), fetch spot balance from spot_exchange
        # and futures margin from futures exchange, then sum them
        spot_balance = spot_exchange.fetch_balance()
        spot_usdt = float(spot_balance.get('USDT', {}).get('free', 0))
        futures_balance = exchange.fetch_balance()
        futures_usdt = float(futures_balance.get('USDT', {}).get('free', 0))
        starting_equity = spot_usdt + futures_usdt
        log.info(f"Starting equity: ${starting_equity:.2f} (spot=${spot_usdt:.2f} + futures=${futures_usdt:.2f})")

    # 5. Initialize risk manager
    risk = RiskManager(
        daily_loss_limit_pct=config.risk.daily_loss_limit_pct,
        total_drawdown_limit_pct=config.risk.total_drawdown_limit_pct,
        max_position_pct=config.risk.max_position_pct,
        max_exchange_exposure_pct=config.risk.max_exchange_exposure_pct,
    )
    risk.initialize(starting_equity)

    # 6. Log start event
    log_event("STARTED", f"Bot started in {'PAPER' if paper_mode else 'LIVE'} mode. Equity: {starting_equity:.2f}")

    feed = MarketFeed(exchange, spot_exchange=spot_exchange)
    strategy = FundingArbStrategy(
        min_entry_apr=config.risk.min_funding_entry_apr,
        min_exit_apr=config.risk.min_funding_exit_apr,
    )
    executor = OrderExecutor(exchange, paper_mode=paper_mode, spot_exchange=spot_exchange)
    rebalancer = Rebalancer(executor, threshold_pct=config.risk.delta_rebalance_threshold)

    open_positions: Dict[str, dict] = {}
    funding_snapshots: Dict[str, any] = {}
    current_equity = starting_equity

    def close_all_positions(reason: str) -> None:
        log.warning(f"Closing all positions: {reason}")
        for asset, pos in list(open_positions.items()):
            qty = pos["qty"]
            snap = funding_snapshots.get(asset)
            price = snap.spot_price if snap else pos.get("entry_spot", 0)
            spot_res = executor.sell_spot(f"{asset}/USDT", qty, price)
            perp_res = executor.close_perp_short(f"{asset}/USDT:USDT", qty, price)
            if spot_res.success and perp_res.success:
                log.info(f"Closed {asset} position")
                log_trade(
                    asset=asset, action="EXIT",
                    spot_qty=qty, spot_price=spot_res.fill_price,
                    perp_price=perp_res.fill_price,
                    funding_rate_8h=snap.funding_rate_8h if snap else 0,
                    annualized_apr=snap.annualized_apr if snap else 0,
                    notional_usdt=pos["notional"],
                    fees_usdt=spot_res.fee_usdt + perp_res.fee_usdt,
                    paper=paper_mode,
                )
                del open_positions[asset]
            else:
                log.error(f"Failed to close {asset}: spot={spot_res.error} perp={perp_res.error}")
                send_alert(f"CRITICAL: Failed to close {asset} position! Manual intervention required.")

    def handle_signal(signum, frame):
        log.info("Received shutdown signal")
        close_all_positions("SIGTERM/SIGINT")
        log_event("STOPPED", "Bot stopped by signal")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info("Bot running. Press Ctrl+C to stop.")

    while True:
        try:
            exchange_exposure = sum(p["notional"] for p in open_positions.values())

            for asset in config.assets:
                try:
                    snapshot = feed.get_funding_snapshot(asset)
                    funding_snapshots[asset] = snapshot

                    in_position = asset in open_positions
                    decision = strategy.evaluate(snapshot, in_position)
                    log.info(f"{asset}: {decision.signal.value} — {decision.reason}")

                    if decision.signal == Signal.ENTER:
                        size = calculate_position_size(
                            asset=asset,
                            portfolio_usdt=current_equity,
                            spot_price=snapshot.spot_price,
                            max_position_pct=config.risk.max_position_pct,
                        )
                        if size is None:
                            log.warning(f"{asset}: Position size below minimum, skipping")
                            continue

                        allowed, reason = risk.check_pre_trade(
                            notional_usdt=size.notional_usdt,
                            portfolio_usdt=current_equity,
                            exchange_exposure_usdt=exchange_exposure,
                        )
                        if not allowed:
                            log.warning(f"{asset}: Pre-trade check failed: {reason}")
                            continue

                        spot_order = executor.buy_spot(size.spot_symbol, size.spot_qty, snapshot.spot_price)
                        perp_order = executor.short_perp(size.perp_symbol, size.perp_qty, snapshot.perp_price)

                        if not spot_order.success or not perp_order.success:
                            log.error(f"{asset}: Entry failed. Closing surviving leg.")
                            if spot_order.success:
                                executor.sell_spot(size.spot_symbol, size.spot_qty, snapshot.spot_price)
                            if perp_order.success:
                                executor.close_perp_short(size.perp_symbol, size.perp_qty, snapshot.perp_price)
                            continue

                        open_positions[asset] = {
                            "qty": size.spot_qty,
                            "entry_spot": snapshot.spot_price,
                            "notional": size.notional_usdt,
                        }
                        exchange_exposure += size.notional_usdt

                        log_trade(
                            asset=asset, action="ENTER",
                            spot_qty=size.spot_qty, spot_price=spot_order.fill_price,
                            perp_price=perp_order.fill_price,
                            funding_rate_8h=snapshot.funding_rate_8h,
                            annualized_apr=snapshot.annualized_apr,
                            notional_usdt=size.notional_usdt,
                            fees_usdt=spot_order.fee_usdt + perp_order.fee_usdt,
                            paper=paper_mode,
                        )
                        log.info(f"{asset}: ENTERED at spot={spot_order.fill_price:.2f}, notional=${size.notional_usdt:.2f}")

                    elif decision.signal == Signal.EXIT and in_position:
                        pos = open_positions[asset]
                        qty = pos["qty"]
                        spot_res = None
                        perp_res = None

                        for attempt in range(3):
                            spot_res = executor.sell_spot(f"{asset}/USDT", qty, snapshot.spot_price)
                            perp_res = executor.close_perp_short(f"{asset}/USDT:USDT", qty, snapshot.perp_price)
                            if spot_res.success and perp_res.success:
                                break
                            log.warning(f"{asset}: Exit attempt {attempt+1} failed, retrying...")
                            time.sleep(1)

                        if not spot_res.success or not perp_res.success:
                            send_alert(f"CRITICAL: Failed to exit {asset} after 3 attempts!")
                            log_event("ERROR", f"Failed to exit {asset}")
                            risk._halt(BotStatus.HALTED_MANUAL, f"Failed to exit {asset}")
                        else:
                            log_trade(
                                asset=asset, action="EXIT",
                                spot_qty=qty, spot_price=spot_res.fill_price,
                                perp_price=perp_res.fill_price,
                                funding_rate_8h=snapshot.funding_rate_8h,
                                annualized_apr=snapshot.annualized_apr,
                                notional_usdt=pos["notional"],
                                fees_usdt=spot_res.fee_usdt + perp_res.fee_usdt,
                                paper=paper_mode,
                            )
                            exchange_exposure -= pos["notional"]
                            del open_positions[asset]
                            log.info(f"{asset}: EXITED")

                    elif decision.signal == Signal.HOLD and in_position:
                        pos = open_positions[asset]
                        rebalancer.check_and_rebalance(
                            asset=asset,
                            spot_qty=pos["qty"],
                            spot_price=snapshot.spot_price,
                            perp_qty=pos["qty"],
                            perp_price=snapshot.perp_price,
                        )

                except Exception as e:
                    log.error(f"Error processing {asset}: {e}", exc_info=True)

            # Update equity (paper: approximate from starting + funding payments)
            risk.update_equity(current_equity)

            if risk.is_halted:
                log.critical(f"Bot halted: {risk.state.halt_reason}")
                close_all_positions("Risk halt")
                log_event("HALTED", risk.state.halt_reason)
                send_alert(f"BOT HALTED: {risk.state.halt_reason}")
                sys.exit(1)

            render_dashboard(
                risk_summary=risk.summary(),
                open_positions=open_positions,
                funding_snapshots=funding_snapshots,
                paper_mode=paper_mode,
            )

            log.info(f"Sleeping {config.funding_poll_interval_s}s until next poll...")
            time.sleep(config.funding_poll_interval_s)

        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)
            log_event("ERROR", str(e))
            time.sleep(30)


if __name__ == "__main__":
    main()
