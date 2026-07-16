"""Free, self-computed replacement for Coinglass's RSI Heatmap
(coinglass.com/pro/i/RsiHeatMap) — same idea (RSI per symbol across several
timeframes), computed from Binance USDⓈ-M perpetual OHLCV via ccxt instead of
Coinglass's paid API (their RSI endpoint requires a $299/mo Standard plan;
RSI itself is a standard calc, not proprietary data).
"""
import ccxt
import pandas as pd

from features.indicators import is_anomalous_candle, rsi

EXCHANGE_ID = "binanceusdm"
QUOTE = "USDT"
RSI_PERIOD = 14
OHLCV_LIMIT = 200  # comfortably more than RSI_PERIOD needs for a stable trailing value

OVERBOUGHT_THRESHOLD = 70
OVERSOLD_THRESHOLD = 30


def classify_rsi_zone(value: float, overbought: float = OVERBOUGHT_THRESHOLD, oversold: float = OVERSOLD_THRESHOLD) -> str:
    """Standard RSI zone convention: >=70 overbought, <=30 oversold, else neutral.
    NEUTRAL is not mapped to a CRT scenario (see signals/crt_rsi_signal.py's
    ZONE_TO_SCENARIO) -- only overbought/oversold tokens are checked, to cut
    alert volume down to the two zones that actually matter."""
    if value >= overbought:
        return "OVERBOUGHT"
    if value <= oversold:
        return "OVERSOLD"
    return "NEUTRAL"


def _is_crypto_perpetual(market: dict) -> bool:
    """Binance's USDⓈ-M market now also lists tokenized-equity perpetuals
    (e.g. SK Hynix, SanDisk) alongside real crypto ones, in the same
    swap/USDT market — they show up as contractType TRADIFI_PERPETUAL /
    underlyingType e.g. KR_EQUITY instead of PERPETUAL / COIN, and some rank
    high by volume. Excluded here so the heatmap stays crypto-only."""
    info = market.get("info", {})
    return info.get("contractType") == "PERPETUAL" and info.get("underlyingType") == "COIN"


def get_top_symbols(exchange: ccxt.Exchange, n: int | None = None) -> list[str]:
    """USDT-margined crypto perpetual swap symbols, sorted by 24h quote
    volume descending. n=None (default) returns the full universe (~650+
    on Binance USDⓈ-M as of 2026-07) -- deliberately not capped to the
    most-traded names: cross-checking against Coinglass's own RSI heatmap
    (2026-07-16) showed 11 of its 15 Binance-listed "overbought" coins
    (FF, BANK, ENS, RUNE, XVS, ZEN, COW, BEAMX, 0G, SLP, ME) fell outside a
    top-30-by-volume cut -- "most overbought/oversold right now" doesn't
    correlate with "highest volume." Pass n to cap it for a faster/smaller
    scan if ever needed."""
    tickers = exchange.fetch_tickers()
    perp_tickers = [
        t
        for symbol, t in tickers.items()
        if exchange.markets.get(symbol, {}).get("swap")
        and exchange.markets[symbol].get("quote") == QUOTE
        and _is_crypto_perpetual(exchange.markets[symbol])
        and t.get("quoteVolume") is not None
    ]
    if not perp_tickers:
        # _is_crypto_perpetual depends on Binance's exact raw info schema
        # (contractType/underlyingType) -- if that ever changes, or this
        # runs against a different exchange, filtering would silently zero
        # out the universe. Fail loudly instead of scanning nothing forever.
        raise RuntimeError(
            f"get_top_symbols found zero crypto perpetual symbols on {exchange.id} -- "
            "check whether Binance's market info schema (contractType/underlyingType) changed."
        )
    perp_tickers.sort(key=lambda t: t["quoteVolume"], reverse=True)
    symbols = [t["symbol"] for t in perp_tickers]
    return symbols if n is None else symbols[:n]


def _fetch_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int = OHLCV_LIMIT) -> list:
    """Includes the still-forming (not yet closed) candle deliberately --
    verified against Coinglass's own RSI heatmap on 20 real symbols
    (2026-07-16): including it matched Coinglass within ~0.02-0.8 RSI
    points (residual is just the few minutes of price drift between their
    snapshot and this fetch); excluding it was consistently 5-15 points
    lower. Coinglass's heatmap is a live tool, not a closed-bar one -- this
    module intentionally mirrors that. CRT detection (features/crt.py, via
    data/live_fetch.py) is the opposite: it strictly needs closed candles,
    since "closes back inside the range" is only meaningful for a candle
    that has actually finished."""
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def _latest_rsi_and_anomaly(exchange: ccxt.Exchange, symbol: str, timeframe: str, period: int) -> tuple[float | None, bool]:
    rows = _fetch_ohlcv(exchange, symbol, timeframe)
    if len(rows) <= period:
        return None, False
    last_open, last_high, last_low = rows[-1][1], rows[-1][2], rows[-1][3]
    anomalous = is_anomalous_candle(last_open, last_high, last_low)
    close = pd.Series([r[4] for r in rows])
    value = rsi(close, period=period).iloc[-1]
    value = None if pd.isna(value) else float(value)
    return value, anomalous


def build_rsi_zone_snapshot(
    n_symbols: int | None = None,
    timeframe: str = "4h",
    period: int = RSI_PERIOD,
    exchange: ccxt.Exchange | None = None,
) -> pd.DataFrame:
    """symbol, rsi, zone for n coins (default: the full ~650+ symbol
    universe, see get_top_symbols) on a single timeframe -- one exchange
    call per symbol, ~90s for the full universe at time of writing, well
    within an hourly poll. Symbols with an anomalous most-recent candle
    (see is_anomalous_candle) are dropped from the universe rather than
    assigned a zone.

    Pass `exchange` to reuse a caller-provided instance (e.g. so a whole
    signal_bot.py poll cycle shares one rate limiter instead of each stage
    creating its own uncoordinated one) -- if omitted, creates its own."""
    if exchange is None:
        exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
    exchange.load_markets()
    symbols = get_top_symbols(exchange, n=n_symbols)

    rows = []
    errors = 0
    for symbol in symbols:
        try:
            value, anomalous = _latest_rsi_and_anomaly(exchange, symbol, timeframe, period)
        except Exception:
            # One symbol failing (network blip, delisted mid-scan, etc.)
            # must not take down a ~650-symbol scan -- skip it and keep going.
            errors += 1
            continue
        if anomalous:
            continue
        zone = classify_rsi_zone(value) if value is not None else "UNKNOWN"
        rows.append({"symbol": symbol, "rsi": value, "zone": zone})

    if errors:
        print(f"build_rsi_zone_snapshot: {errors}/{len(symbols)} symbols failed and were skipped")

    return pd.DataFrame(rows)
