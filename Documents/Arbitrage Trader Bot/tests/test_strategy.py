"""Tests for funding arb strategy logic."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime

from src.strategy.funding_arb import FundingArbStrategy, Signal
from src.data.feed import FundingSnapshot


def make_snapshot(annualized_apr: float, funding_rate_8h: float = None) -> FundingSnapshot:
    if funding_rate_8h is None:
        funding_rate_8h = annualized_apr / (3 * 365 * 100)
    return FundingSnapshot(
        asset="BTC",
        timestamp=datetime.utcnow(),
        funding_rate_8h=funding_rate_8h,
        annualized_apr=annualized_apr,
        next_funding_time=None,
        spot_price=50000.0,
        perp_price=50010.0,
        basis_pct=0.02,
    )


@pytest.fixture
def strategy():
    return FundingArbStrategy(min_entry_apr=5.0, min_exit_apr=3.0)


def test_above_threshold_not_in_position_enters(strategy):
    snap = make_snapshot(10.0)
    d = strategy.evaluate(snap, currently_in_position=False)
    assert d.signal == Signal.ENTER


def test_below_threshold_not_in_position_no_trade(strategy):
    snap = make_snapshot(2.0)
    d = strategy.evaluate(snap, currently_in_position=False)
    assert d.signal == Signal.NO_TRADE


def test_in_position_above_exit_threshold_holds(strategy):
    snap = make_snapshot(4.0)
    d = strategy.evaluate(snap, currently_in_position=True)
    assert d.signal == Signal.HOLD


def test_in_position_below_exit_threshold_exits(strategy):
    snap = make_snapshot(1.0)
    d = strategy.evaluate(snap, currently_in_position=True)
    assert d.signal == Signal.EXIT


def test_negative_funding_not_in_position_no_trade(strategy):
    snap = make_snapshot(-5.0, funding_rate_8h=-0.0001)
    d = strategy.evaluate(snap, currently_in_position=False)
    assert d.signal == Signal.NO_TRADE


def test_negative_funding_in_position_exits(strategy):
    snap = make_snapshot(-5.0, funding_rate_8h=-0.0001)
    d = strategy.evaluate(snap, currently_in_position=True)
    assert d.signal == Signal.EXIT


def test_exactly_at_entry_threshold_enters(strategy):
    snap = make_snapshot(5.0)
    d = strategy.evaluate(snap, currently_in_position=False)
    assert d.signal == Signal.ENTER


def test_exactly_at_exit_threshold_holds(strategy):
    snap = make_snapshot(3.0)
    d = strategy.evaluate(snap, currently_in_position=True)
    assert d.signal == Signal.HOLD
