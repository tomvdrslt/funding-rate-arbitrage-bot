"""Tests for risk manager."""
import pytest
from datetime import date

from src.risk.manager import RiskManager, BotStatus


@pytest.fixture
def risk():
    rm = RiskManager(
        daily_loss_limit_pct=3.0,
        total_drawdown_limit_pct=15.0,
        max_position_pct=0.20,
        max_exchange_exposure_pct=0.50,
    )
    rm.initialize(10000.0)
    return rm


def test_daily_loss_breach_halts(risk):
    risk.update_equity(9600.0)  # -4%, exceeds 3% limit
    assert risk.state.status == BotStatus.HALTED_DAILY_LOSS
    assert risk.is_halted


def test_total_drawdown_breach_halts(risk):
    # First push equity up to set peak
    risk.update_equity(12000.0)
    # Then drop beyond 15% drawdown from peak
    risk.update_equity(10000.0)  # 10000/12000 = 16.7% drawdown
    assert risk.state.status == BotStatus.HALTED_DRAWDOWN
    assert risk.is_halted


def test_halted_state_blocks_pre_trade(risk):
    risk.update_equity(9600.0)  # halts bot
    allowed, reason = risk.check_pre_trade(1000.0, 10000.0, 0.0)
    assert not allowed
    assert "halted" in reason.lower()


def test_within_limit_does_not_halt(risk):
    risk.update_equity(9800.0)  # -2%, within 3% limit
    assert not risk.is_halted
    assert risk.state.status == BotStatus.RUNNING


def test_peak_equity_tracked(risk):
    risk.update_equity(11000.0)
    assert risk.state.peak_equity == 11000.0
    risk.update_equity(10500.0)
    assert risk.state.peak_equity == 11000.0


def test_pre_trade_passes_within_limits(risk):
    allowed, reason = risk.check_pre_trade(1000.0, 10000.0, 0.0)
    assert allowed


def test_pre_trade_blocks_oversized_position(risk):
    allowed, reason = risk.check_pre_trade(3000.0, 10000.0, 0.0)  # 30% > 20%
    assert not allowed


def test_pre_trade_blocks_excess_exchange_exposure(risk):
    allowed, reason = risk.check_pre_trade(2000.0, 10000.0, 4000.0)  # 60% > 50%
    assert not allowed
