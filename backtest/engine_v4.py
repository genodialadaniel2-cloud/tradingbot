"""
Event-driven backtest engine for HYPOTHESIS.md v4: daily-bar time-series
momentum. Structurally different from v1-v3's engines -- there is no fixed
time-boxed exit; a position is held as long as the trend signal (trailing
K-day return) agrees with its direction, and reverses (closes + reopens) the
day after the signal flips sign. An ATR-based stop can still close a position
early. Decisions are still made using information known as of a bar's close
and executed at the next bar's open (no lookahead), consistent with v1-v3.

Because entries/exits are signal-driven rather than time-boxed, a "pending
action" (decided at bar i's close) is executed at bar i+1's open -- this
mirrors v1-v3's next-bar-open fill convention but needs explicit state since
a reversal both closes and reopens a position on the same bar.

A position still open at the end of the dataset is dropped (not force-closed)
-- consistent with v1-v3's "skip if truncated" discipline, just implemented
differently since a trend-following exit has no fixed horizon to check against.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtest.costs import CostModel, funding_pnl_pct, round_trip_cost_pct
from features.indicators import trailing_return


@dataclass(frozen=True)
class V4Params:
    lookback_days: int = 30
    atr_stop_multiplier: float = 2.5
    cost_model: CostModel = field(default_factory=CostModel)


def run_backtest(df: pd.DataFrame, params: V4Params) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    if "trend_return" not in df.columns:
        # Not precomputed by the caller (e.g. base case, sensitivity sweep) --
        # compute it here on whatever range was passed in. Walk-forward
        # precomputes this on the FULL in-sample history before slicing into
        # windows instead, so each window's early bars still see a real
        # lookback_days trailing history rather than a truncated one -- see
        # backtest/walk_forward_v4.py.
        df["trend_return"] = trailing_return(df["close"], params.lookback_days)

    n = len(df)
    trades = []
    position = None
    pending = None  # ("open", direction, atr_at_signal) or ("flip", direction, atr_at_signal)

    for i in range(n):
        row = df.iloc[i]

        if pending is not None:
            action, direction, atr_at_signal = pending
            pending = None
            if action == "flip" and position is not None:
                trades.append(_close_trade(position, i, row["datetime"], row["open"], exit_is_stop=False, exit_reason="signal_flip", params=params))
                position = None
            position = _open_position(i, row, direction, atr_at_signal, params)

        if position is not None:
            hit_stop = (
                (position["direction"] == 1 and row["low"] <= position["stop_price"])
                or (position["direction"] == -1 and row["high"] >= position["stop_price"])
            )
            if hit_stop:
                trades.append(_close_trade(position, i, row["datetime"], position["stop_price"], exit_is_stop=True, exit_reason="stop", params=params))
                position = None
            elif i > position["entry_idx"]:
                position["funding_accrued"] += funding_pnl_pct(position["direction"], row["funding_sum"])

        if pd.notna(row["trend_return"]) and pd.notna(row["atr_14"]):
            if row["trend_return"] > 0:
                desired = 1
            elif row["trend_return"] < 0:
                desired = -1
            else:
                desired = 0

            if desired != 0 and i + 1 < n:
                if position is None:
                    pending = ("open", desired, row["atr_14"])
                elif position["direction"] != desired:
                    pending = ("flip", desired, row["atr_14"])

    return pd.DataFrame(trades)


def _open_position(entry_idx: int, entry_row: pd.Series, direction: int, atr_at_signal: float, params: V4Params) -> dict:
    entry_price = entry_row["open"]
    stop_price = entry_price - direction * params.atr_stop_multiplier * atr_at_signal
    return {
        "entry_idx": entry_idx,
        "entry_time": entry_row["datetime"],
        "entry_price": entry_price,
        "direction": direction,
        "stop_price": stop_price,
        "funding_accrued": 0.0,
        "atr_at_entry": atr_at_signal,
    }


def _close_trade(position, exit_idx, exit_time, exit_price, exit_is_stop, exit_reason, params: V4Params) -> dict:
    direction = position["direction"]
    entry_price = position["entry_price"]
    gross_pnl_pct = direction * (exit_price - entry_price) / entry_price
    cost_pct = round_trip_cost_pct(params.cost_model, exit_is_stop)
    net_pnl_pct = gross_pnl_pct + position["funding_accrued"] - cost_pct

    return {
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "direction": "long" if direction == 1 else "short",
        "entry_price": entry_price,
        "exit_price": exit_price,
        "atr_at_entry": position["atr_at_entry"],
        "stop_price": position["stop_price"],
        "exit_reason": exit_reason,
        "holding_days": exit_idx - position["entry_idx"],
        "gross_pnl_pct": gross_pnl_pct,
        "funding_pnl_pct": position["funding_accrued"],
        "cost_pct": cost_pct,
        "net_pnl_pct": net_pnl_pct,
    }
