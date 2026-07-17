from features.rsi_heatmap import classify_rsi_zone, is_anomalous_candle


def test_classify_rsi_zone_overbought():
    assert classify_rsi_zone(70) == "OVERBOUGHT"
    assert classify_rsi_zone(85) == "OVERBOUGHT"


def test_classify_rsi_zone_oversold():
    assert classify_rsi_zone(30) == "OVERSOLD"
    assert classify_rsi_zone(15) == "OVERSOLD"


def test_classify_rsi_zone_strong():
    assert classify_rsi_zone(60) == "STRONG"
    assert classify_rsi_zone(65) == "STRONG"
    assert classify_rsi_zone(69) == "STRONG"


def test_classify_rsi_zone_weak():
    assert classify_rsi_zone(31) == "WEAK"
    assert classify_rsi_zone(50) == "WEAK"
    assert classify_rsi_zone(59) == "WEAK"


def test_classify_rsi_zone_custom_thresholds():
    assert classify_rsi_zone(65, overbought=60, oversold=40) == "OVERBOUGHT"
    assert classify_rsi_zone(35, overbought=60, oversold=40) == "OVERSOLD"
    assert classify_rsi_zone(55, overbought=70, strong=50, oversold=30) == "STRONG"


def test_is_anomalous_candle_flags_extreme_pump():
    # AKE-style candle: open 0.000189, high 0.000562 -> +197% intrabar
    assert is_anomalous_candle(open_=0.000189, high=0.000562, low=0.000185) is True


def test_is_anomalous_candle_flags_extreme_dump():
    assert is_anomalous_candle(open_=100.0, high=101.0, low=60.0) is True


def test_is_anomalous_candle_allows_normal_volatility():
    # a wide-ish but ordinary 4H candle, e.g. +/-5%
    assert is_anomalous_candle(open_=100.0, high=105.0, low=96.0) is False


def test_is_anomalous_candle_respects_custom_threshold():
    assert is_anomalous_candle(open_=100.0, high=112.0, low=99.0, threshold=0.10) is True
    assert is_anomalous_candle(open_=100.0, high=105.0, low=99.0, threshold=0.10) is False


def test_is_anomalous_candle_handles_zero_open():
    assert is_anomalous_candle(open_=0.0, high=1.0, low=0.0) is False
