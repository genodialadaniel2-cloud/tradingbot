"""
Phase 2 features across three hypotheses (v1 funding-extreme reversion, v2
volatility-compression breakout, v3 liquidity-regime overshoot reversion) --
only what each HYPOTHESIS.md iteration needed at the time it was written, not
a general indicator library.

All are trailing/backward-looking only (a value at row i is computed from
rows <= i, never from rows > i), except `is_low_liquidity_window`, which
depends only on a bar's own timestamp and needs no history at all -- neither
introduces lookahead when used in the Phase 3 event-driven backtest.
"""

import numpy as np
import pandas as pd

FUNDING_PRINTS_PER_DAY = 3  # Binance perp funding settles every 8h
TRAILING_WINDOW_DAYS = 90
TRAILING_WINDOW_PRINTS = FUNDING_PRINTS_PER_DAY * TRAILING_WINDOW_DAYS  # 270


def funding_zscore(funding_rate: pd.Series, window: int = TRAILING_WINDOW_PRINTS, min_periods: int = 30) -> pd.Series:
    """Trailing window z-score of each funding print vs. its own history (population std, inclusive of itself)."""
    roll = funding_rate.rolling(window=window, min_periods=min_periods)
    mean = roll.mean()
    std = roll.std(ddof=0)
    return (funding_rate - mean) / std


def funding_percentile(funding_rate: pd.Series, window: int = TRAILING_WINDOW_PRINTS, min_periods: int = 30) -> pd.Series:
    """Trailing window percentile rank (0-1) of each funding print vs. its own history, inclusive of itself."""

    def _pct_rank(x: np.ndarray) -> float:
        return float((x <= x[-1]).mean())

    return funding_rate.rolling(window=window, min_periods=min_periods).apply(_pct_rank, raw=True)


VOL_PERCENTILE_WINDOW_HOURS = 30 * 24  # 30-day trailing window on 1H bars, for v2's compression filter


def rolling_prior_range(high: pd.Series, low: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """
    Trailing N-hour high/low computed from the N bars strictly BEFORE the
    current one (shift(1) before rolling) -- a bar's own high/low must never
    be part of the range it's being tested for breaking out of, or every bar
    would trivially "break out" of a range that includes itself.
    """
    prior_high = high.shift(1).rolling(window=window, min_periods=window).max()
    prior_low = low.shift(1).rolling(window=window, min_periods=window).min()
    return prior_high, prior_low


def volatility_percentile(atr_series: pd.Series, close: pd.Series, window: int = VOL_PERCENTILE_WINDOW_HOURS, min_periods: int = 168) -> pd.Series:
    """Trailing-window percentile rank (0-1) of ATR-as-%-of-price vs. its own history, inclusive of itself."""
    atr_pct = atr_series / close

    def _pct_rank(x: np.ndarray) -> float:
        return float((x <= x[-1]).mean())

    return atr_pct.rolling(window=window, min_periods=min_periods).apply(_pct_rank, raw=True)


LIQUIDITY_WINDOW_HOURS = 30 * 24  # 30-day trailing window on 1H bars, same horizon as v2's vol percentile, for v3's move-magnitude filter


def is_low_liquidity_window(datetime: pd.Series) -> pd.Series:
    """
    True for bars in the Asian session (00:00-08:00 UTC) or on a weekend
    (Saturday/Sunday, UTC) -- a fixed calendar definition derived only from
    the bar's own timestamp, so it carries zero lookahead risk by
    construction (unlike a trailing statistic, it needs no warmup either).
    """
    dt = pd.to_datetime(datetime, utc=True)
    is_asian_session = dt.dt.hour < 8
    is_weekend = dt.dt.dayofweek >= 5  # pandas: 5=Saturday, 6=Sunday
    return is_asian_session | is_weekend


def abs_return_percentile(close: pd.Series, window: int = LIQUIDITY_WINDOW_HOURS, min_periods: int = 168) -> pd.Series:
    """Trailing-window percentile rank (0-1) of |1-bar return| vs. its own history, inclusive of itself."""
    abs_return = close.pct_change().abs()

    def _pct_rank(x: np.ndarray) -> float:
        return float((x <= x[-1]).mean())

    return abs_return.rolling(window=window, min_periods=min_periods).apply(_pct_rank, raw=True)


def trailing_return(close: pd.Series, k: int) -> pd.Series:
    """Cumulative return over the trailing k bars ending at the current bar (close[t]/close[t-k] - 1). NaN for the first k rows (no lookahead: depends only on close[t] and close[t-k])."""
    return close.pct_change(periods=k)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range, Wilder's smoothing (matches ta-lib's ATR)."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_values = tr.copy()
    atr_values.iloc[:period] = np.nan
    # Wilder's smoothing: first value is a simple mean of the first `period` TRs,
    # then each subsequent value is (prev_atr * (period-1) + tr) / period.
    first_atr = tr.iloc[1 : period + 1].mean()  # tr.iloc[0] is NaN (no prev_close)
    atr_values.iloc[period] = first_atr
    for i in range(period + 1, len(tr)):
        atr_values.iloc[i] = (atr_values.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period
    return atr_values


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index, Wilder's smoothing (matches ta-lib's RSI).

    Returns an all-NaN series (rather than raising) if there's not enough
    history for even one Wilder average -- a caller-side length check
    shouldn't be required for this function to behave safely."""
    if len(close) <= period:
        return pd.Series(np.nan, index=close.index)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.copy()
    avg_loss = loss.copy()
    avg_gain.iloc[: period + 1] = np.nan
    avg_loss.iloc[: period + 1] = np.nan

    # Wilder's smoothing: first value is a simple mean of the first `period`
    # gains/losses (indices 1..period, since delta.iloc[0] is NaN), then each
    # subsequent value is (prev_avg * (period-1) + current) / period.
    avg_gain.iloc[period] = gain.iloc[1 : period + 1].mean()
    avg_loss.iloc[period] = loss.iloc[1 : period + 1].mean()
    for i in range(period + 1, len(close)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss
    rsi_values = 100 - (100 / (1 + rs))
    rsi_values[avg_loss == 0] = 100.0
    # A perfectly flat market (avg_gain==0 AND avg_loss==0) is 0/0 = NaN,
    # caught by the avg_loss==0 rule above and wrongly set to 100 (maximally
    # "overbought") -- it should be neutral, since nothing moved at all.
    rsi_values[(avg_gain == 0) & (avg_loss == 0)] = 50.0
    return rsi_values


ANOMALY_MOVE_THRESHOLD = 0.30  # flag a candle that moved this much intrabar from its open


def is_anomalous_candle(open_: float, high: float, low: float, threshold: float = ANOMALY_MOVE_THRESHOLD) -> bool:
    """Flags a single candle too extreme to trust as normal price action --
    typically a thin-liquidity spike (or wash-traded volume) on one coin on
    one exchange, not something a broader index price would show the same
    way. Used both to drop a symbol from the live RSI universe
    (features/rsi_heatmap.py) and to skip an individual CRT trigger candle
    (features/crt.py) rather than alert on it."""
    if open_ == 0:
        return False
    return max(abs(high / open_ - 1), abs(low / open_ - 1)) > threshold
