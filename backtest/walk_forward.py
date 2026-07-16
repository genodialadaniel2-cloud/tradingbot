"""
Phase 3 walk-forward: the hypothesis is a fixed rule (no fitted parameters),
so there's nothing to "train" per window -- what's being checked is whether a
single frozen rule holds up consistently period-by-period, not just in
aggregate. Splits the in-sample range into N consecutive, non-overlapping
chronological windows and reports each independently.

Feature values (funding percentile, ATR) are computed once over the FULL
in-sample history before slicing, so each window's signals still see a real
90-day trailing lookback rather than a truncated one -- windowing only affects
which bars are eligible to open trades, not how the features are computed.
"""

from pathlib import Path

import pandas as pd

from backtest.engine import StrategyParams, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest import load_in_sample

N_WINDOWS = 6


def make_windows(df: pd.DataFrame, n_windows: int):
    start, end = df["datetime"].min(), df["datetime"].max()
    total = (end - start)
    edges = [start + total * i / n_windows for i in range(n_windows + 1)]
    windows = []
    for i in range(n_windows):
        w = df[(df["datetime"] >= edges[i]) & (df["datetime"] < edges[i + 1])]
        windows.append((edges[i], edges[i + 1], w))
    return windows


def main(params: StrategyParams = None):
    params = params or StrategyParams()
    df = load_in_sample()
    windows = make_windows(df, N_WINDOWS)

    results = []
    for i, (w_start, w_end, w_df) in enumerate(windows, start=1):
        trades = run_backtest(w_df, params)
        days = (w_end - w_start).total_seconds() / 86400
        m = compute_metrics(trades, days)
        m["window"] = i
        m["start"] = w_start
        m["end"] = w_end
        results.append(m)
        print(format_metrics(m, f"Window {i}: {w_start.date()} -> {w_end.date()} ({days:.0f}d)"))
        print()

    return results


if __name__ == "__main__":
    main()
