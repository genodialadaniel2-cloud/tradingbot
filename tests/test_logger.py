import json

import monitoring.logger as logger


def test_log_signal_handles_non_ascii_symbol_names(tmp_path, monkeypatch):
    # Binance lists non-Latin-script tickers (e.g. Chinese-character meme
    # coins) that pass the crypto-perpetual filter same as any other
    # symbol -- logging one must not crash on Windows' default file encoding.
    log_path = tmp_path / "signals.jsonl"
    monkeypatch.setattr(logger, "LOG_PATH", log_path)

    logger.log_signal("crt_bearish", direction="bearish", message="币安人生/USDT:USDT triggered a signal")

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert "币安人生" in record["message"]


def test_log_heartbeat_writes_expected_fields(tmp_path, monkeypatch):
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    monkeypatch.setattr(logger, "HEARTBEAT_PATH", heartbeat_path)

    logger.log_heartbeat(scanned=527, signals_found=3, signals_sent=2, errors=1)

    record = json.loads(heartbeat_path.read_text(encoding="utf-8").strip())
    assert record["scanned"] == 527
    assert record["signals_found"] == 3
    assert record["signals_sent"] == 2
    assert record["errors"] == 1
