"""Risk management — circuit breakers and position checks."""
import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class BotStatus(Enum):
    RUNNING = "RUNNING"
    HALTED_DAILY_LOSS = "HALTED_DAILY_LOSS"
    HALTED_DRAWDOWN = "HALTED_DRAWDOWN"
    HALTED_MANUAL = "HALTED_MANUAL"


@dataclass
class RiskState:
    starting_equity: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    daily_start_equity: float = 0.0
    daily_start_date: Optional[date] = None
    status: BotStatus = BotStatus.RUNNING
    halt_reason: str = ""
    total_pnl: float = 0.0
    total_funding_collected: float = 0.0
    trade_count: int = 0


class RiskManager:
    def __init__(self, daily_loss_limit_pct: float, total_drawdown_limit_pct: float,
                 max_position_pct: float, max_exchange_exposure_pct: float):
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.total_drawdown_limit_pct = total_drawdown_limit_pct
        self.max_position_pct = max_position_pct
        self.max_exchange_exposure_pct = max_exchange_exposure_pct
        self.state = RiskState()

    def initialize(self, starting_equity: float) -> None:
        """Set up initial risk state."""
        self.state = RiskState(
            starting_equity=starting_equity,
            peak_equity=starting_equity,
            current_equity=starting_equity,
            daily_start_equity=starting_equity,
            daily_start_date=date.today(),
            status=BotStatus.RUNNING,
        )
        logger.info(f"RiskManager initialized with equity={starting_equity:.2f}")

    def update_equity(self, current_equity: float) -> None:
        """Update equity and run circuit breaker checks."""
        self.state.current_equity = current_equity
        self.state.total_pnl = current_equity - self.state.starting_equity

        # Reset daily tracking on new day
        today = date.today()
        if self.state.daily_start_date != today:
            self.state.daily_start_equity = current_equity
            self.state.daily_start_date = today
            logger.info(f"New day — daily equity reset to {current_equity:.2f}")

        # Update peak
        if current_equity > self.state.peak_equity:
            self.state.peak_equity = current_equity

        # Run checks
        self._check_daily_loss()
        self._check_total_drawdown()

    def _check_daily_loss(self) -> None:
        if self.state.daily_start_equity <= 0:
            return
        daily_return = (self.state.current_equity - self.state.daily_start_equity) / self.state.daily_start_equity
        if daily_return < -(self.daily_loss_limit_pct / 100):
            self._halt(
                BotStatus.HALTED_DAILY_LOSS,
                f"Daily loss {daily_return*100:.2f}% exceeds limit -{self.daily_loss_limit_pct}%"
            )

    def _check_total_drawdown(self) -> None:
        if self.state.peak_equity <= 0:
            return
        drawdown = (self.state.peak_equity - self.state.current_equity) / self.state.peak_equity
        if drawdown > (self.total_drawdown_limit_pct / 100):
            self._halt(
                BotStatus.HALTED_DRAWDOWN,
                f"Total drawdown {drawdown*100:.2f}% exceeds limit {self.total_drawdown_limit_pct}%"
            )

    def _halt(self, status: BotStatus, reason: str) -> None:
        if self.state.status != BotStatus.RUNNING:
            return  # Already halted
        self.state.status = status
        self.state.halt_reason = reason
        logger.critical(f"BOT HALTED: {reason}")

    @property
    def is_halted(self) -> bool:
        return self.state.status != BotStatus.RUNNING

    def check_pre_trade(
        self, notional_usdt: float, portfolio_usdt: float, exchange_exposure_usdt: float
    ) -> Tuple[bool, str]:
        """
        Returns (allowed, reason).
        Returns (False, reason) if:
          - bot is halted
          - position too large (> max_position_pct of portfolio)
          - exchange exposure would exceed limit
        """
        if self.is_halted:
            return False, f"Bot is halted: {self.state.halt_reason}"

        if portfolio_usdt > 0:
            position_pct = notional_usdt / portfolio_usdt
            if position_pct > self.max_position_pct:
                return False, (
                    f"Position {position_pct*100:.1f}% exceeds max {self.max_position_pct*100:.1f}%"
                )

            new_exposure_pct = (exchange_exposure_usdt + notional_usdt) / portfolio_usdt
            if new_exposure_pct > self.max_exchange_exposure_pct:
                return False, (
                    f"Exchange exposure {new_exposure_pct*100:.1f}% would exceed max "
                    f"{self.max_exchange_exposure_pct*100:.1f}%"
                )

        return True, "OK"

    def record_funding_payment(self, amount_usdt: float) -> None:
        self.state.total_funding_collected += amount_usdt

    def summary(self) -> dict:
        s = self.state
        drawdown = 0.0
        if s.peak_equity > 0:
            drawdown = (s.peak_equity - s.current_equity) / s.peak_equity * 100
        daily_pnl = s.current_equity - s.daily_start_equity
        return {
            "status": s.status.value,
            "halt_reason": s.halt_reason,
            "starting_equity": s.starting_equity,
            "current_equity": s.current_equity,
            "peak_equity": s.peak_equity,
            "total_pnl": s.total_pnl,
            "total_pnl_pct": (s.total_pnl / s.starting_equity * 100) if s.starting_equity > 0 else 0,
            "daily_pnl": daily_pnl,
            "drawdown_from_peak_pct": drawdown,
            "total_funding_collected": s.total_funding_collected,
            "trade_count": s.trade_count,
        }
