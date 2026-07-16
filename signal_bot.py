"""Signal bot runner.

Pipeline: RSI 4H zone snapshot (regime filter) -> CRT candle pattern on 1H/4H
(trigger) -> Telegram alert only when CRT confirms.
  OVERBOUGHT tokens -> checked for CRT bearish only
  OVERSOLD tokens -> checked for CRT bullish only
  NEUTRAL tokens -> not checked at all
See signals/crt_rsi_signal.py for the combined rule.

Reliability notes (see CLAUDE.md's signal-bot audit entry for the full list
this addresses):
- One shared ccxt exchange instance per cycle, so its rate limiter actually
  coordinates across the RSI scan and the CRT checks instead of each
  fetch creating its own uncoordinated one.
- One exchange.fetch_time() call per cycle bounds forming-candle detection
  to server time instead of the local machine clock, which can drift.
- A confirmed CRT is only marked as alerted (monitoring.dedupe.mark_alerted)
  AFTER send_message succeeds -- a failed send is retried next cycle
  rather than silently treated as delivered.
- Both the whole cycle (main) and each individual send (run_once) are
  wrapped so one bad symbol, one Telegram hiccup, or one network blip
  can't take the bot down permanently.
"""
import sys
import time

import ccxt

from features.rsi_heatmap import build_rsi_zone_snapshot
from monitoring.dedupe import dedupe_key, mark_alerted
from monitoring.logger import log_heartbeat, log_signal
from notify.telegram_bot import send_message
from signals.crt_rsi_signal import find_combined_signals, format_combined_signal_message

# Binance lists perpetuals with non-Latin-script tickers (e.g. Chinese-
# character meme coins) that pass the crypto-perpetual filter same as any
# other symbol. Windows' default console/file encoding (cp1252 here) can't
# represent them, and a bare print() containing one would crash outright --
# discovered via a full-universe live run. Reconfigure early so a
# diagnostic message mentioning one of these tickers degrades to '?' rather
# than taking the whole bot down.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

EXCHANGE_ID = "binanceusdm"
RSI_TIMEFRAME = "4h"
N_SYMBOLS = None  # None = full crypto perpetual universe (~650+), see get_top_symbols
POLL_SECONDS = 60 * 60  # hourly, so a new 1H CRT candle is caught promptly


def run_once() -> None:
    exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
    exchange.load_markets()
    now_ms = exchange.fetch_time()  # one server-time reference for this whole cycle

    snapshot = build_rsi_zone_snapshot(n_symbols=N_SYMBOLS, timeframe=RSI_TIMEFRAME, exchange=exchange)
    combined = find_combined_signals(snapshot, exchange=exchange, now_ms=now_ms)

    sent = 0
    send_errors = 0
    for cs in combined:
        message = format_combined_signal_message(cs)
        try:
            send_message(message)
        except Exception as e:
            # Deliberately do NOT mark_alerted here -- an undelivered signal
            # must stay eligible for retry next cycle, not be silently
            # treated as sent.
            print(f"signal_bot: failed to send alert for {cs.symbol}, will retry next cycle: {e}")
            send_errors += 1
            continue
        mark_alerted(dedupe_key(cs.symbol, cs.crt.timeframe, cs.crt.scenario), cs.crt.candle_close_time)
        log_signal(f"crt_{cs.crt.scenario}", direction=cs.crt.scenario, message=message)
        sent += 1

    log_heartbeat(scanned=len(snapshot), signals_found=len(combined), signals_sent=sent, errors=send_errors)


def main() -> None:
    while True:
        try:
            run_once()
        except Exception as e:
            # A single bad cycle (exchange outage, etc.) must not end the
            # bot -- log it and try again next cycle rather than crash.
            print(f"signal_bot: run_once() failed, will retry next cycle: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if "--once" in sys.argv:
        # Single-cycle mode for a scheduler that provides the loop itself
        # (e.g. GitHub Actions cron) instead of a long-lived process.
        run_once()
    else:
        main()
