"""
Phase 2 (v3 hypothesis): compute the move-magnitude percentile (fixed 30-day
trailing window) and the calendar-only low-liquidity-window flag. The
regime_filter used to run the low-liquidity treatment vs. high-liquidity
control comparison is a Phase 3 engine parameter, not a feature.

Reads only data/processed/ (in-sample), never data/holdout/.
"""

from pathlib import Path

import pandas as pd

from features.indicators import abs_return_percentile, atr, is_low_liquidity_window

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def main():
    ohlcv = pd.read_parquet(PROCESSED_DIR / "ohlcv_1h.parquet")
    ohlcv = ohlcv.sort_values("datetime").reset_index(drop=True)

    ohlcv["atr_14"] = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)
    ohlcv["bar_return_1h"] = ohlcv["close"].pct_change()
    ohlcv["abs_return_percentile_30d"] = abs_return_percentile(ohlcv["close"])
    ohlcv["is_low_liquidity"] = is_low_liquidity_window(ohlcv["datetime"])

    # v3's signal doesn't use funding at all, but it's still a perp position --
    # funding payments while held are a real cost/tailwind and must be modeled
    # regardless of what the entry signal is (per CLAUDE.md's Phase 3 gate).
    funding = pd.read_parquet(PROCESSED_DIR / "funding_rate_8h.parquet").sort_values("datetime").reset_index(drop=True)
    ohlcv = pd.merge_asof(ohlcv, funding[["datetime", "fundingRate"]], on="datetime", direction="backward")
    ohlcv["is_funding_settlement"] = ohlcv["datetime"].isin(set(funding["datetime"]))

    ohlcv.to_parquet(PROCESSED_DIR / "features_v3_1h.parquet", index=False)

    n_warmup = ohlcv["abs_return_percentile_30d"].isna().sum()
    print(f"ATR(14): {ohlcv['atr_14'].notna().sum()}/{len(ohlcv)} bars valid")
    print(f"Abs-return percentile (30d/720h trailing window, min_periods=168): {n_warmup} bars NaN (warmup) out of {len(ohlcv)}")
    print(f"Low-liquidity window bars: {ohlcv['is_low_liquidity'].sum()}/{len(ohlcv)} ({ohlcv['is_low_liquidity'].mean():.1%})")
    print("Wrote data/processed/features_v3_1h.parquet")


if __name__ == "__main__":
    main()
