"""Append-only log of fired signals, for later audit against what actually
happened (same discipline as CLAUDE.md's paper-trading comparison, just
without a paper-trading phase to compare against — this is the record that
would let you check it later)."""
import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent / "signals.jsonl"
HEARTBEAT_PATH = Path(__file__).parent / "heartbeat.jsonl"


def log_signal(name: str, direction: str, message: str) -> None:
    record = {
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "direction": direction,
        "message": message,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def log_heartbeat(scanned: int, signals_found: int, signals_sent: int, errors: int = 0) -> None:
    """One line per poll cycle -- the only way to tell "quiet market" apart
    from "the bot silently stopped finding anything" without this is to
    watch for the absence of any Telegram messages, which is ambiguous by
    definition. Check this file if alerts seem to have gone quiet."""
    record = {
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        "scanned": scanned,
        "signals_found": signals_found,
        "signals_sent": signals_sent,
        "errors": errors,
    }
    with HEARTBEAT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
