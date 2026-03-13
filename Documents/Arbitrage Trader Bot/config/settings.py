from dataclasses import dataclass, field
from typing import List
import os
from dotenv import load_dotenv

# Exchanges that use a separate CCXT instance for futures
SPLIT_EXCHANGES = {
    'kraken': 'krakenfutures',
}

@dataclass
class ExchangeConfig:
    name: str
    api_key: str
    api_secret: str
    testnet: bool
    futures_name: str = ""  # Set automatically for split exchanges (e.g. kraken → krakenfutures)

    def __post_init__(self):
        if not self.futures_name:
            self.futures_name = SPLIT_EXCHANGES.get(self.name, self.name)

@dataclass
class RiskConfig:
    max_position_pct: float
    max_exchange_exposure_pct: float
    min_funding_entry_apr: float
    min_funding_exit_apr: float
    daily_loss_limit_pct: float
    total_drawdown_limit_pct: float
    delta_rebalance_threshold: float

@dataclass
class BotConfig:
    exchange: ExchangeConfig
    risk: RiskConfig
    assets: List[str]
    funding_poll_interval_s: int
    paper_mode: bool

def load_config(paper_mode: bool = True) -> BotConfig:
    # Load from config/.env if it exists, else from environment
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(env_path)

    exchange = ExchangeConfig(
        name=os.getenv('EXCHANGE', 'binance'),
        api_key=os.getenv('API_KEY', ''),
        api_secret=os.getenv('API_SECRET', ''),
        testnet=os.getenv('USE_TESTNET', 'true').lower() == 'true',
    )

    risk = RiskConfig(
        max_position_pct=float(os.getenv('MAX_POSITION_PCT', '0.20')),
        max_exchange_exposure_pct=float(os.getenv('MAX_EXCHANGE_EXPOSURE_PCT', '0.50')),
        min_funding_entry_apr=float(os.getenv('MIN_FUNDING_ENTRY_APR', '5.0')),
        min_funding_exit_apr=float(os.getenv('MIN_FUNDING_EXIT_APR', '3.0')),
        daily_loss_limit_pct=float(os.getenv('DAILY_LOSS_LIMIT_PCT', '3.0')),
        total_drawdown_limit_pct=float(os.getenv('TOTAL_DRAWDOWN_LIMIT_PCT', '15.0')),
        delta_rebalance_threshold=float(os.getenv('DELTA_REBALANCE_THRESHOLD', '2.0')),
    )

    assets_str = os.getenv('ASSETS', 'BTC')
    assets = [a.strip() for a in assets_str.split(',')]

    return BotConfig(
        exchange=exchange,
        risk=risk,
        assets=assets,
        funding_poll_interval_s=int(os.getenv('FUNDING_POLL_INTERVAL_S', '3600')),
        paper_mode=paper_mode,
    )
