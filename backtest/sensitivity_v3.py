from backtest.engine_v3 import V3Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest_v3 import load_in_sample, sample_days

BASE = V3Params()


def main():
    df = load_in_sample()
    days = sample_days(df)

    variants = {
        "BASE (move_pct=0.80, atr_mult=2.0, horizon=8h, regime=low_liquidity)": BASE,
        "move_percentile_threshold=0.64 (-20%)": V3Params(move_percentile_threshold=0.64),
        "move_percentile_threshold=0.96 (+20%)": V3Params(move_percentile_threshold=0.96),
        "atr_stop_multiplier=1.6 (-20%)": V3Params(atr_stop_multiplier=1.6),
        "atr_stop_multiplier=2.4 (+20%)": V3Params(atr_stop_multiplier=2.4),
        "exit_horizon_hours=6 (-25%)": V3Params(exit_horizon_hours=6),
        "exit_horizon_hours=10 (+25%)": V3Params(exit_horizon_hours=10),
    }

    for label, params in variants.items():
        trades = run_backtest(df, params)
        m = compute_metrics(trades, days)
        print(format_metrics(m, label))
        print()


if __name__ == "__main__":
    main()
