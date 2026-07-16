import pandas as pd

from backtest.costs import CostModel
from backtest.engine_v3 import V3Params, run_backtest


def _make_bars(n, base_price=100.0, low_liquidity=False):
    dt = pd.date_range(pd.Timestamp("2024-01-01", tz="UTC"), periods=n, freq="h")
    df = pd.DataFrame(
        {
            "datetime": dt,
            "open": [base_price] * n,
            "high": [base_price + 0.2] * n,
            "low": [base_price - 0.2] * n,
            "close": [base_price] * n,
            "atr_14": [1.0] * n,
            "bar_return_1h": [0.0] * n,
            "abs_return_percentile_30d": [0.5] * n,
            "is_low_liquidity": [low_liquidity] * n,
            "fundingRate": [0.0] * n,
            "is_funding_settlement": [False] * n,
        }
    )
    return df


def test_no_signal_when_move_not_large_enough():
    n = 40
    df = _make_bars(n, low_liquidity=True)
    df.loc[10, "close"] = 103.0  # a real move, but percentile stays below threshold
    df.loc[10, "bar_return_1h"] = 0.03
    params = V3Params(move_percentile_threshold=0.80, exit_horizon_hours=5)
    trades = run_backtest(df, params)
    assert len(trades) == 0


def test_fades_up_move_with_short_in_low_liquidity_window():
    n = 40
    df = _make_bars(n, low_liquidity=True)
    df.loc[10, "abs_return_percentile_30d"] = 0.95  # large move
    df.loc[10, "bar_return_1h"] = 0.05  # up move -> should fade with a short
    # price reverts (falls) after entry so a short is profitable
    for i in range(11, n):
        df.loc[i, "open"] = 100.0 - (i - 10) * 0.1
        df.loc[i, "close"] = 100.0 - (i - 10) * 0.1
        df.loc[i, "high"] = df.loc[i, "open"] + 0.2
        df.loc[i, "low"] = df.loc[i, "open"] - 0.2

    params = V3Params(move_percentile_threshold=0.80, exit_horizon_hours=5, atr_stop_multiplier=2.0, regime_filter="low_liquidity", cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "short"
    assert t["gross_pnl_pct"] > 0


def test_fades_down_move_with_long():
    n = 40
    df = _make_bars(n, low_liquidity=True)
    df.loc[10, "abs_return_percentile_30d"] = 0.95
    df.loc[10, "bar_return_1h"] = -0.05  # down move -> should fade with a long
    for i in range(11, n):
        df.loc[i, "open"] = 100.0 + (i - 10) * 0.1
        df.loc[i, "close"] = 100.0 + (i - 10) * 0.1
        df.loc[i, "high"] = df.loc[i, "open"] + 0.2
        df.loc[i, "low"] = df.loc[i, "open"] - 0.2

    params = V3Params(move_percentile_threshold=0.80, exit_horizon_hours=5, atr_stop_multiplier=2.0, regime_filter="low_liquidity", cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "long"
    assert t["gross_pnl_pct"] > 0


def test_regime_filter_low_liquidity_ignores_high_liquidity_bar():
    n = 40
    df = _make_bars(n, low_liquidity=False)  # bar occurs in a high-liquidity window
    df.loc[10, "abs_return_percentile_30d"] = 0.95
    df.loc[10, "bar_return_1h"] = 0.05
    params = V3Params(move_percentile_threshold=0.80, exit_horizon_hours=5, regime_filter="low_liquidity")
    trades = run_backtest(df, params)
    assert len(trades) == 0


def test_regime_filter_high_liquidity_ignores_low_liquidity_bar():
    n = 40
    df = _make_bars(n, low_liquidity=True)  # bar occurs in a low-liquidity window
    df.loc[10, "abs_return_percentile_30d"] = 0.95
    df.loc[10, "bar_return_1h"] = 0.05
    params = V3Params(move_percentile_threshold=0.80, exit_horizon_hours=5, regime_filter="high_liquidity")
    trades = run_backtest(df, params)
    assert len(trades) == 0


def test_regime_filter_all_ignores_liquidity_flag():
    n = 40
    df = _make_bars(n, low_liquidity=False)
    df.loc[10, "abs_return_percentile_30d"] = 0.95
    df.loc[10, "bar_return_1h"] = 0.05
    for i in range(11, n):
        df.loc[i, "open"] = 100.0 - (i - 10) * 0.1
        df.loc[i, "close"] = 100.0 - (i - 10) * 0.1
        df.loc[i, "high"] = df.loc[i, "open"] + 0.2
        df.loc[i, "low"] = df.loc[i, "open"] - 0.2
    params = V3Params(move_percentile_threshold=0.80, exit_horizon_hours=5, regime_filter="all", cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)
    assert len(trades) == 1
