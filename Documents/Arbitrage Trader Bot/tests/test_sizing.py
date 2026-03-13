"""Tests for position sizing."""
import pytest
from src.strategy.sizing import calculate_position_size, PositionSize


def test_correct_notional_calculation():
    result = calculate_position_size("BTC", 10000.0, 50000.0, 0.20)
    assert result is not None
    assert abs(result.notional_usdt - 2000.0) < 1.0  # ~2000 USDT


def test_correct_btc_quantity_rounding():
    result = calculate_position_size("BTC", 10000.0, 50000.0, 0.20)
    assert result is not None
    # 2000 / 50000 = 0.04 BTC, rounded to 5dp
    assert result.spot_qty == round(2000.0 / 50000.0, 5)


def test_correct_eth_quantity_rounding():
    result = calculate_position_size("ETH", 10000.0, 2000.0, 0.20)
    assert result is not None
    # 2000 / 2000 = 1.0 ETH, rounded to 4dp
    assert result.spot_qty == round(2000.0 / 2000.0, 4)


def test_returns_none_below_minimum():
    # Very small portfolio, high price
    result = calculate_position_size("BTC", 50.0, 50000.0, 0.20, min_order_size=10.0)
    # 50 * 0.20 = 10 USDT, qty = 10/50000 = 0.0002, actual = 0.0002 * 50000 = 10
    # With rounding to 5dp: round(0.0002, 5) = 0.0002, notional = 10 >= 10
    # This may pass — let's use a really tiny portfolio
    result2 = calculate_position_size("BTC", 10.0, 50000.0, 0.20, min_order_size=10.0)
    # 10 * 0.20 = 2 USDT, qty = 0.00004, notional = 2 < 10
    assert result2 is None


def test_symbols_are_correct():
    result = calculate_position_size("ETH", 10000.0, 2000.0, 0.20)
    assert result is not None
    assert result.spot_symbol == "ETH/USDT"
    assert result.perp_symbol == "ETH/USDT:USDT"
