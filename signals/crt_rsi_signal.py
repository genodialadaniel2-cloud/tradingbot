"""Combined signal: RSI 4H zone (regime filter) + CRT candle pattern (trigger).

Spec (user-specified):
- OVERBOUGHT and STRONG tokens are checked only for the CRT bearish scenario
  (STRONG is the 60-70 RSI band directly below OVERBOUGHT -- see
  features/rsi_heatmap.py's classify_rsi_zone -- and shares its lean).
- OVERSOLD tokens are checked only for the CRT bullish scenario.
- WEAK tokens (the residual 30-60 middle band) are not checked at all, same
  role the old NEUTRAL zone played -- cuts alert volume to the zones that
  actually matter.
- CRT is evaluated on 4H candles only.
- A Telegram alert fires only when CRT confirms -- the RSI zone alone is
  not sent as an alert, it's the filter that decides which scenario to
  check for on a given token.

Manual-trigger model (temporary, while the bot runs from a local one-shot
script instead of a continuous/scheduled poller -- see CLAUDE.md): every
run only evaluates whatever the two most-recently-closed 4H candles are
*at trigger time*, e.g. triggering at 4:30PM checks the 12:00PM and 4:00PM
candles. There is no backfill scan across older candles and no staleness
cutoff, because there's no "missed poll" to catch up on -- each trigger is
by definition checking the current state, not replaying history.
"""
from dataclasses import dataclass

import ccxt
import pandas as pd

from data.live_fetch import fetch_latest_ohlcv
from features.crt import CRTEvent, find_crt_events
from monitoring.dedupe import already_alerted, dedupe_key

EXCHANGE_ID = "binanceusdm"
CRT_TIMEFRAMES = ("4h",)
CRT_FETCH_LIMIT = 5  # small buffer over 2 -- fetch_latest_ohlcv trims one still-forming candle, this just guarantees 2 closed ones remain

ZONE_TO_SCENARIO = {
    "OVERBOUGHT": "bearish",
    "STRONG": "bearish",
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
                df = df.tail(2)  # only the two most-recently-closed candles matter for a one-shot manual trigger
                events = find_crt_events(df, symbol=row["symbol"], timeframe=timeframe, scenario=scenario)
            except Exception:
                # One symbol/timeframe failing (network blip, delisted
                # mid-scan, etc.) must not take down the whole scan.
                continue
            for event in events:
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
