"""Latest-bars fetch for live signal evaluation.

Separate from fetch_data.py, which does the one-time historical pull +
holdout split for research/backtesting. This just grabs the most recent N
bars on demand for signal_bot.py's polling loop -- no holdout bookkeeping,
nothing gets written to data/raw or data/holdout.
"""
import ccxt
import pandas as pd

EXCHANGE_ID = "binanceusdm"
SYMBOL = "BTC/USDT:USDT"


def fetch_latest_ohlcv(
    exchange: ccxt.Exchange | None = None,
    symbol: str = SYMBOL,
    timeframe: str = "1h",
    limit: int = 500,
    now_ms: int | None = None,
) -> pd.DataFrame:
    """Pass `exchange` to reuse a caller-provided instance -- a fresh
    ccxt instance per call (the old default) means each one's rate limiter
    has no memory of the others, which stops actually limiting anything
    once this is called hundreds of times a cycle. If omitted, creates its
    own (fine for standalone/one-off use).

    Pass `now_ms` (e.g. from exchange.fetch_time(), fetched once per poll
    cycle by the caller) to judge "is the last candle still forming"
    against exchange server time instead of the local machine clock, which
    can drift (this environment measured ~5s drift already) and either
    trim a genuinely closed candle or fail to trim a forming one.
    """
    if exchange is None:
        exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    # Exchanges return the still-forming candle as the last row when its
    # window hasn't closed yet. Using it would mean a signal reacting to a
    # candle that can still change shape -- drop it so the last row is
    # always the most recent CLOSED candle.
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    reference_now_ms = now_ms if now_ms is not None else exchange.milliseconds()
    if rows and rows[-1][0] + timeframe_ms > reference_now_ms:
        rows = rows[:-1]

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df
