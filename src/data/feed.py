"""Live funding rate + price feed via CCXT."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import ccxt

# Exchanges where spot and futures are on the same account/instance
UNIFIED_EXCHANGES = {'bybit', 'okx', 'bitget', 'gate', 'mexc', 'htx', 'kucoin'}

# Exchanges where futures funding interval may not be 8h — scale factor: payments per day
FUNDING_INTERVALS = {
    'bybit': 3,   # 8h = 3x/day
    'okx': 3,
    'binance': 3,
    'bitget': 3,
    'gate': 3,
    'mexc': 3,
    'htx': 3,
    'kraken': 3,
    'kucoin': 3,
}


@dataclass
class FundingSnapshot:
    asset: str
    timestamp: datetime
    funding_rate_8h: float
    annualized_apr: float
    next_funding_time: Optional[datetime]
    spot_price: float
    perp_price: float
    basis_pct: float


def build_exchange(config) -> ccxt.Exchange:
    """Build and return a CCXT futures exchange instance.
    For split exchanges (e.g. Kraken), this returns the futures sub-exchange (krakenfutures).
    """
    futures_name = config.exchange.futures_name.lower()
    exchange_cls = getattr(ccxt, futures_name)
    exchange = exchange_cls({
        'apiKey': config.exchange.api_key,
        'secret': config.exchange.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
        },
    })
    if config.exchange.testnet:
        _try_sandbox(exchange)
    return exchange


def build_spot_exchange(config) -> ccxt.Exchange:
    """Build a spot-mode exchange instance.
    For split exchanges (e.g. Kraken), this is a separate instance from the futures exchange.
    """
    exchange_name = config.exchange.name.lower()
    exchange_cls = getattr(ccxt, exchange_name)
    exchange = exchange_cls({
        'apiKey': config.exchange.api_key,
        'secret': config.exchange.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
        },
    })
    if config.exchange.testnet:
        _try_sandbox(exchange)
    return exchange


def _try_sandbox(exchange: ccxt.Exchange) -> None:
    """Enable sandbox mode if the exchange supports it, otherwise skip silently."""
    try:
        exchange.set_sandbox_mode(True)
    except ccxt.NotSupported:
        pass


def get_symbols(asset: str, quote: str) -> tuple:
    """Return (spot_symbol, perp_symbol) for the given asset and quote currency."""
    return f"{asset}/{quote}", f"{asset}/{quote}:{quote}"


class MarketFeed:
    def __init__(self, exchange: ccxt.Exchange, spot_exchange: ccxt.Exchange = None,
                 quote_currency: str = "USDT"):
        self.exchange = exchange
        self.spot_exchange = spot_exchange or exchange
        self.quote_currency = quote_currency

    def get_funding_snapshot(self, asset: str) -> FundingSnapshot:
        """Fetch current funding rate and prices for an asset."""
        spot_symbol, perp_symbol = get_symbols(asset, self.quote_currency)

        # Fetch funding rate
        funding_info = self.exchange.fetch_funding_rate(perp_symbol)
        funding_rate_8h = float(funding_info.get('fundingRate', 0))
        next_funding_ts = funding_info.get('fundingDatetime')
        next_funding_time = None
        if next_funding_ts:
            if isinstance(next_funding_ts, str):
                next_funding_time = datetime.fromisoformat(next_funding_ts.replace('Z', '+00:00'))
            elif isinstance(next_funding_ts, (int, float)):
                next_funding_time = datetime.utcfromtimestamp(next_funding_ts / 1000)

        # Fetch spot price using the spot exchange instance
        spot_ticker = self.spot_exchange.fetch_ticker(spot_symbol)
        spot_price = float(spot_ticker['last'])

        # Fetch perp price
        perp_ticker = self.exchange.fetch_ticker(perp_symbol)
        perp_price = float(perp_ticker['last'])

        basis_pct = ((perp_price - spot_price) / spot_price) * 100
        annualized_apr = funding_rate_8h * 3 * 365 * 100

        return FundingSnapshot(
            asset=asset,
            timestamp=datetime.utcnow(),
            funding_rate_8h=funding_rate_8h,
            annualized_apr=annualized_apr,
            next_funding_time=next_funding_time,
            spot_price=spot_price,
            perp_price=perp_price,
            basis_pct=basis_pct,
        )
