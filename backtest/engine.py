"""
Event-driven backtest engine for the HYPOTHESIS.md rule: fade funding-rate
extremes, ATR stop, time-boxed exit. Every decision at bar i uses only data
known as of bar i's close; entries fill at the NEXT bar's open (a realistic
"can't trade the exact close tick" assumption, not lookahead -- the decision
itself never depends on data from bar i+1 or later).

Execution/timing conventions (logged here because they materially affect
results, per CLAUDE.md's "every strategy change should be explainable"):
  - Signal is evaluated only on bars that are exact funding-settlement bars
    (every 8h), using that bar's own funding percentile/z-score and ATR(14)
    as of that bar's close.
  - Entry fills at the OPEN of the following bar (signal_bar_idx + 1).
  - Stop-loss level is fixed at entry (entry_price -/+ multiplier * ATR at
    signal time) and checked against each subsequent bar's high/low, starting
    with the entry bar itself (its open is the fill, its own high/low can still
    trigger the stop within the same bar -- not lookahead, since the open
    precedes the high/low within that bar).
  - If no stop is hit, the trade exits at the CLOSE of the bar exactly
    `exit_horizon_hours` after the entry bar (a pre-committed, not
    data-dependent, exit -- doesn't introduce lookahead).
  - One position at a time: a new signal is ignored while a trade is open (no
    pyramiding/concurrent positions -- position sizing/portfolio management is
    explicitly Phase 4, out of scope here).
  - A signal is not taken at all if there isn't enough remaining data to let
    the trade reach its full exit horizon -- avoids counting an artificially
    truncated trade at the end of the dataset as a real outcome.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtest.costs import CostModel, funding_pnl_pct, round_trip_cost_pct


@dataclass(frozen=True)
class StrategyParams:
    percentile_tail: float = 0.05       # fade when trailing-90d percentile is in the top/bottom 5%
    atr_stop_multiplier: float = 2.0    # stop distance = multiplier * ATR(14, 1h) at signal time
    exit_horizon_hours: int = 12        # time-boxed exit, mid-point of the hypothesis's 4-24h window
    cost_model: CostModel = field(default_factory=CostModel)


def run_backtest(df: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    df = df.reset_index(drop=True)
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
            and row["is_funding_settlement"]
            and pd.notna(row["funding_percentile_90d"])
            and pd.notna(row["atr_14"])
        ):
            direction = None
            if row["funding_percentile_90d"] >= 1 - params.percentile_tail:
                direction = -1  # fade positive extreme -> short
            elif row["funding_percentile_90d"] <= params.percentile_tail:
                direction = 1  # fade negative extreme -> long

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
                        "signal_percentile": row["funding_percentile_90d"],
                        "signal_time": row["datetime"],
                        "atr_at_entry": atr_at_signal,
                    }

    return pd.DataFrame(trades)


def _close_trade(position, exit_idx, exit_time, exit_price, exit_is_stop, params: StrategyParams) -> dict:
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
        "signal_percentile": position["signal_percentile"],
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
