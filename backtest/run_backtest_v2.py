from pathlib import Path

import pandas as pd

from backtest.engine_v2 import V2Params, run_backtest
from backtest.metrics import compute_metrics, format_metrics

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def load_in_sample() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "features_v2_1h.parquet")


def sample_days(df: pd.DataFrame) -> float:
    return (df["datetime"].max() - df["datetime"].min()).total_seconds() / 86400


def main():
    df = load_in_sample()
    params = V2Params()
    trades = run_backtest(df, params)
    m = compute_metrics(trades, sample_days(df))
    print(format_metrics(m, "V2 BASE CASE (full in-sample, 2022-01-01 -> 2025-05-26)"))
    print()
    if len(trades):
        print(f"Gross-only expectancy (before costs): {trades['gross_pnl_pct'].mean():.4%}")
        print(f"Funding contribution to expectancy: {trades['funding_pnl_pct'].mean():.4%}")
        print(f"Long trades: {(trades['direction']=='long').sum()}, Short trades: {(trades['direction']=='short').sum()}")
    trades.to_csv(Path(__file__).parent / "v2_base_case_trades.csv", index=False)


if __name__ == "__main__":
    main()
