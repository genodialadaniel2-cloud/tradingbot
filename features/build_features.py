"""
Phase 2: compute the two features HYPOTHESIS.md needs (funding z-score /
percentile, ATR) on the in-sample data only (data/processed/, itself built
from data/raw/ -- never data/holdout/) and write them out for Phase 3.

Regeneratable from data/processed/ with no network calls.
"""

from pathlib import Path

import pandas as pd

from features.indicators import atr, funding_percentile, funding_zscore

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def main():
    ohlcv = pd.read_parquet(PROCESSED_DIR / "ohlcv_1h.parquet")
    funding = pd.read_parquet(PROCESSED_DIR / "funding_rate_8h.parquet")

    ohlcv = ohlcv.sort_values("datetime").reset_index(drop=True)
    funding = funding.sort_values("datetime").reset_index(drop=True)

    ohlcv["atr_14"] = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)

    funding["funding_zscore_90d"] = funding_zscore(funding["fundingRate"])
    funding["funding_percentile_90d"] = funding_percentile(funding["fundingRate"])

    ohlcv.to_parquet(PROCESSED_DIR / "ohlcv_features_1h.parquet", index=False)
    funding.to_parquet(PROCESSED_DIR / "funding_features_8h.parquet", index=False)

    # Combined convenience file for Phase 3: forward-fill funding features onto
    # the hourly grid. direction="backward" means a print at time T only fills
    # bars >= T, never before -- no lookahead introduced by the join itself.
    merged = pd.merge_asof(
        ohlcv,
        funding[["datetime", "fundingRate", "funding_zscore_90d", "funding_percentile_90d"]],
        on="datetime",
        direction="backward",
    )
    merged["is_funding_settlement"] = merged["datetime"].isin(set(funding["datetime"]))
    merged.to_parquet(PROCESSED_DIR / "features_1h.parquet", index=False)

    n_warmup = funding["funding_zscore_90d"].isna().sum()
    print(f"ATR(14): {ohlcv['atr_14'].notna().sum()}/{len(ohlcv)} bars valid (first 14 are NaN warmup)")
    print(f"Funding z-score/percentile (90d/270-print trailing window, min_periods=30): "
          f"{n_warmup} prints NaN (warmup, min_periods not yet met) out of {len(funding)}")
    print(f"Wrote data/processed/ohlcv_features_1h.parquet, funding_features_8h.parquet, features_1h.parquet")


if __name__ == "__main__":
    main()
