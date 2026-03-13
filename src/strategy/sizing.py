"""Position sizing logic."""
from dataclasses import dataclass
from typing import Optional

# Precision by asset (decimal places for quantity)
ASSET_PRECISION = {
    "BTC": 5,
    "ETH": 4,
}
DEFAULT_PRECISION = 3


@dataclass
class PositionSize:
    asset: str
    spot_qty: float
    perp_qty: float
    notional_usdt: float
    spot_symbol: str
    perp_symbol: str


def calculate_position_size(
    asset: str,
    portfolio_usdt: float,
    spot_price: float,
    max_position_pct: float,
    min_order_size: float = 10.0,
) -> Optional[PositionSize]:
    """
    Calculate position size for a delta-neutral entry.

    Returns None if the resulting notional is below min_order_size.
    """
    notional = portfolio_usdt * max_position_pct
    precision = ASSET_PRECISION.get(asset, DEFAULT_PRECISION)
    qty = round(notional / spot_price, precision)

    actual_notional = qty * spot_price

    if actual_notional < min_order_size:
        return None

    return PositionSize(
        asset=asset,
        spot_qty=qty,
        perp_qty=qty,
        notional_usdt=actual_notional,
        spot_symbol=f"{asset}/USDT",
        perp_symbol=f"{asset}/USDT:USDT",
    )
