"""
Phase 3 FINAL, ONE-TIME holdout validation. Run exactly once, after every
parameter choice was frozen using only in-sample data (see RESEARCH_LOG.md).
Never re-run this script with different parameters based on what it reports --
that would be holdout optimization, which the standing rules forbid outright.

Builds its own features on data/holdout/ raw data using the SAME feature code
as the in-sample pipeline, but the funding percentile/z-score trailing window
naturally warms up using only holdout-period data (a limitation disclosed in
RESEARCH_LOG.md, not hidden).
"""

from pathlib import Path

import pandas as pd

from backtest.engine import StrategyParams, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from features.indicators import atr, funding_percentile, funding_zscore

HOLDOUT_DIR = Path(__file__).parent.parent / "data" / "holdout"

# Frozen base-case parameters from HYPOTHESIS.md / Phase 3 in-sample work.
# NOT re-tuned based on holdout results -- this is the one and only look.
FROZEN_PARAMS = StrategyParams()


def build_holdout_features() -> pd.DataFrame:
    ohlcv = pd.read_parquet(HOLDOUT_DIR / "ohlcv_1h.parquet")
    funding = pd.read_parquet(HOLDOUT_DIR / "funding_rate.parquet")

    ohlcv["datetime"] = pd.to_datetime(ohlcv["timestamp"], unit="ms", utc=True)
    funding["datetime"] = pd.to_datetime(funding["timestamp"], unit="ms", utc=True)
    ohlcv = ohlcv.sort_values("datetime").reset_index(drop=True)
    funding = funding.sort_values("datetime").reset_index(drop=True)

    ohlcv["atr_14"] = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)
    funding["funding_zscore_90d"] = funding_zscore(funding["fundingRate"])
    funding["funding_percentile_90d"] = funding_percentile(funding["fundingRate"])

    merged = pd.merge_asof(
        ohlcv,
        funding[["datetime", "fundingRate", "funding_zscore_90d", "funding_percentile_90d"]],
        on="datetime",
        direction="backward",
    )
    merged["is_funding_settlement"] = merged["datetime"].isin(set(funding["datetime"]))
    return merged


def main():
    df = build_holdout_features()
    days = (df["datetime"].max() - df["datetime"].min()).total_seconds() / 86400
    trades = run_backtest(df, FROZEN_PARAMS)
    m = compute_metrics(trades, days)
    print(format_metrics(m, f"HOLDOUT (frozen params, {df['datetime'].min().date()} -> {df['datetime'].max().date()}, {days:.0f}d) -- ONE-TIME RUN"))
    trades.to_csv(Path(__file__).parent / "holdout_trades.csv", index=False)


if __name__ == "__main__":
    main()
