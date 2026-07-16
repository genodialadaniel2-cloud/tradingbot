"""
Phase 1 data pull: BTC/USDT perpetual (Binance USDM futures) 1H OHLCV + funding
rate history via ccxt public endpoints (no API key required).

Holdout ordering is enforced here, not downstream: the most recent ~25% of the
pulled history is split off into data/holdout/ in this same script, before any
cleaning/resampling touches the data. Everything under data/holdout/ must stay
untouched until Phase 3's single final validation run.

Re-run this script any time to refresh data/raw/ and data/holdout/ from the
exchange; it does not depend on anything in data/processed/.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd

EXCHANGE_ID = "binanceusdm"
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1h"
START_DATE = "2022-01-01T00:00:00Z"  # ~4.5 years of history as of 2026-07-14, well over the 2-year minimum
HOLDOUT_FRACTION = 0.25  # middle of the instructed 20-30% range

RAW_DIR = Path(__file__).parent / "raw"
HOLDOUT_DIR = Path(__file__).parent / "holdout"


def fetch_ohlcv_paginated(exchange, symbol, timeframe, since_ms):
    all_rows = []
    limit = 1500
    now_ms = exchange.milliseconds()
    cursor = since_ms
    while cursor < now_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
    return all_rows


def fetch_funding_rate_history_paginated(exchange, symbol, since_ms):
    all_rows = []
    limit = 1000
    now_ms = exchange.milliseconds()
    cursor = since_ms
    while cursor < now_ms:
        batch = exchange.fetch_funding_rate_history(symbol, since=cursor, limit=limit)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
    return all_rows


def main():
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    exchange.load_markets()
    assert SYMBOL in exchange.markets, f"{SYMBOL} not found on {EXCHANGE_ID}"

    since_ms = exchange.parse8601(START_DATE)

    print(f"Fetching {TIMEFRAME} OHLCV for {SYMBOL} since {START_DATE} ...")
    ohlcv_raw = fetch_ohlcv_paginated(exchange, SYMBOL, TIMEFRAME, since_ms)
    ohlcv_df = pd.DataFrame(ohlcv_raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    ohlcv_df = ohlcv_df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    print(f"  -> {len(ohlcv_df)} hourly bars")

    print(f"Fetching funding rate history for {SYMBOL} since {START_DATE} ...")
    funding_raw = fetch_funding_rate_history_paginated(exchange, SYMBOL, since_ms)
    funding_df = pd.DataFrame(
        [{"timestamp": r["timestamp"], "datetime": r["datetime"], "fundingRate": r["fundingRate"], "symbol": r["symbol"]} for r in funding_raw]
    )
    funding_df = funding_df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    print(f"  -> {len(funding_df)} funding prints")

    # Bound both series to their mutual overlap so the split boundary is meaningful for both.
    overall_start = max(ohlcv_df["timestamp"].min(), funding_df["timestamp"].min())
    overall_end = min(ohlcv_df["timestamp"].max(), funding_df["timestamp"].max())
    ohlcv_df = ohlcv_df[(ohlcv_df["timestamp"] >= overall_start) & (ohlcv_df["timestamp"] <= overall_end)].reset_index(drop=True)
    funding_df = funding_df[(funding_df["timestamp"] >= overall_start) & (funding_df["timestamp"] <= overall_end)].reset_index(drop=True)

    split_boundary_ms = int(overall_start + (1 - HOLDOUT_FRACTION) * (overall_end - overall_start))
    split_boundary_iso = datetime.fromtimestamp(split_boundary_ms / 1000, tz=timezone.utc).isoformat()

    ohlcv_insample = ohlcv_df[ohlcv_df["timestamp"] < split_boundary_ms].reset_index(drop=True)
    ohlcv_holdout = ohlcv_df[ohlcv_df["timestamp"] >= split_boundary_ms].reset_index(drop=True)
    funding_insample = funding_df[funding_df["timestamp"] < split_boundary_ms].reset_index(drop=True)
    funding_holdout = funding_df[funding_df["timestamp"] >= split_boundary_ms].reset_index(drop=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)

    ohlcv_insample.to_parquet(RAW_DIR / "ohlcv_1h.parquet", index=False)
    funding_insample.to_parquet(RAW_DIR / "funding_rate.parquet", index=False)
    ohlcv_holdout.to_parquet(HOLDOUT_DIR / "ohlcv_1h.parquet", index=False)
    funding_holdout.to_parquet(HOLDOUT_DIR / "funding_rate.parquet", index=False)

    fetched_at = datetime.now(timezone.utc).isoformat()
    common_meta = {
        "exchange": EXCHANGE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "ccxt_version": ccxt.__version__,
        "fetched_at_utc": fetched_at,
        "overall_start_utc": datetime.fromtimestamp(overall_start / 1000, tz=timezone.utc).isoformat(),
        "overall_end_utc": datetime.fromtimestamp(overall_end / 1000, tz=timezone.utc).isoformat(),
        "split_boundary_utc": split_boundary_iso,
        "holdout_fraction": HOLDOUT_FRACTION,
    }

    raw_meta = dict(common_meta, role="in_sample_raw", ohlcv_rows=len(ohlcv_insample), funding_rows=len(funding_insample))
    holdout_meta = dict(common_meta, role="holdout_raw_DO_NOT_TOUCH_UNTIL_FINAL_VALIDATION", ohlcv_rows=len(ohlcv_holdout), funding_rows=len(funding_holdout))

    (RAW_DIR / "_meta.json").write_text(json.dumps(raw_meta, indent=2))
    (HOLDOUT_DIR / "_meta.json").write_text(json.dumps(holdout_meta, indent=2))

    print(f"\nSplit boundary: {split_boundary_iso}")
    print(f"In-sample:  {len(ohlcv_insample)} OHLCV bars, {len(funding_insample)} funding prints -> data/raw/")
    print(f"Holdout:    {len(ohlcv_holdout)} OHLCV bars, {len(funding_holdout)} funding prints -> data/holdout/")


if __name__ == "__main__":
    main()
