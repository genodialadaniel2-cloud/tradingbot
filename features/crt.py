"""CRT (Candle Range Theory) detection -- a two-candle liquidity-sweep-and-
reclaim pattern. Strictly 1H and 4H timeframes only, per spec.

Candle 1 ("previous candle") defines a range [low_1, high_1]. Candle 2
("second candle") is the next candle after it.

Bearish CRT: candle 2's high breaks above candle 1's high, but candle 2
closes back inside candle 1's range. Target zone = candle 1's range (the
expected move is back down through it).

Bullish CRT: candle 2's low breaks below candle 1's low, but candle 2
closes back inside candle 1's range. Target zone = candle 1's range (the
expected move is back up through it).

Both candles must be CLOSED bars -- never evaluate this against a
still-forming candle (see data/live_fetch.py's forming-candle trim).
"""
from dataclasses import dataclass

import pandas as pd

from features.indicators import is_anomalous_candle

VALID_TIMEFRAMES = ("1h", "4h")
BEARISH = "bearish"
BULLISH = "bullish"


@dataclass
class CRTEvent:
    symbol: str
    timeframe: str
    scenario: str  # BEARISH | BULLISH
    range_low: float
    range_high: float
    sweep_level: float
    close_price: float
    candle_close_time: int  # candle 2's timestamp (ms) -- identifies which candle this fired on


def detect_crt(df: pd.DataFrame, symbol: str, timeframe: str, scenario: str) -> CRTEvent | None:
    """df: closed candles only, oldest-to-newest, with columns
    timestamp/high/low/close. The last row is candle 2, the second-to-last
    is candle 1.
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"CRT is only defined for {VALID_TIMEFRAMES}, got {timeframe!r}")
    if scenario not in (BEARISH, BULLISH):
        raise ValueError(f"scenario must be {BEARISH!r} or {BULLISH!r}, got {scenario!r}")
    if len(df) < 2:
        return None

    candle_1 = df.iloc[-2]
    candle_2 = df.iloc[-1]
    range_low, range_high = candle_1["low"], candle_1["high"]
    closes_inside_range = range_low <= candle_2["close"] <= range_high

    if scenario == BEARISH:
        breaks_level = candle_1["high"]
        confirmed = candle_2["high"] > breaks_level and closes_inside_range
    else:
        breaks_level = candle_1["low"]
        confirmed = candle_2["low"] < breaks_level and closes_inside_range

    if not confirmed:
        return None

    return CRTEvent(
        symbol=symbol,
        timeframe=timeframe,
        scenario=scenario,
        range_low=range_low,
        range_high=range_high,
        sweep_level=breaks_level,
        close_price=candle_2["close"],
        candle_close_time=int(candle_2["timestamp"]),
    )


def find_crt_events(df: pd.DataFrame, symbol: str, timeframe: str, scenario: str) -> list[CRTEvent]:
    """Scans every adjacent closed-candle pair in df, not just the last one
    -- checking only the latest pair means a confirmation that occurred a
    candle or two ago is permanently lost if a poll is ever delayed, the
    bot restarts, or a cycle is skipped, since the next poll only ever
    looks at what's newest. df should cover more than 2 candles (see
    signals/crt_rsi_signal.py's CRT_FETCH_LIMIT) so a missed poll or two
    still gets caught.

    Each pair's trigger candle (candle 2, the one whose sweep-and-reclaim
    would confirm the pattern) is checked with is_anomalous_candle and
    skipped if it fails -- a thin-liquidity spike shouldn't confirm a
    signal just because it happened to also satisfy the CRT geometry.
    """
    events = []
    for i in range(1, len(df)):
        pair = df.iloc[i - 1 : i + 1]
        event = detect_crt(pair, symbol=symbol, timeframe=timeframe, scenario=scenario)
        if event is None:
            continue
        candle_2 = df.iloc[i]
        if is_anomalous_candle(candle_2["open"], candle_2["high"], candle_2["low"]):
            continue
        events.append(event)
    return events
