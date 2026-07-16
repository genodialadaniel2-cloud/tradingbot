from pathlib import Path

import pandas as pd

from backtest.engine_v4 import V4Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def load_in_sample() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "features_v4_1d.parquet")


def sample_days(df: pd.DataFrame) -> float:
    return (df["datetime"].max() - df["datetime"].min()).total_seconds() / 86400


def main():
    df = load_in_sample()
    days = sample_days(df)
    params = V4Params()
    trades = run_backtest(df, params)
    m = compute_metrics(trades, days)
    print(format_metrics(m, "V4 BASE CASE (daily bars, full in-sample, 2022-01-01 -> 2025-05-26)"))
    print()
    if len(trades):
        print(f"Gross-only expectancy (before costs): {trades['gross_pnl_pct'].mean():.4%}")
        print(f"Funding contribution to expectancy: {trades['funding_pnl_pct'].mean():.4%}")
        print(f"Long trades: {(trades['direction']=='long').sum()}, Short trades: {(trades['direction']=='short').sum()}")
        print(f"Signal-flip exits: {(trades['exit_reason']=='signal_flip').sum()}, Stop exits: {(trades['exit_reason']=='stop').sum()}")
        print(f"Median holding period: {trades['holding_days'].median():.0f} days")
    trades.to_csv(Path(__file__).parent / "v4_base_case_trades.csv", index=False)


if __name__ == "__main__":
    main()
