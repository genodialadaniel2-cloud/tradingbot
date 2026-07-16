"""
Phase 1 cleaning step: reads ONLY data/raw/ (the in-sample slice fetch_data.py
already split off from the holdout) and produces gap-checked, timestamp-aligned
output in data/processed/. Never reads data/holdout/ -- this script and every
script downstream of it in this session must not touch that directory.

Regeneratable: re-run any time after fetch_data.py to rebuild data/processed/
from data/raw/ with no network calls.
"""

import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

ONE_HOUR_MS = 60 * 60 * 1000
EIGHT_HOURS_MS = 8 * ONE_HOUR_MS


def check_ohlcv_gaps(df):
    ts = df["timestamp"].to_numpy()
    diffs = ts[1:] - ts[:-1]
    gap_idx = (diffs != ONE_HOUR_MS).nonzero()[0]
    gaps = []
    for i in gap_idx:
        gaps.append(
            {
                "after_ts": int(ts[i]),
                "after_iso": pd.to_datetime(ts[i], unit="ms", utc=True).isoformat(),
                "before_next_iso": pd.to_datetime(ts[i + 1], unit="ms", utc=True).isoformat(),
                "gap_hours": (int(diffs[i]) / ONE_HOUR_MS),
            }
        )
    return gaps


def check_funding_gaps(df):
    ts = df["timestamp"].to_numpy()
    diffs = ts[1:] - ts[:-1]
    # allow small millisecond jitter Binance sometimes adds to funding timestamps
    tolerance_ms = 5000
    gap_idx = (abs(diffs - EIGHT_HOURS_MS) > tolerance_ms).nonzero()[0]
    gaps = []
    for i in gap_idx:
        gaps.append(
            {
                "after_ts": int(ts[i]),
                "after_iso": pd.to_datetime(ts[i], unit="ms", utc=True).isoformat(),
                "before_next_iso": pd.to_datetime(ts[i + 1], unit="ms", utc=True).isoformat(),
                "gap_hours": (int(diffs[i]) / ONE_HOUR_MS),
            }
        )
    return gaps


def main():
    ohlcv = pd.read_parquet(RAW_DIR / "ohlcv_1h.parquet")
    funding = pd.read_parquet(RAW_DIR / "funding_rate.parquet")

    ohlcv = ohlcv.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    funding = funding.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    ohlcv["datetime"] = pd.to_datetime(ohlcv["timestamp"], unit="ms", utc=True)
    funding["datetime"] = pd.to_datetime(funding["timestamp"], unit="ms", utc=True)

    ohlcv_gaps = check_ohlcv_gaps(ohlcv)
    funding_gaps = check_funding_gaps(funding)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ohlcv.to_parquet(PROCESSED_DIR / "ohlcv_1h.parquet", index=False)
    funding.to_parquet(PROCESSED_DIR / "funding_rate_8h.parquet", index=False)

    # Convenience join for Phase 2/3: forward-fill the last *known* funding print
    # onto the hourly grid. No lookahead -- a print at time T is only ever
    # forward-filled into bars at or after T, never before.
    merged = pd.merge_asof(
        ohlcv.sort_values("datetime"),
        funding[["datetime", "fundingRate"]].sort_values("datetime"),
        on="datetime",
        direction="backward",
    )
    merged.to_parquet(PROCESSED_DIR / "ohlcv_1h_with_funding.parquet", index=False)

    gap_report = {
        "ohlcv_rows": len(ohlcv),
        "ohlcv_gaps_found": len(ohlcv_gaps),
        "ohlcv_gaps": ohlcv_gaps,
        "funding_rows": len(funding),
        "funding_gaps_found": len(funding_gaps),
        "funding_gaps": funding_gaps,
        "date_range_start_utc": ohlcv["datetime"].min().isoformat(),
        "date_range_end_utc": ohlcv["datetime"].max().isoformat(),
    }
    (PROCESSED_DIR / "_gap_report.json").write_text(json.dumps(gap_report, indent=2))

    print(f"OHLCV: {len(ohlcv)} rows, {len(ohlcv_gaps)} gap(s) found")
    for g in ohlcv_gaps:
        print(f"  gap: {g['after_iso']} -> {g['before_next_iso']} ({g['gap_hours']:.1f}h)")
    print(f"Funding: {len(funding)} rows, {len(funding_gaps)} gap(s) found")
    for g in funding_gaps:
        print(f"  gap: {g['after_iso']} -> {g['before_next_iso']} ({g['gap_hours']:.1f}h)")
    print(f"\nWrote data/processed/ohlcv_1h.parquet, funding_rate_8h.parquet, ohlcv_1h_with_funding.parquet, _gap_report.json")


if __name__ == "__main__":
    main()
