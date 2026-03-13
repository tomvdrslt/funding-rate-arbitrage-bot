"""Delta hedge rebalancer."""
import logging
from typing import Optional

from src.execution.orders import OrderExecutor, OrderResult

logger = logging.getLogger(__name__)


class Rebalancer:
    def __init__(self, executor: OrderExecutor, threshold_pct: float = 2.0):
        self.executor = executor
        self.threshold_pct = threshold_pct

    def check_and_rebalance(
        self,
        asset: str,
        spot_qty: float,
        spot_price: float,
        perp_qty: float,
        perp_price: float,
    ) -> Optional[OrderResult]:
        """
        If the notional drift between spot and perp legs exceeds threshold,
        place a corrective order to bring back to equal notional.
        Returns an OrderResult if a rebalance was executed, else None.
        """
        spot_notional = spot_qty * spot_price
        perp_notional = perp_qty * perp_price

        if spot_notional == 0:
            return None

        drift_pct = abs(spot_notional - perp_notional) / spot_notional * 100

        if drift_pct <= self.threshold_pct:
            return None

        logger.info(
            f"Rebalancing {asset}: spot_notional={spot_notional:.2f}, "
            f"perp_notional={perp_notional:.2f}, drift={drift_pct:.2f}%"
        )

        # Bring perp notional in line with spot notional
        target_perp_qty = spot_notional / perp_price
        delta_qty = abs(target_perp_qty - perp_qty)
        perp_symbol = f"{asset}/USDT:USDT"

        if target_perp_qty > perp_qty:
            # Need more short — sell more perp
            result = self.executor.short_perp(perp_symbol, delta_qty, perp_price)
        else:
            # Need less short — close some perp
            result = self.executor.close_perp_short(perp_symbol, delta_qty, perp_price)

        if result.success:
            logger.info(f"Rebalance complete for {asset}")
        else:
            logger.error(f"Rebalance failed for {asset}: {result.error}")

        return result
