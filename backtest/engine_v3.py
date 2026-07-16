"""
Event-driven backtest engine for HYPOTHESIS.md v3: liquidity-regime overshoot
reversion. Shares the same no-lookahead execution conventions as v1/v2's
engines (see backtest/engine.py's docstring for the full rationale) -- entry
fills at the next bar's open, stop checked from the entry bar's own H/L
onward, time-boxed exit, one position at a time, funding accrual, skip if the
dataset ends before the trade's full horizon.

Signal (checked on every bar):
  - abs_return_percentile_30d (precomputed, fixed 30-day window) >= move_percentile_threshold
  - AND, depending on regime_filter, the bar's is_low_liquidity flag is
    True ("low_liquidity"), False ("high_liquidity"), or ignored ("all") --
    regime_filter is how Phase 3 runs the required treatment-vs-control
    comparison HYPOTHESIS.md specifies (same rule, different regime, to
    isolate whether any edge is liquidity-specific or just generic
    post-shock reversion).
Entry direction FADES the triggering bar's own return sign (reversion, like
v1, but triggered by session/liquidity timing rather than a funding extreme).
"""

from dataclasses import dataclass, field

import pandas as pd

from backtest.costs import CostModel, funding_pnl_pct, round_trip_cost_pct


@dataclass(frozen=True)
class V3Params:
    move_percentile_threshold: float = 0.80  # trigger = top 20% of trailing 30d |1h return| distribution
    atr_stop_multiplier: float = 2.0
    exit_horizon_hours: int = 8
    regime_filter: str = "low_liquidity"  # "low_liquidity" | "high_liquidity" | "all"
    cost_model: CostModel = field(default_factory=CostModel)


def run_backtest(df: pd.DataFrame, params: V3Params) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

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
            and pd.notna(row["abs_return_percentile_30d"])
            and pd.notna(row["atr_14"])
            and pd.notna(row["bar_return_1h"])
            and row["bar_return_1h"] != 0
            and row["abs_return_percentile_30d"] >= params.move_percentile_threshold
            and _regime_matches(row["is_low_liquidity"], params.regime_filter)
        ):
            direction = -1 if row["bar_return_1h"] > 0 else 1  # fade: short an up move, long a down move

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
                    "signal_move_percentile": row["abs_return_percentile_30d"],
                    "signal_time": row["datetime"],
                    "atr_at_entry": atr_at_signal,
                }

    return pd.DataFrame(trades)


def _regime_matches(is_low_liquidity: bool, regime_filter: str) -> bool:
    if regime_filter == "low_liquidity":
        return bool(is_low_liquidity)
    if regime_filter == "high_liquidity":
        return not bool(is_low_liquidity)
    if regime_filter == "all":
        return True
    raise ValueError(f"unknown regime_filter: {regime_filter!r}")


def _close_trade(position, exit_idx, exit_time, exit_price, exit_is_stop, params: V3Params) -> dict:
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
        "signal_move_percentile": position["signal_move_percentile"],
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
