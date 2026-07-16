"""
Phase 3 orchestration: run the base-case parameters on the full in-sample
data/processed/features_1h.parquet, then walk-forward windows, then parameter
sensitivity. Never reads data/holdout/ -- that's a separate, one-time script
run only after every parameter is frozen.
"""

from pathlib import Path

import pandas as pd

from backtest.engine import StrategyParams, run_backtest
from backtest.metrics import compute_metrics, format_metrics

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def load_in_sample() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "features_1h.parquet")


def sample_days(df: pd.DataFrame) -> float:
    return (df["datetime"].max() - df["datetime"].min()).total_seconds() / 86400


def main():
    df = load_in_sample()
    params = StrategyParams()
    trades = run_backtest(df, params)
    m = compute_metrics(trades, sample_days(df))
    print(format_metrics(m, "BASE CASE (full in-sample, 2022-01-01 -> 2025-05-26)"))
    print()
    print(f"Gross-only expectancy (before costs): {trades['gross_pnl_pct'].mean():.4%}" if len(trades) else "no trades")
    print(f"Funding-carry contribution to expectancy: {trades['funding_pnl_pct'].mean():.4%}" if len(trades) else "")
    trades.to_csv(Path(__file__).parent / "base_case_trades.csv", index=False)


if __name__ == "__main__":
    main()
