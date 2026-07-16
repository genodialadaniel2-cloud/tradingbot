"""
Phase 2 (v2 hypothesis): compute the volatility-compression feature that's
fixed-window (30-day trailing ATR-%-of-price percentile). The breakout range
window (N hours) is a swept Phase 3 parameter, so rolling_prior_range() is
computed on the fly inside the engine for whichever N is being tested, rather
than precomputed here for one fixed value.

Reads only data/processed/ (in-sample), never data/holdout/.
"""

from pathlib import Path

import pandas as pd

from features.indicators import atr, volatility_percentile

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def main():
    ohlcv = pd.read_parquet(PROCESSED_DIR / "ohlcv_1h.parquet")
    ohlcv = ohlcv.sort_values("datetime").reset_index(drop=True)

    ohlcv["atr_14"] = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)
    ohlcv["vol_percentile_30d"] = volatility_percentile(ohlcv["atr_14"], ohlcv["close"])

    # v2's signal doesn't use funding at all, but it's still a perp position --
    # funding payments while held are a real cost/tailwind and must be modeled
    # regardless of what the entry signal is (per CLAUDE.md's Phase 3 gate).
    funding = pd.read_parquet(PROCESSED_DIR / "funding_rate_8h.parquet").sort_values("datetime").reset_index(drop=True)
    ohlcv = pd.merge_asof(ohlcv, funding[["datetime", "fundingRate"]], on="datetime", direction="backward")
    ohlcv["is_funding_settlement"] = ohlcv["datetime"].isin(set(funding["datetime"]))

    ohlcv.to_parquet(PROCESSED_DIR / "features_v2_1h.parquet", index=False)

    n_warmup = ohlcv["vol_percentile_30d"].isna().sum()
    print(f"ATR(14): {ohlcv['atr_14'].notna().sum()}/{len(ohlcv)} bars valid")
    print(f"Vol percentile (30d/720h trailing window, min_periods=168): {n_warmup} bars NaN (warmup) out of {len(ohlcv)}")
    print("Wrote data/processed/features_v2_1h.parquet")


if __name__ == "__main__":
    main()
