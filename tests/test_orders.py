"""Tests for order execution."""
import pytest
from unittest.mock import MagicMock, patch
import ccxt

from src.execution.orders import OrderExecutor, SLIPPAGE, TAKER_FEE


@pytest.fixture
def paper_executor():
    mock_exchange = MagicMock(spec=ccxt.Exchange)
    return OrderExecutor(mock_exchange, paper_mode=True)


@pytest.fixture
def live_executor():
    mock_exchange = MagicMock(spec=ccxt.Exchange)
    return OrderExecutor(mock_exchange, paper_mode=False)


def test_paper_buy_applies_slippage_upward(paper_executor):
    result = paper_executor.buy_spot("BTC/USDT", 0.01, 50000.0)
    assert result.success
    assert result.fill_price > 50000.0
    assert abs(result.fill_price - 50000.0 * (1 + SLIPPAGE)) < 0.01
    assert result.paper


def test_paper_sell_applies_slippage_downward(paper_executor):
    result = paper_executor.sell_spot("BTC/USDT", 0.01, 50000.0)
    assert result.success
    assert result.fill_price < 50000.0
    assert abs(result.fill_price - 50000.0 * (1 - SLIPPAGE)) < 0.01
    assert result.paper


def test_paper_deducts_fees(paper_executor):
    result = paper_executor.buy_spot("BTC/USDT", 1.0, 50000.0)
    assert result.fee_usdt > 0
    expected_fee = 1.0 * result.fill_price * TAKER_FEE
    assert abs(result.fee_usdt - expected_fee) < 0.01


def test_paper_short_applies_slippage_downward(paper_executor):
    result = paper_executor.short_perp("BTC/USDT:USDT", 0.01, 50000.0)
    assert result.success
    assert result.fill_price < 50000.0


def test_live_order_failure_returns_result_not_exception(live_executor):
    live_executor.exchange.create_order.side_effect = Exception("Connection error")
    result = live_executor.buy_spot("BTC/USDT", 0.01, 50000.0)
    assert not result.success
    assert result.error != ""
    assert "Connection error" in result.error


def test_live_order_failure_no_raise(live_executor):
    live_executor.exchange.create_order.side_effect = ccxt.NetworkError("timeout")
    # Should not raise
    result = live_executor.short_perp("BTC/USDT:USDT", 0.01, 50000.0)
    assert not result.success
