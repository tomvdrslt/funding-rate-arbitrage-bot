"""Strategy logic for funding rate arbitrage."""
from dataclasses import dataclass
from enum import Enum

from src.data.feed import FundingSnapshot


class Signal(Enum):
    ENTER = "ENTER"
    HOLD = "HOLD"
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


@dataclass
class StrategyDecision:
    signal: Signal
    asset: str
    annualized_apr: float
    reason: str


class FundingArbStrategy:
    def __init__(self, min_entry_apr: float, min_exit_apr: float):
        self.min_entry_apr = min_entry_apr
        self.min_exit_apr = min_exit_apr

    def evaluate(self, snapshot: FundingSnapshot, currently_in_position: bool) -> StrategyDecision:
        apr = snapshot.annualized_apr
        asset = snapshot.asset

        if snapshot.funding_rate_8h < 0 and currently_in_position:
            return StrategyDecision(
                signal=Signal.EXIT,
                asset=asset,
                annualized_apr=apr,
                reason=f"Negative funding ({apr:.2f}% APR) — would start paying",
            )

        if snapshot.funding_rate_8h < 0 and not currently_in_position:
            return StrategyDecision(
                signal=Signal.NO_TRADE,
                asset=asset,
                annualized_apr=apr,
                reason=f"Negative funding ({apr:.2f}% APR) — sitting out",
            )

        if currently_in_position and apr < self.min_exit_apr:
            return StrategyDecision(
                signal=Signal.EXIT,
                asset=asset,
                annualized_apr=apr,
                reason=f"APR {apr:.2f}% below exit threshold {self.min_exit_apr}%",
            )

        if not currently_in_position and apr >= self.min_entry_apr:
            return StrategyDecision(
                signal=Signal.ENTER,
                asset=asset,
                annualized_apr=apr,
                reason=f"APR {apr:.2f}% above entry threshold {self.min_entry_apr}%",
            )

        if currently_in_position and apr >= self.min_exit_apr:
            return StrategyDecision(
                signal=Signal.HOLD,
                asset=asset,
                annualized_apr=apr,
                reason=f"APR {apr:.2f}% above exit threshold — holding",
            )

        return StrategyDecision(
            signal=Signal.NO_TRADE,
            asset=asset,
            annualized_apr=apr,
            reason=f"APR {apr:.2f}% below entry threshold {self.min_entry_apr}%",
        )
