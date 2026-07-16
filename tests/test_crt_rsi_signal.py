from unittest.mock import MagicMock, patch

import pandas as pd

import monitoring.dedupe as dedupe
from signals.crt_rsi_signal import MAX_SIGNAL_AGE_MS, find_combined_signals


def _bearish_crt_df():
    # candle 1 range [100,110], candle 2 breaks 110 and closes back inside -> confirms bearish
    return pd.DataFrame(
        [
            {"timestamp": 1_000, "open": 105, "high": 110, "low": 100, "close": 105},
            {"timestamp": 2_000, "open": 105, "high": 112, "low": 104, "close": 106},
        ]
    )


def _no_crt_df():
    return pd.DataFrame(
        [
            {"timestamp": 1_000, "open": 105, "high": 110, "low": 100, "close": 105},
            {"timestamp": 2_000, "open": 105, "high": 106, "low": 104, "close": 106},
        ]
    )


def test_overbought_zone_only_checked_for_bearish_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"}])

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_bearish_crt_df()):
        results = find_combined_signals(snapshot, now_ms=3_000)

    assert len(results) == 2  # confirms on both 1h and 4h (same fake df returned for both)
    assert all(r.crt.scenario == "bearish" for r in results)


def test_oversold_only_checked_for_bullish_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "ETH/USDT:USDT", "rsi": 20.0, "zone": "OVERSOLD"}])
    # This df is shaped as a BEARISH confirmation, so if OVERSOLD were
    # (incorrectly) checked for bearish instead of bullish, this would fire.
    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_bearish_crt_df()):
        results = find_combined_signals(snapshot)

    assert results == []


def test_neutral_zone_is_never_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 50.0, "zone": "NEUTRAL"}])

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv") as mock_fetch:
        results = find_combined_signals(snapshot)

    mock_fetch.assert_not_called()
    assert results == []


def test_unknown_zone_is_never_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": None, "zone": "UNKNOWN"}])

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv") as mock_fetch:
        results = find_combined_signals(snapshot)

    mock_fetch.assert_not_called()
    assert results == []


def test_already_alerted_candle_is_not_returned_again(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"}])

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_bearish_crt_df()):
        first = find_combined_signals(snapshot, now_ms=3_000)
        assert len(first) == 2
        # Simulate signal_bot.py having successfully delivered and marked these.
        for cs in first:
            dedupe.mark_alerted(
                dedupe.dedupe_key(cs.symbol, cs.crt.timeframe, cs.crt.scenario), cs.crt.candle_close_time
            )
        second = find_combined_signals(snapshot, now_ms=3_000)

    assert second == []


def test_does_not_mark_alerted_itself(tmp_path, monkeypatch):
    # find_combined_signals must only READ dedupe state, never WRITE it --
    # that responsibility belongs to the caller, only after a confirmed send.
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"}])

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_bearish_crt_df()):
        first = find_combined_signals(snapshot, now_ms=3_000)
        assert len(first) == 2
        second = find_combined_signals(snapshot, now_ms=3_000)

    assert len(second) == 2  # unchanged -- nothing was marked alerted by find_combined_signals itself


def test_one_symbol_fetch_failure_does_not_break_the_whole_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame(
        [
            {"symbol": "BROKEN/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"},
            {"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"},
        ]
    )

    def fake_fetch(exchange, symbol, timeframe, limit, now_ms=None):
        if symbol == "BROKEN/USDT:USDT":
            raise ConnectionError("simulated network blip")
        return _bearish_crt_df()

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", side_effect=fake_fetch):
        results = find_combined_signals(snapshot, now_ms=3_000)

    assert len(results) == 2  # both 1h and 4h confirmed for BTC despite BROKEN failing
    assert all(r.symbol == "BTC/USDT:USDT" for r in results)


def test_stale_confirmation_is_not_alerted_on_cold_start(tmp_path, monkeypatch):
    # candle_close_time=2000 (ms). If "now" is far beyond MAX_SIGNAL_AGE_MS
    # past that, this must not fire -- otherwise a cold start (empty dedupe
    # state) replays old history as if it just happened. Verified live:
    # without this, a real full-universe first run produced 2440 "signals".
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"}])
    stale_now_ms = 2_000 + MAX_SIGNAL_AGE_MS + 1

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_bearish_crt_df()):
        results = find_combined_signals(snapshot, now_ms=stale_now_ms)

    assert results == []


def test_fresh_confirmation_within_max_age_is_still_alerted(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"}])
    fresh_now_ms = 2_000 + 1_000  # well within MAX_SIGNAL_AGE_MS

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_bearish_crt_df()):
        results = find_combined_signals(snapshot, now_ms=fresh_now_ms)

    assert len(results) == 2


def test_no_crt_confirmation_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    snapshot = pd.DataFrame([{"symbol": "BTC/USDT:USDT", "rsi": 75.0, "zone": "OVERBOUGHT"}])

    with patch("signals.crt_rsi_signal.fetch_latest_ohlcv", return_value=_no_crt_df()):
        results = find_combined_signals(snapshot)

    assert results == []
