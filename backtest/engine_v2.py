"""
Event-driven backtest engine for HYPOTHESIS.md v2: volatility-compression
breakout continuation. Shares the same no-lookahead execution conventions as
v1's engine (backtest/engine.py) -- see that file's docstring for the full
rationale; only the signal and its dependence on the swept breakout window
differ here.

Signal (checked on every bar, not gated to funding settlements like v1):
  - vol_percentile_30d (precomputed, fixed 30-day window) <= vol_percentile_threshold
  - AND close breaks the prior N-hour high/low (N = breakout_window_hours,
    computed here per-run since it's a swept parameter, using
    rolling_prior_range() which excludes the current bar from its own range).
Entry direction follows the breakout (long on upside break, short on downside
-- continuation, not fade). Stop-loss and time-boxed exit, funding accrual,
and one-position-at-a-time all reuse the same logic/timing as v1's engine.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtest.costs import CostModel, funding_pnl_pct, round_trip_cost_pct
from features.indicators import rolling_prior_range


@dataclass(frozen=True)
class V2Params:
    vol_percentile_threshold: float = 0.15  # compressed = bottom 15% of trailing 30d realized vol
    breakout_window_hours: int = 24         # prior N-hour range to break out of
    atr_stop_multiplier: float = 2.0
    exit_horizon_hours: int = 12
    cost_model: CostModel = field(default_factory=CostModel)


def run_backtest(df: pd.DataFrame, params: V2Params) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    df["prior_high"], df["prior_low"] = rolling_prior_range(df["high"], df["low"], params.breakout_window_hours)

    n = len(df)
    trades = []
    position = None

    for i in range(n):
        row = df.iloc[i]

        if position is not None:
            hit_stop = (
                (position["direction"] == 1 and row["low"] <= position["stop_price"])
                or (position["direction"] == -1 and row["high"] >= position["stop_price"])
            )
            if hit_stop:
                trades.append(_close_trade(position, i, row["datetime"], position["stop_price"], exit_is_stop=True, params=params))
                position = None
            elif i >= position["exit_target_idx"]:
                trades.append(_close_trade(position, i, row["datetime"], row["close"], exit_is_stop=False, params=params))
                position = None
            else:
                if row["is_funding_settlement"] and i > position["entry_idx"]:
                    position["funding_accrued"] += funding_pnl_pct(position["direction"], row["fundingRate"])

        if (
            position is None
            and pd.notna(row["vol_percentile_30d"])
            and pd.notna(row["prior_high"])
            and pd.notna(row["atr_14"])
            and row["vol_percentile_30d"] <= params.vol_percentile_threshold
        ):
            direction = None
            if row["close"] > row["prior_high"]:
                direction = 1
            elif row["close"] < row["prior_low"]:
                direction = -1

            if direction is not None:
                entry_idx = i + 1
                exit_target_idx = entry_idx + params.exit_horizon_hours
                if entry_idx < n and exit_target_idx < n:
                    entry_row = df.iloc[entry_idx]
                    entry_price = entry_row["open"]
                    atr_at_signal = row["atr_14"]
                    stop_price = entry_price - direction * params.atr_stop_multiplier * atr_at_signal
                    position = {
                        "entry_idx": entry_idx,
                        "entry_time": entry_row["datetime"],
                        "entry_price": entry_price,
                        "direction": direction,
                        "stop_price": stop_price,
                        "exit_target_idx": exit_target_idx,
                        "funding_accrued": 0.0,
                        "signal_vol_percentile": row["vol_percentile_30d"],
                        "signal_time": row["datetime"],
                        "atr_at_entry": atr_at_signal,
                    }

    return pd.DataFrame(trades)


def _close_trade(position, exit_idx, exit_time, exit_price, exit_is_stop, params: V2Params) -> dict:
    direction = position["direction"]
    entry_price = position["entry_price"]
    gross_pnl_pct = direction * (exit_price - entry_price) / entry_price
    cost_pct = round_trip_cost_pct(params.cost_model, exit_is_stop)
    net_pnl_pct = gross_pnl_pct + position["funding_accrued"] - cost_pct

    return {
        "signal_time": position["signal_time"],
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "direction": "long" if direction == 1 else "short",
        "signal_vol_percentile": position["signal_vol_percentile"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "atr_at_entry": position["atr_at_entry"],
        "stop_price": position["stop_price"],
        "exit_reason": "stop" if exit_is_stop else "horizon",
        "holding_hours": exit_idx - position["entry_idx"],
        "gross_pnl_pct": gross_pnl_pct,
        "funding_pnl_pct": position["funding_accrued"],
        "cost_pct": cost_pct,
        "net_pnl_pct": net_pnl_pct,
    }
