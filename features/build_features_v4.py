"""
Phase 2 (v4 hypothesis): daily ATR(14) for the stop. The trend-signal lookback
(K days) is a swept Phase 3 parameter, so trailing_return() is computed on the
fly inside the engine for whichever K is being tested, same pattern v2/v3
used for their swept window parameters.

Reads only data/processed/ohlcv_1d.parquet (in-sample, resampled by
data/resample_daily.py), never data/holdout/.
"""

from pathlib import Path

import pandas as pd

from features.indicators import atr

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def main():
    df = pd.read_parquet(PROCESSED_DIR / "ohlcv_1d.parquet").sort_values("datetime").reset_index(drop=True)

    df["atr_14"] = atr(df["high"], df["low"], df["close"], period=14)

    df.to_parquet(PROCESSED_DIR / "features_v4_1d.parquet", index=False)

    n_warmup = df["atr_14"].isna().sum()
    print(f"ATR(14) on daily bars: {df['atr_14'].notna().sum()}/{len(df)} bars valid ({n_warmup} warmup)")
    print("Wrote data/processed/features_v4_1d.parquet")


if __name__ == "__main__":
    main()
