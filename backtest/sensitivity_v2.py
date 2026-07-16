from backtest.engine_v2 import V2Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest_v2 import load_in_sample, sample_days

BASE = V2Params()


def main():
    df = load_in_sample()
    days = sample_days(df)

    variants = {
        "BASE (vol_pct=0.15, breakout_window=24h, atr_mult=2.0, horizon=12h)": BASE,
        "vol_percentile_threshold=0.12 (-20%)": V2Params(vol_percentile_threshold=0.12),
        "vol_percentile_threshold=0.18 (+20%)": V2Params(vol_percentile_threshold=0.18),
        "breakout_window_hours=19 (-20%)": V2Params(breakout_window_hours=19),
        "breakout_window_hours=29 (+20%)": V2Params(breakout_window_hours=29),
        "atr_stop_multiplier=1.6 (-20%)": V2Params(atr_stop_multiplier=1.6),
        "atr_stop_multiplier=2.4 (+20%)": V2Params(atr_stop_multiplier=2.4),
        "exit_horizon_hours=10 (-17%)": V2Params(exit_horizon_hours=10),
        "exit_horizon_hours=14 (+17%)": V2Params(exit_horizon_hours=14),
    }

    for label, params in variants.items():
        trades = run_backtest(df, params)
        m = compute_metrics(trades, days)
        print(format_metrics(m, label))
        print()


if __name__ == "__main__":
    main()
