# Journal

Trade/decision journal for this project. Newest entries at top.

## 2026-07-16 — Dropped 1H CRT checks, 4H only

**Change:** `CRT_TIMEFRAMES` in `signals/crt_rsi_signal.py` went from `("1h", "4h")` to `("4h",)`. `features/crt.py`'s detector itself is untouched and still generically supports either timeframe — only the call site changed.

**Why:** user's call, on top of the NEUTRAL-zone volume cut above — narrows the trigger to the timeframe that matches the RSI zone filter's own 4H cadence, cutting alert volume further (roughly halves CRT fetch/check volume per cycle too, since each symbol was being checked on two timeframes before).

## 2026-07-16 — Dropped the WEAK/NEUTRAL RSI zone from CRT checks

**Change:** the middle RSI band (30-70, previously labeled WEAK) is no longer mapped to a CRT scenario in `signals/crt_rsi_signal.py`'s `ZONE_TO_SCENARIO`. Renamed to NEUTRAL in `classify_rsi_zone` (`features/rsi_heatmap.py`) to reflect that it's now just "not checked," not a third alert scenario. Only OVERBOUGHT (→ CRT bearish) and OVERSOLD (→ CRT bullish) are evaluated now.

**Why:** the live test run hit 261 confirmations in a single hourly cycle across the full ~650-symbol universe — too much alert volume. The middle band was the largest contributor since it covers most of any token's time. User's call: focus alerts on the two extreme zones only.

## 2026-07-16 — Signal-bot pivot: RSI zone + CRT, then adversarial audit

**Context:** after four hypotheses (v1-v4) were all rejected at the backtest gate (see [[../RESEARCH_LOG.md|RESEARCH_LOG]] and `HYPOTHESIS_v1-4_REJECTED.md`), decided finding a standalone tradeable edge was too hard to keep chasing. Pivoted the whole project goal from a self-trading strategy bot to a **Telegram signal-alert bot** — no execution, human reads the alert and decides. Full technical detail and current architecture live in `[[../CLAUDE.md|CLAUDE.md]]`, kept current throughout; this entry is the narrative of how we got there and why.

### Signal design (user-specified, Claude built the infra only)
- **RSI zone (4H, regime filter):** OVERBOUGHT (≥70) / WEAK / OVERSOLD (≤30), free self-computed replacement for Coinglass's paid RSI Heatmap (their API needs $299/mo; RSI itself isn't proprietary data).
- **CRT — Candle Range Theory (1H/4H only, trigger):** candle 2 sweeps candle 1's high (bearish) or low (bullish) then closes back inside candle 1's range → confirmed, target zone = candle 1's range.
- **Combined rule:** OVERBOUGHT → CRT bearish only; WEAK/OVERSOLD → CRT bullish only. Alert fires only on CRT confirmation, never on RSI zone alone.

### Cross-checked against Coinglass directly, twice
User shared real Coinglass screenshots (overbought list, oversold scatter) to validate. Found and fixed real discrepancies rather than assuming our numbers were right:
- Binance lists tokenized-equity perpetuals (IBM, Cisco, Eli Lilly, CoreWeave, Astera Labs, SK Hynix, SanDisk as `TRADIFI_PERPETUAL` contracts) mixed into the same crypto perpetual market — excluded.
- A coin (AKE) showed RSI 90+ from a real +197% single-candle pump, not a bug — but it exposed that pump-inflated volume was pulling thin-liquidity coins into a "top 30 by volume" universe. Added an anomaly filter (>30% intrabar move excludes a symbol).
- Coinglass's RSI is *live* (includes the still-forming candle) — ours was closed-bar only, an 5-15pt gap. Fixed to match (verified within ~0.02-2 pts across ~30 real symbols). CRT stayed closed-bar only, correctly — its own definition needs a finished candle.
- "Most overbought right now" doesn't correlate with "highest volume" — 11 of Coinglass's own 15 overbought coins weren't even in our top-30-by-volume universe. Switched to scanning the full ~650-symbol Binance perpetual universe (~70-150s/scan, fine for an hourly poll).

### Adversarial audit, on request ("near-perfect, assume guilty until proven innocent")
Read every file in the pipeline adversarially, reported 14 findings via structured review, fixed all of them, added tests (57 → 88 passing). The two worst: the whole poll loop had zero exception handling (one bad API call out of ~2000/hour would've killed the bot permanently), and dedupe was marking a signal "alerted" *before* confirming the Telegram send actually succeeded (a failed send would've been silently lost forever, never retried).

Then ran the real thing end-to-end against live Binance data three times, and **live testing found 2 more bugs the code-reading audit missed**:
- Binance lists non-Latin-script perpetuals (Chinese-character meme coins, e.g. `币安人生`) that crashed on Windows' default console/file encoding — forced UTF-8 everywhere.
- The CRT backfill fix (added during the audit, to survive a missed poll) had no staleness bound — a cold start replayed 2 days of history as 2440 simultaneous "new" signals in one run. Added a 3h cutoff, verified live: 2440 → 261.

**Lesson worth remembering:** the 14 code-audit findings were all real and worth doing, but they weren't sufficient — running the actual pipeline against live data surfaced two more genuine bugs that adversarial reading alone didn't catch. Both passes matter.

### Where this left off
Telegram is not yet connected (`notify/telegram_bot.py` correctly raises a clear error until `.env` has `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`). That's the next session's starting point.

## See also
- [[../CLAUDE.md|CLAUDE.md]] — living technical source of truth, architecture, structure, open decisions
- [[research]] — market/data-source notes (not yet started)
- [[strategies]] — strategy ideas and specs (not yet started; note the project's current stance is alerts, not strategies)
