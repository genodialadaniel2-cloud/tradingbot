"""
Phase 3 walk-forward for v3, run for both the low_liquidity treatment and the
high_liquidity control in every window side by side -- a single window where
the treatment beats the control isn't enough; the comparison needs to hold up
window by window per HYPOTHESIS.md's falsification criteria.
"""

from backtest.engine_v3 import V3Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest_v3 import load_in_sample
from backtest.walk_forward import make_windows

N_WINDOWS = 6


def main():
    df = load_in_sample()
    windows = make_windows(df, N_WINDOWS)

    results = {"low_liquidity": [], "high_liquidity": []}
    for i, (w_start, w_end, w_df) in enumerate(windows, start=1):
        days = (w_end - w_start).total_seconds() / 86400
        print(f"=== Window {i}: {w_start.date()} -> {w_end.date()} ({days:.0f}d) ===")
        for regime in ["low_liquidity", "high_liquidity"]:
            params = V3Params(regime_filter=regime)
            trades = run_backtest(w_df, params)
            m = compute_metrics(trades, days)
            m["window"] = i
            m["start"] = w_start
            m["end"] = w_end
            results[regime].append(m)
            print(format_metrics(m, f"  {regime}"))
        print()

    return results


if __name__ == "__main__":
    main()
