import pandas as pd
import pytest

from features.crt import BEARISH, BULLISH, detect_crt, find_crt_events


def _candles(candle_1: dict, candle_2: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"timestamp": 1_000, "high": candle_1["high"], "low": candle_1["low"], "close": candle_1["close"]},
            {"timestamp": 2_000, "high": candle_2["high"], "low": candle_2["low"], "close": candle_2["close"]},
        ]
    )


def _series(*candles: dict) -> pd.DataFrame:
    """Multi-candle series (with 'open', unlike _candles) for find_crt_events,
    which needs it for the per-trigger-candle anomaly check."""
    return pd.DataFrame(
        [
            {
                "timestamp": 1_000 * (i + 1),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
            }
            for i, c in enumerate(candles)
        ]
    )


def test_bearish_crt_confirmed_sweep_high_close_back_inside():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 112, "low": 104, "close": 106},  # breaks 110, closes inside [100,110]
    )
    event = detect_crt(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH)
    assert event is not None
    assert event.scenario == BEARISH
    assert event.range_low == 100 and event.range_high == 110
    assert event.sweep_level == 110
    assert event.candle_close_time == 2_000


def test_bearish_crt_not_confirmed_when_close_stays_outside_range():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 112, "low": 111, "close": 111.5},  # breaks high but closes above range
    )
    assert detect_crt(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH) is None


def test_bearish_crt_not_confirmed_without_breaking_high():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 109, "low": 104, "close": 106},  # never breaks 110
    )
    assert detect_crt(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH) is None


def test_bullish_crt_confirmed_sweep_low_close_back_inside():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 106, "low": 95, "close": 104},  # breaks 100, closes inside [100,110]
    )
    event = detect_crt(df, symbol="ETH/USDT:USDT", timeframe="4h", scenario=BULLISH)
    assert event is not None
    assert event.scenario == BULLISH
    assert event.range_low == 100 and event.range_high == 110
    assert event.sweep_level == 100


def test_bullish_crt_not_confirmed_when_close_stays_outside_range():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 99, "low": 90, "close": 92},  # breaks low but closes below range
    )
    assert detect_crt(df, symbol="ETH/USDT:USDT", timeframe="4h", scenario=BULLISH) is None


def test_bullish_crt_not_confirmed_without_breaking_low():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 106, "low": 101, "close": 104},  # never breaks 100
    )
    assert detect_crt(df, symbol="ETH/USDT:USDT", timeframe="4h", scenario=BULLISH) is None


def test_scenario_does_not_cross_fire():
    # A bullish-shaped sweep (breaks low, closes back inside) must not
    # register as a bearish CRT, and vice versa.
    bullish_shaped = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 106, "low": 95, "close": 104},
    )
    assert detect_crt(bullish_shaped, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH) is None

    bearish_shaped = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 112, "low": 104, "close": 106},
    )
    assert detect_crt(bearish_shaped, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BULLISH) is None


def test_rejects_invalid_timeframe():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 112, "low": 104, "close": 106},
    )
    with pytest.raises(ValueError):
        detect_crt(df, symbol="BTC/USDT:USDT", timeframe="15m", scenario=BEARISH)


def test_returns_none_with_fewer_than_two_candles():
    df = _candles(
        candle_1={"high": 110, "low": 100, "close": 105},
        candle_2={"high": 112, "low": 104, "close": 106},
    ).iloc[:1]
    assert detect_crt(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH) is None


def test_find_crt_events_catches_a_confirmation_that_is_not_the_latest_pair():
    # Confirmation happens between candle 2 and 3, but candle 4 has since
    # closed -- a bot that only checked the LATEST pair (3,4) would miss
    # this entirely if a poll was delayed past that point.
    df = _series(
        {"open": 100, "high": 101, "low": 99, "close": 100},  # candle 1
        {"open": 100, "high": 110, "low": 100, "close": 105},  # candle 2 (range 100-110)
        {"open": 105, "high": 112, "low": 104, "close": 106},  # candle 3: breaks 110, closes back inside -> CRT
        {"open": 106, "high": 107, "low": 103, "close": 104},  # candle 4: unrelated, no new confirmation
    )
    events = find_crt_events(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH)
    assert len(events) == 1
    assert events[0].candle_close_time == 3_000  # fired on candle 3's close, not candle 4's


def test_find_crt_events_skips_anomalous_trigger_candle():
    # Same shape as a confirmed bearish CRT, but candle 2 (the trigger) is a
    # >30% intrabar spike from its own open -- a thin-liquidity wick, not a
    # trustworthy sweep, must not confirm.
    df = _series(
        {"open": 100, "high": 101, "low": 99, "close": 100},  # candle 1 (range 99-101)
        {"open": 100, "high": 250, "low": 100, "close": 100.5},  # candle 2: breaks 101, closes back inside, but +150% spike
    )
    events = find_crt_events(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH)
    assert events == []


def test_find_crt_events_returns_empty_when_nothing_confirms():
    df = _series(
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 100, "high": 101, "low": 99, "close": 100},
    )
    assert find_crt_events(df, symbol="BTC/USDT:USDT", timeframe="1h", scenario=BEARISH) == []
