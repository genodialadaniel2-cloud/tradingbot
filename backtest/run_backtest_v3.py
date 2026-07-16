from pathlib import Path

import pandas as pd

from backtest.engine_v3 import V3Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def load_in_sample() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "features_v3_1h.parquet")


def sample_days(df: pd.DataFrame) -> float:
    return (df["datetime"].max() - df["datetime"].min()).total_seconds() / 86400


def main():
    df = load_in_sample()
    days = sample_days(df)

    # All three regimes run side by side -- "low_liquidity" is the hypothesis's
    # actual claim, "high_liquidity" is the required control group, "all" is
    # an unconditional reference. See HYPOTHESIS.md's falsification criteria.
    for regime in ["low_liquidity", "high_liquidity", "all"]:
        params = V3Params(regime_filter=regime)
        trades = run_backtest(df, params)
        m = compute_metrics(trades, days)
        print(format_metrics(m, f"V3 regime={regime.upper()} (full in-sample, 2022-01-01 -> 2025-05-26)"))
        if len(trades):
            print(f"  gross-only expectancy (before costs): {trades['gross_pnl_pct'].mean():.4%}")
            print(f"  funding contribution to expectancy:   {trades['funding_pnl_pct'].mean():.4%}")
            print(f"  long trades: {(trades['direction']=='long').sum()}, short trades: {(trades['direction']=='short').sum()}")
        trades.to_csv(Path(__file__).parent / f"v3_{regime}_trades.csv", index=False)
        print()


if __name__ == "__main__":
    main()
