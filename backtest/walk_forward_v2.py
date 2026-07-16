from backtest.engine_v2 import V2Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest_v2 import load_in_sample
from backtest.walk_forward import make_windows

N_WINDOWS = 6


def main(params: V2Params = None):
    params = params or V2Params()
    df = load_in_sample()
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
