from backtest.engine_v4 import V4Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest_v4 import load_in_sample, sample_days

BASE = V4Params()


def main():
    df = load_in_sample()
    days = sample_days(df)

    variants = {
        "BASE (lookback=30d, atr_mult=2.5)": BASE,
        "lookback_days=24 (-20%)": V4Params(lookback_days=24),
        "lookback_days=36 (+20%)": V4Params(lookback_days=36),
        "atr_stop_multiplier=2.0 (-20%)": V4Params(atr_stop_multiplier=2.0),
        "atr_stop_multiplier=3.0 (+20%)": V4Params(atr_stop_multiplier=3.0),
    }

    for label, params in variants.items():
        trades = run_backtest(df, params)
        m = compute_metrics(trades, days)
        print(format_metrics(m, label))
        print()


if __name__ == "__main__":
    main()
