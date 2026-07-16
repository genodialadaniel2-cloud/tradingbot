"""Combined signal: RSI 4H zone (regime filter) + CRT candle pattern (trigger).

Spec (user-specified):
- OVERBOUGHT tokens are checked only for the CRT bearish scenario.
- OVERSOLD tokens are checked only for the CRT bullish scenario.
- NEUTRAL tokens are not checked at all (cuts alert volume to just the two
  zones that matter).
- CRT is evaluated on 4H candles only.
- A Telegram alert fires only when CRT confirms -- the RSI zone alone is
  not sent as an alert, it's the filter that decides which scenario to
  check for on a given token.
"""
from dataclasses import dataclass

import ccxt
import pandas as pd

from data.live_fetch import fetch_latest_ohlcv
from features.crt import CRTEvent, find_crt_events
from monitoring.dedupe import already_alerted, dedupe_key

EXCHANGE_ID = "binanceusdm"
CRT_TIMEFRAMES = ("4h",)
CRT_FETCH_LIMIT = 12  # candles scanned per timeframe -- more than 2 so a missed poll or two doesn't permanently lose a confirmation
MAX_SIGNAL_AGE_MS = 3 * 60 * 60 * 1000  # 3h: covers a missed poll or two at the hourly cadence, without replaying old history as fresh -- verified live: without this, a cold start (empty dedupe state) replayed up to 2 days of 4H history as 2440 "new" signals at once

ZONE_TO_SCENARIO = {
    "OVERBOUGHT": "bearish",
    "OVERSOLD": "bullish",
}


@dataclass
class CombinedSignal:
    symbol: str
    zone: str
    rsi: float
    crt: CRTEvent


def find_combined_signals(
    zone_snapshot: pd.DataFrame,
    exchange: ccxt.Exchange | None = None,
    now_ms: int | None = None,
) -> list[CombinedSignal]:
    """zone_snapshot: output of features.rsi_heatmap.build_rsi_zone_snapshot
    (columns symbol, rsi, zone). Returns confirmations not already alerted
    (monitoring.dedupe.already_alerted is only a read here) -- the CALLER
    is responsible for calling monitoring.dedupe.mark_alerted only after
    successfully delivering each one, so a failed send can be retried next
    cycle instead of being silently treated as delivered.

    Pass `exchange`/`now_ms` through from the caller's single poll-cycle
    instance/server-time reference rather than letting each fetch create
    its own (see data/live_fetch.py's fetch_latest_ohlcv).
    """
    owns_exchange = exchange is None
    if owns_exchange:
        exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
    reference_now_ms = now_ms if now_ms is not None else exchange.milliseconds()

    results = []
    for _, row in zone_snapshot.iterrows():
        scenario = ZONE_TO_SCENARIO.get(row["zone"])
        if scenario is None:  # UNKNOWN zone -- not enough RSI history yet
            continue
        for timeframe in CRT_TIMEFRAMES:
            try:
                df = fetch_latest_ohlcv(
                    exchange, row["symbol"], timeframe=timeframe, limit=CRT_FETCH_LIMIT, now_ms=now_ms
                )
                events = find_crt_events(df, symbol=row["symbol"], timeframe=timeframe, scenario=scenario)
            except Exception:
                # One symbol/timeframe failing (network blip, delisted
                # mid-scan, etc.) must not take down the whole scan.
                continue
            for event in events:
                if reference_now_ms - event.candle_close_time > MAX_SIGNAL_AGE_MS:
                    continue  # too old to alert on as if it just happened (see MAX_SIGNAL_AGE_MS)
                key = dedupe_key(row["symbol"], timeframe, scenario)
                if already_alerted(key, event.candle_close_time):
                    continue
                results.append(CombinedSignal(symbol=row["symbol"], zone=row["zone"], rsi=row["rsi"], crt=event))
    return results


def format_combined_signal_message(cs: CombinedSignal) -> str:
    base = cs.symbol.split("/")[0]
    direction = "🔴 SHORT setup" if cs.crt.scenario == "bearish" else "🟢 LONG setup"
    return (
        f"*{base}* — {direction}\n"
        f"RSI 4H: {cs.rsi:.1f} ({cs.zone})\n"
        f"CRT confirmed on {cs.crt.timeframe}: swept {cs.crt.sweep_level:.4g}, "
        f"closed back at {cs.crt.close_price:.4g}\n"
        f"Target zone: {cs.crt.range_low:.4g} - {cs.crt.range_high:.4g}"
    )
