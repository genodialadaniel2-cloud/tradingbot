from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

import signal_bot


@dataclass
class _FakeCRT:
    timeframe: str
    scenario: str
    candle_close_time: int


@dataclass
class _FakeCombinedSignal:
    symbol: str
    crt: _FakeCRT


def _fake_exchange():
    exchange = MagicMock()
    exchange.fetch_time.return_value = 1_000_000
    return exchange


def test_failed_send_is_not_marked_alerted_and_does_not_block_remaining_signals():
    ok_signal = _FakeCombinedSignal("BTC/USDT:USDT", _FakeCRT("1h", "bearish", 1_000))
    fails_signal = _FakeCombinedSignal("ETH/USDT:USDT", _FakeCRT("1h", "bearish", 2_000))

    with (
        patch("signal_bot.ccxt") as mock_ccxt,
        patch("signal_bot.build_rsi_zone_snapshot", return_value=[1, 2, 3]),
        patch("signal_bot.find_combined_signals", return_value=[fails_signal, ok_signal]),
        patch("signal_bot.format_combined_signal_message", return_value="msg"),
        patch("signal_bot.send_message", side_effect=[Exception("network blip"), None]) as mock_send,
        patch("signal_bot.mark_alerted") as mock_mark,
        patch("signal_bot.log_signal") as mock_log_signal,
        patch("signal_bot.log_heartbeat") as mock_heartbeat,
    ):
        setattr(mock_ccxt, signal_bot.EXCHANGE_ID, lambda *a, **k: _fake_exchange())
        signal_bot.run_once()

    assert mock_send.call_count == 2
    # Only the successfully-sent signal gets marked alerted / logged.
    mock_mark.assert_called_once()
    marked_key_call = mock_mark.call_args[0]
    assert marked_key_call[1] == 1_000  # ok_signal's candle_close_time
    mock_log_signal.assert_called_once()
    mock_heartbeat.assert_called_once_with(scanned=3, signals_found=2, signals_sent=1, errors=1)


def test_all_sends_succeed_all_get_marked():
    a = _FakeCombinedSignal("BTC/USDT:USDT", _FakeCRT("1h", "bearish", 1_000))
    b = _FakeCombinedSignal("ETH/USDT:USDT", _FakeCRT("4h", "bullish", 2_000))

    with (
        patch("signal_bot.ccxt") as mock_ccxt,
        patch("signal_bot.build_rsi_zone_snapshot", return_value=[1]),
        patch("signal_bot.find_combined_signals", return_value=[a, b]),
        patch("signal_bot.format_combined_signal_message", return_value="msg"),
        patch("signal_bot.send_message") as mock_send,
        patch("signal_bot.mark_alerted") as mock_mark,
        patch("signal_bot.log_signal"),
        patch("signal_bot.log_heartbeat") as mock_heartbeat,
    ):
        setattr(mock_ccxt, signal_bot.EXCHANGE_ID, lambda *a, **k: _fake_exchange())
        signal_bot.run_once()

    assert mock_send.call_count == 2
    assert mock_mark.call_count == 2
    mock_heartbeat.assert_called_once_with(scanned=1, signals_found=2, signals_sent=2, errors=0)


def test_main_survives_run_once_exception_and_keeps_looping(monkeypatch):
    monkeypatch.setattr(signal_bot, "run_once", MagicMock(side_effect=RuntimeError("boom")))
    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise StopIteration  # break out of the infinite loop after one iteration

    monkeypatch.setattr(signal_bot.time, "sleep", fake_sleep)

    with pytest.raises(StopIteration):
        signal_bot.main()

    # Reaching time.sleep at all proves run_once's exception was caught,
    # not propagated -- the bot did not crash on the first bad cycle.
    assert sleep_calls == [signal_bot.POLL_SECONDS]
