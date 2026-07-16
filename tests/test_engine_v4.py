import pandas as pd

from backtest.costs import CostModel
from backtest.engine_v4 import V4Params, run_backtest


def _make_bars(closes, atr_val=1.0):
    n = len(closes)
    dt = pd.date_range(pd.Timestamp("2024-01-01", tz="UTC"), periods=n, freq="D")
    close = pd.Series(closes, dtype=float)
    df = pd.DataFrame(
        {
            "datetime": dt,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "atr_14": [atr_val] * n,
            "funding_sum": [0.0] * n,
        }
    )
    return df


def test_long_entry_flip_to_short_records_profitable_long():
    closes = [100, 100, 100, 100, 100, 105, 110, 115, 120, 125, 130, 115, 115]
    df = _make_bars(closes)
    params = V4Params(lookback_days=1, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "long"
    assert t["exit_reason"] == "signal_flip"
    assert t["entry_price"] == 110  # open of bar 6, the day after the first positive trend_return
    assert t["exit_price"] == 115  # open of bar 12, the day after trend_return flips negative
    assert t["gross_pnl_pct"] > 0


def test_short_entry_flip_to_long_records_profitable_short():
    closes = [100, 100, 100, 100, 100, 95, 90, 85, 80, 75, 70, 85, 85]
    df = _make_bars(closes)
    params = V4Params(lookback_days=1, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "short"
    assert t["exit_reason"] == "signal_flip"
    assert t["gross_pnl_pct"] > 0


def test_atr_stop_closes_long_before_signal_flip():
    closes = [100, 100, 100, 100, 100, 105, 110, 110, 110]
    df = _make_bars(closes)
    df.loc[7, "low"] = 90.0  # a sharp intrabar drop on the bar after entry
    params = V4Params(lookback_days=1, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["exit_reason"] == "stop"
    assert t["entry_price"] == 110
    assert t["stop_price"] == 110 - 2.0 * 1.0  # atr_stop_multiplier * atr_14
    assert t["exit_price"] == t["stop_price"]
    assert t["gross_pnl_pct"] < 0


def test_position_still_open_at_end_is_not_recorded():
    closes = [100, 100, 100, 100, 100, 105, 110, 115, 120]  # uptrend never flips before data ends
    df = _make_bars(closes)
    params = V4Params(lookback_days=1, atr_stop_multiplier=2.0)
    trades = run_backtest(df, params)
    assert len(trades) == 0
