"""Order placement with paper mode support."""
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import ccxt

logger = logging.getLogger(__name__)

SLIPPAGE = 0.0005   # 0.05%
TAKER_FEE = 0.0005  # 0.05%
MAKER_FEE = 0.0002  # 0.02%
LIMIT_AGGRESSION = 0.0005  # 0.05% inside market for limit orders


@dataclass
class OrderResult:
    success: bool
    symbol: str
    side: str
    qty: float
    fill_price: float
    fee_usdt: float
    order_id: str
    timestamp: float
    paper: bool
    error: str = ""


class OrderExecutor:
    def __init__(self, exchange: ccxt.Exchange, paper_mode: bool,
                 spot_exchange: ccxt.Exchange = None):
        self.exchange = exchange          # futures/perp exchange
        self.spot_exchange = spot_exchange or exchange  # spot exchange (same unless split e.g. Kraken)
        self.paper_mode = paper_mode

    # --- Paper mode helpers ---

    def _paper_order(self, symbol: str, side: str, qty: float, price: float) -> OrderResult:
        """Simulate a fill with slippage and fee."""
        if side in ("buy", "close_short"):
            fill_price = price * (1 + SLIPPAGE)
        else:
            fill_price = price * (1 - SLIPPAGE)
        fee_usdt = qty * fill_price * TAKER_FEE
        return OrderResult(
            success=True,
            symbol=symbol,
            side=side,
            qty=qty,
            fill_price=fill_price,
            fee_usdt=fee_usdt,
            order_id=f"PAPER-{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            paper=True,
        )

    # --- Live mode helpers ---

    def _live_order(self, symbol: str, side: str, qty: float, price: float,
                    ccxt_side: str, reduce_only: bool = False) -> OrderResult:
        """Place a limit order slightly aggressive to get a fill at near-maker fees."""
        try:
            if ccxt_side == "buy":
                limit_price = round(price * (1 + LIMIT_AGGRESSION), 2)
            else:
                limit_price = round(price * (1 - LIMIT_AGGRESSION), 2)

            params = {}
            if reduce_only:
                params["reduceOnly"] = True

            order = self.exchange.create_order(
                symbol=symbol,
                type="limit",
                side=ccxt_side,
                amount=qty,
                price=limit_price,
                params=params,
            )
            fill_price = float(order.get("average") or order.get("price") or limit_price)
            fee_usdt = qty * fill_price * MAKER_FEE
            return OrderResult(
                success=True,
                symbol=symbol,
                side=side,
                qty=qty,
                fill_price=fill_price,
                fee_usdt=fee_usdt,
                order_id=str(order.get("id", "")),
                timestamp=time.time(),
                paper=False,
            )
        except Exception as e:
            logger.error(f"Order failed {symbol} {side} qty={qty}: {e}")
            return OrderResult(
                success=False,
                symbol=symbol,
                side=side,
                qty=qty,
                fill_price=price,
                fee_usdt=0.0,
                order_id="",
                timestamp=time.time(),
                paper=False,
                error=str(e),
            )

    # --- Public API ---

    def buy_spot(self, symbol: str, qty: float, price: float) -> OrderResult:
        if self.paper_mode:
            return self._paper_order(symbol, "buy", qty, price)
        # Route to spot exchange
        orig = self.exchange
        self.exchange = self.spot_exchange
        result = self._live_order(symbol, "buy", qty, price, "buy")
        self.exchange = orig
        return result

    def sell_spot(self, symbol: str, qty: float, price: float) -> OrderResult:
        if self.paper_mode:
            return self._paper_order(symbol, "sell", qty, price)
        # Route to spot exchange
        orig = self.exchange
        self.exchange = self.spot_exchange
        result = self._live_order(symbol, "sell", qty, price, "sell")
        self.exchange = orig
        return result

    def short_perp(self, symbol: str, qty: float, price: float) -> OrderResult:
        if self.paper_mode:
            return self._paper_order(symbol, "short", qty, price)
        # Routes to futures exchange (self.exchange)
        return self._live_order(symbol, "short", qty, price, "sell")

    def close_perp_short(self, symbol: str, qty: float, price: float) -> OrderResult:
        if self.paper_mode:
            return self._paper_order(symbol, "close_short", qty, price)
        # Routes to futures exchange (self.exchange)
        return self._live_order(symbol, "close_short", qty, price, "buy", reduce_only=True)
