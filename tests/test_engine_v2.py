import pandas as pd

from backtest.costs import CostModel
from backtest.engine_v2 import V2Params, run_backtest


def _make_bars(n, base_price=100.0):
    dt = pd.date_range(pd.Timestamp("2024-01-01", tz="UTC"), periods=n, freq="h")
    df = pd.DataFrame(
        {
            "datetime": dt,
            "open": [base_price] * n,
            "high": [base_price + 0.2] * n,
            "low": [base_price - 0.2] * n,
            "close": [base_price] * n,
            "atr_14": [1.0] * n,
            "vol_percentile_30d": [0.5] * n,
            "fundingRate": [0.0] * n,
            "is_funding_settlement": [False] * n,
        }
    )
    return df


def test_no_signal_when_not_compressed():
    n = 40
    df = _make_bars(n)
    # a clean breakout shape, but vol_percentile stays high (not compressed) throughout
    df.loc[10, "close"] = 150.0
    df.loc[10, "high"] = 150.5
    params = V2Params(breakout_window_hours=5, vol_percentile_threshold=0.15, exit_horizon_hours=5)
    trades = run_backtest(df, params)
    assert len(trades) == 0


def test_long_on_compressed_upside_breakout():
    n = 40
    df = _make_bars(n)
    df.loc[10, "vol_percentile_30d"] = 0.05  # compressed
    df.loc[10, "close"] = 150.0  # breaks well above the prior 100-ish range
    df.loc[10, "high"] = 150.5
    # rally continues after entry
    for i in range(11, n):
        df.loc[i, "open"] = 150.0 + (i - 10)
        df.loc[i, "close"] = 150.0 + (i - 10)
        df.loc[i, "high"] = df.loc[i, "open"] + 0.5
        df.loc[i, "low"] = df.loc[i, "open"] - 0.5

    params = V2Params(breakout_window_hours=5, vol_percentile_threshold=0.15, exit_horizon_hours=5, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "long"
    assert t["gross_pnl_pct"] > 0


def test_short_on_compressed_downside_breakout():
    n = 40
    df = _make_bars(n)
    df.loc[10, "vol_percentile_30d"] = 0.05
    df.loc[10, "close"] = 50.0  # breaks well below the prior range
    df.loc[10, "low"] = 49.5
    for i in range(11, n):
        df.loc[i, "open"] = 50.0 - (i - 10)
        df.loc[i, "close"] = 50.0 - (i - 10)
        df.loc[i, "high"] = df.loc[i, "open"] + 0.5
        df.loc[i, "low"] = df.loc[i, "open"] - 0.5

    params = V2Params(breakout_window_hours=5, vol_percentile_threshold=0.15, exit_horizon_hours=5, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "short"
    assert t["gross_pnl_pct"] > 0


def test_no_signal_without_actual_range_break():
    n = 40
    df = _make_bars(n)
    df.loc[10, "vol_percentile_30d"] = 0.05  # compressed, but price never breaks the range
    params = V2Params(breakout_window_hours=5, vol_percentile_threshold=0.15, exit_horizon_hours=5)
    trades = run_backtest(df, params)
    assert len(trades) == 0
