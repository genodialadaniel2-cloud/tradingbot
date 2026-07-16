from unittest.mock import MagicMock

from data.live_fetch import fetch_latest_ohlcv


def _fake_exchange(rows, timeframe_seconds=3600):
    exchange = MagicMock()
    exchange.fetch_ohlcv.return_value = rows
    exchange.parse_timeframe.return_value = timeframe_seconds
    return exchange


def test_trims_still_forming_candle():
    # candle at 1_000_000ms + 3600_000ms timeframe = closes at 4_600_000ms,
    # but "now" is only 4_500_000ms -- still forming, must be dropped.
    rows = [
        [0, 100, 101, 99, 100, 10],
        [1_000_000, 100, 102, 98, 101, 10],
    ]
    exchange = _fake_exchange(rows)
    df = fetch_latest_ohlcv(exchange, symbol="BTC/USDT:USDT", timeframe="1h", now_ms=4_500_000)
    assert len(df) == 1
    assert df.iloc[-1]["timestamp"] == 0


def test_keeps_last_candle_once_actually_closed():
    rows = [
        [0, 100, 101, 99, 100, 10],
        [1_000_000, 100, 102, 98, 101, 10],
    ]
    exchange = _fake_exchange(rows)
    # now is well past candle 2's close (1_000_000 + 3_600_000)
    df = fetch_latest_ohlcv(exchange, symbol="BTC/USDT:USDT", timeframe="1h", now_ms=10_000_000)
    assert len(df) == 2
    assert df.iloc[-1]["timestamp"] == 1_000_000


def test_uses_provided_now_ms_instead_of_local_clock():
    # exchange.milliseconds() would return something wildly different from
    # now_ms -- if the function ignored now_ms and used local clock instead,
    # this candle (whose closing time we've deliberately set relative to
    # now_ms) would be trimmed incorrectly.
    rows = [[0, 100, 101, 99, 100, 10]]
    exchange = _fake_exchange(rows)
    exchange.milliseconds.return_value = 999_999_999_999  # local clock says "way in the future"
    df = fetch_latest_ohlcv(exchange, symbol="BTC/USDT:USDT", timeframe="1h", now_ms=100)
    # now_ms=100 is before this candle could have closed (0 + 3_600_000) -> still forming -> trimmed
    assert len(df) == 0


def test_falls_back_to_exchange_clock_when_now_ms_not_given():
    rows = [[0, 100, 101, 99, 100, 10]]
    exchange = _fake_exchange(rows)
    exchange.milliseconds.return_value = 10_000_000  # well past this candle's close
    df = fetch_latest_ohlcv(exchange, symbol="BTC/USDT:USDT", timeframe="1h")
    assert len(df) == 1
