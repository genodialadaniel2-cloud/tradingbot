"""
Phase 3 walk-forward for v4. Same 6-window split as v1-v3 for comparability,
but per HYPOTHESIS.md's disclosed caveat, daily-bar trend-following produces
far fewer trades than v1-v3's hourly signals -- individual windows may not
clear the ~100-trade sample-size comfort level v1-v3 achieved. Trade counts
are reported explicitly per window rather than papered over.
"""

from backtest.engine_v4 import V4Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest_v4 import load_in_sample
from backtest.walk_forward import make_windows
from features.indicators import trailing_return

N_WINDOWS = 6


def main(params: V4Params = None):
    params = params or V4Params()
    df = load_in_sample()
    df["trend_return"] = trailing_return(df["close"], params.lookback_days)  # full-history lookback, then sliced -- see engine_v4.run_backtest
    windows = make_windows(df, N_WINDOWS)

    results = []
    for i, (w_start, w_end, w_df) in enumerate(windows, start=1):
        trades = run_backtest(w_df, params)
        days = (w_end - w_start).total_seconds() / 86400
        m = compute_metrics(trades, days)
        m["window"] = i
        results.append(m)
        print(format_metrics(m, f"Window {i}: {w_start.date()} -> {w_end.date()} ({days:.0f}d)"))
        print()

    return results


if __name__ == "__main__":
    main()
