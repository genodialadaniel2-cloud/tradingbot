import pandas as pd

from backtest.costs import CostModel
from backtest.engine import StrategyParams, run_backtest


def _make_bars(prices, funding_rates=None, funding_percentiles=None):
    n = len(prices)
    start = pd.Timestamp("2024-01-01", tz="UTC")
    dt = pd.date_range(start, periods=n, freq="h")
    df = pd.DataFrame(
        {
            "datetime": dt,
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "atr_14": [1.0] * n,
            "fundingRate": funding_rates if funding_rates is not None else [0.0] * n,
            "funding_percentile_90d": funding_percentiles if funding_percentiles is not None else [0.5] * n,
            "is_funding_settlement": [False] * n,
        }
    )
    return df


def test_long_signal_on_extreme_low_percentile_profits_on_rally():
    n = 40
    prices = [100.0] * n
    percentiles = [0.5] * n
    percentiles[5] = 0.01  # extreme low -> fade with a long
    funding = [0.0] * n
    df = _make_bars(prices, funding, percentiles)
    df.loc[5, "is_funding_settlement"] = True
    # price rallies steadily after entry (bar 6 onward)
    for i in range(6, n):
        df.loc[i, "open"] = 100.0 + (i - 5)
        df.loc[i, "close"] = 100.0 + (i - 5)
        df.loc[i, "high"] = df.loc[i, "open"] + 0.5
        df.loc[i, "low"] = df.loc[i, "open"] - 0.5

    params = StrategyParams(exit_horizon_hours=5, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "long"
    assert t["exit_reason"] == "horizon"
    assert t["gross_pnl_pct"] > 0  # rallied after a long entry -> profit


def test_short_signal_on_extreme_high_percentile_profits_on_selloff():
    n = 40
    prices = [100.0] * n
    percentiles = [0.5] * n
    percentiles[5] = 0.99  # extreme high -> fade with a short
    df = _make_bars(prices, [0.0] * n, percentiles)
    df.loc[5, "is_funding_settlement"] = True
    for i in range(6, n):
        df.loc[i, "open"] = 100.0 - (i - 5)
        df.loc[i, "close"] = 100.0 - (i - 5)
        df.loc[i, "high"] = df.loc[i, "open"] + 0.5
        df.loc[i, "low"] = df.loc[i, "open"] - 0.5

    params = StrategyParams(exit_horizon_hours=5, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "short"
    assert t["gross_pnl_pct"] > 0  # sold off after a short entry -> profit


def test_stop_loss_triggers_before_horizon_and_uses_stop_slippage():
    n = 40
    prices = [100.0] * n
    percentiles = [0.5] * n
    percentiles[5] = 0.01  # long signal
    df = _make_bars(prices, [0.0] * n, percentiles)
    df.loc[5, "is_funding_settlement"] = True
    # price crashes right after entry -- should hit the long stop (entry - 2*ATR = entry - 2.0)
    df.loc[6, "open"] = 100.0
    df.loc[6, "low"] = 90.0  # blows through the stop
    df.loc[6, "high"] = 100.5
    df.loc[6, "close"] = 95.0
    for i in range(7, n):
        df.loc[i, "open"] = 95.0
        df.loc[i, "close"] = 95.0
        df.loc[i, "high"] = 95.5
        df.loc[i, "low"] = 94.5

    params = StrategyParams(exit_horizon_hours=10, atr_stop_multiplier=2.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["exit_reason"] == "stop"
    assert t["exit_price"] == t["stop_price"] == 98.0  # entry 100 - 2*ATR(1.0)*2.0
    assert t["gross_pnl_pct"] < 0


def test_funding_accrual_sign_short_receives_positive_funding():
    n = 40
    prices = [100.0] * n
    percentiles = [0.5] * n
    percentiles[5] = 0.99  # short signal
    funding = [0.0] * n
    funding[13] = 0.001  # a settlement crossed while holding (entry at bar 6, horizon 10 -> exit bar 16)
    df = _make_bars(prices, funding, percentiles)
    df.loc[5, "is_funding_settlement"] = True
    df.loc[13, "is_funding_settlement"] = True

    params = StrategyParams(exit_horizon_hours=10, atr_stop_multiplier=100.0, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "short"
    # short receives funding when funding rate is positive (longs pay shorts)
    assert t["funding_pnl_pct"] > 0
    assert abs(t["funding_pnl_pct"] - 0.001) < 1e-12


def test_no_trade_taken_if_horizon_cannot_complete_before_data_ends():
    n = 10
    prices = [100.0] * n
    percentiles = [0.5] * n
    percentiles[8] = 0.01  # signal too close to the end of the dataset
    df = _make_bars(prices, [0.0] * n, percentiles)
    df.loc[8, "is_funding_settlement"] = True

    params = StrategyParams(exit_horizon_hours=12, cost_model=CostModel(0, 0, 0))
    trades = run_backtest(df, params)

    assert len(trades) == 0


def test_costs_reduce_net_pnl_below_gross():
    n = 40
    prices = [100.0] * n
    percentiles = [0.5] * n
    percentiles[5] = 0.01
    df = _make_bars(prices, [0.0] * n, percentiles)
    df.loc[5, "is_funding_settlement"] = True
    for i in range(6, n):
        df.loc[i, "open"] = 100.0 + (i - 5)
        df.loc[i, "close"] = 100.0 + (i - 5)
        df.loc[i, "high"] = df.loc[i, "open"] + 0.5
        df.loc[i, "low"] = df.loc[i, "open"] - 0.5

    params = StrategyParams(exit_horizon_hours=5, cost_model=CostModel(taker_fee=0.0005, slippage_normal=0.0002, slippage_stop=0.001))
    trades = run_backtest(df, params)

    t = trades.iloc[0]
    assert t["net_pnl_pct"] < t["gross_pnl_pct"]
    assert t["cost_pct"] > 0
