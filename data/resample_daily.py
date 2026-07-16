"""
Phase 1 (v4 hypothesis): resample the already-cleaned, gap-checked in-sample
hourly data (data/processed/) to daily (UTC midnight-to-midnight) bars. No
new data pull -- v4's daily-bar pivot is a re-aggregation of the same
underlying trades/prints already fetched for v1-v3, not a new source.

OHLC aggregation: open=first, high=max, low=min, close=last, volume=sum --
standard resampling, introduces no lookahead since each daily bar is built
only from that day's own hourly bars.

Funding: summed per day (3 settlements/day) so the engine can apply one
funding cost/tailwind figure per day a position is held, consistent with
v1-v3's per-settlement funding accrual but at daily granularity.
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).parent / "processed"


def main():
    ohlcv = pd.read_parquet(PROCESSED_DIR / "ohlcv_1h.parquet").sort_values("datetime").reset_index(drop=True)
    funding = pd.read_parquet(PROCESSED_DIR / "funding_rate_8h.parquet").sort_values("datetime").reset_index(drop=True)

    ohlcv_daily = (
        ohlcv.set_index("datetime")
        .resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])  # drop any partial/empty calendar day
        .reset_index()
    )

    funding_daily = (
        funding.set_index("datetime")[["fundingRate"]]
        .resample("1D")
        .sum()
        .rename(columns={"fundingRate": "funding_sum"})
        .reset_index()
    )

    merged = pd.merge_asof(ohlcv_daily, funding_daily, on="datetime", direction="backward")
    merged["funding_sum"] = merged["funding_sum"].fillna(0.0)

    merged.to_parquet(PROCESSED_DIR / "ohlcv_1d.parquet", index=False)

    print(f"Resampled {len(ohlcv)} hourly bars -> {len(merged)} daily bars")
    print(f"Range: {merged['datetime'].min()} -> {merged['datetime'].max()}")
    print(f"Funding daily sum: mean={merged['funding_sum'].mean():.5%}, missing={merged['funding_sum'].isna().sum()}")
    print("Wrote data/processed/ohlcv_1d.parquet")


if __name__ == "__main__":
    main()
