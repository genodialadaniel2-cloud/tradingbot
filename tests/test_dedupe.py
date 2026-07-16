import monitoring.dedupe as dedupe


def test_dedupe_key_format():
    assert dedupe.dedupe_key("BTC/USDT:USDT", "1h", "bearish") == "BTC/USDT:USDT|1h|bearish"


def test_already_alerted_false_when_never_marked(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    assert dedupe.already_alerted("BTC/USDT:USDT|1h|bearish", 1_000) is False


def test_mark_then_already_alerted_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    key = dedupe.dedupe_key("BTC/USDT:USDT", "1h", "bearish")
    dedupe.mark_alerted(key, 1_000)
    assert dedupe.already_alerted(key, 1_000) is True
    assert dedupe.already_alerted(key, 2_000) is False  # a different (newer) candle is not the same alert


def test_mark_alerted_writes_atomically_no_tmp_file_left_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    dedupe.mark_alerted("k", 1_000)
    assert (tmp_path / "state.json").exists()
    assert not (tmp_path / "state.tmp").exists()


def test_corrupted_state_file_resets_to_empty_instead_of_crashing(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text("{not valid json")
    monkeypatch.setattr(dedupe, "STATE_PATH", state_path)
    assert dedupe.already_alerted("k", 1_000) is False


def test_independent_keys_do_not_collide(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    dedupe.mark_alerted(dedupe.dedupe_key("BTC/USDT:USDT", "1h", "bearish"), 1_000)
    assert dedupe.already_alerted(dedupe.dedupe_key("BTC/USDT:USDT", "4h", "bearish"), 1_000) is False
    assert dedupe.already_alerted(dedupe.dedupe_key("ETH/USDT:USDT", "1h", "bearish"), 1_000) is False


def test_handles_non_ascii_symbol_names(tmp_path, monkeypatch):
    # Binance lists non-Latin-script tickers (e.g. Chinese-character meme
    # coins) that pass the crypto-perpetual filter same as any other symbol.
    monkeypatch.setattr(dedupe, "STATE_PATH", tmp_path / "state.json")
    key = dedupe.dedupe_key("币安人生/USDT:USDT", "4h", "bearish")
    dedupe.mark_alerted(key, 1_000)
    assert dedupe.already_alerted(key, 1_000) is True
