"""Tracks the last candle alerted per (symbol, timeframe, scenario) so a
confirmed CRT doesn't get re-sent every poll cycle until a new candle closes
-- signal_bot.py polls more often than 4H candles close, and a confirmed
CRT stays confirmed (same two closed candles) across multiple polls within
that window.
"""
import json
import os
from pathlib import Path

STATE_PATH = Path(__file__).parent / "crt_alert_state.json"


def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A crash mid-write (see _save's atomic replace, added after this
        # was hit) could leave a truncated file. Treat as empty rather than
        # crash the bot -- worst case is a handful of candles get re-alerted
        # once, which is far better than the bot dying on every poll.
        print(f"monitoring/dedupe.py: {STATE_PATH} is corrupted, resetting to empty state")
        return {}


def _save(state: dict) -> None:
    # Write to a temp file then atomically replace, so a crash/kill mid-write
    # can't leave a truncated/corrupt JSON file behind.
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp_path, STATE_PATH)


def dedupe_key(symbol: str, timeframe: str, scenario: str) -> str:
    """Shared key format so the read side (already_alerted, checked before
    sending) and the write side (mark_alerted, called only after a
    confirmed send) can never drift apart into two different formats."""
    return f"{symbol}|{timeframe}|{scenario}"


def already_alerted(key: str, candle_close_time: int) -> bool:
    return _load().get(key) == candle_close_time


def mark_alerted(key: str, candle_close_time: int) -> None:
    state = _load()
    state[key] = candle_close_time
    _save(state)
