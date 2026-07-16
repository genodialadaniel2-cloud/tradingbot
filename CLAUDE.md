# TradingBot

> Status: **signal bot, not a strategy bot.** After four independent hypotheses (v1-v4 — funding-extreme reversion, volatility-breakout continuation, liquidity-regime reversion, daily time-series momentum) all failed the backtest gate (see `RESEARCH_LOG.md`), the project pivoted away from finding a standalone tradeable edge. The new goal is simpler and lower-risk: watch BTC and push a Telegram alert when a condition fires. No auto-execution exists or is planned as part of this. This file is the source of truth for how Claude should work here — keep it current as decisions change, don't let it drift from what's built.

## What this is

- **Target market:** BTC perpetual futures (Binance USDⓈ-M via ccxt, symbol `BTC/USDT:USDT`) — same data source as the earlier strategy work, reused here.
- **What it does:** polls recent OHLCV, evaluates a set of signal rules against it, and sends a Telegram message when one fires. Nothing places an order. A human reads the alert and decides what, if anything, to do.
- **Signal logic is user-designed.** Claude's job is the infrastructure — data fetch, the evaluation loop, Telegram delivery, logging — not inventing indicator/entry rules unprompted. When asked to add a signal, implement exactly what's specified; don't embellish with extra conditions "to be safe."
- **Language / runtime:** Python 3.14, repo-local `.venv/` (unchanged from before).

## Working agreements

- **Secrets never get committed.** Telegram bot token and chat id go in untracked `.env` (see `.env.example` for the shape), never in source or committed config. If exchange API keys are ever added, same rule.
- **No execution path exists, and none should be added without an explicit, separate conversation.** If this bot ever grows an order-placement path, treat that the way the old plan treated live trading: high blast radius, needs its own confirmation and a paper-trading gate before real money — don't let "just one small automation" creep in silently as part of an unrelated signal change.
- **State the reasoning when adding a signal.** Even without a backtest gate, note what condition triggers it and why it's meaningful — unexplained rules are hard to audit later, same principle as before, just without the phase gate forcing it.
- **The old backtest pipeline is still there if wanted.** If a signal's historical hit rate needs sanity-checking before trusting it, `backtest/` and `data/` (built for v1-v4) still work for that. If used, the same discipline applies: walk-forward not single-window, and treat a suspiciously good result (win rate >~70%, Sharpe >3) as a bug to audit, not a win.
- **Proactively flag lookahead bias** in any signal logic — e.g. `Signal.check()` must only look at bars already closed, never the forming bar.

## Structure

```
data/
  fetch_data.py     # historical bulk pull + holdout split (v1-v4 research pipeline, kept)
  live_fetch.py     # latest-N-bars fetch for the live signal loop -- takes a shared exchange instance + now_ms
  process_data.py, resample_daily.py
  raw/ processed/ holdout/
features/
  indicators.py     # rsi(), atr(), is_anomalous_candle() -- shared building blocks
  rsi_heatmap.py    # universe selection + RSI 4H zone snapshot (regime filter)
  crt.py            # CRT candle pattern detection (trigger), incl. multi-candle backfill scan
  build_features*.py
backtest/            # v1-v4 research artifacts + reusable engine/metrics, kept for optional validation
signals/
  crt_rsi_signal.py # combines RSI zone + CRT into the one signal that's actually wired up
notify/
  telegram_bot.py   # push-only Telegram delivery (send_message)
monitoring/
  logger.py         # append-only JSONL log of every fired signal + a heartbeat.jsonl health line per cycle
  dedupe.py         # tracks last-alerted candle per (symbol, timeframe, scenario), atomic writes
signal_bot.py        # the runner: one shared exchange/server-time per cycle -> RSI scan -> CRT check -> notify; `--once` for a single cycle (GitHub Actions), default is the infinite loop (local/VPS)
.github/workflows/
  signal_bot.yml     # hourly cron (+ manual workflow_dispatch) running `signal_bot.py --once` on GitHub's free runners -- 24/7 without the PC on
requirements-bot.txt # slim deps for the Actions runner (ccxt/pandas/numpy/python-dotenv/requests) -- excludes ta-lib, which needs a system lib the runner doesn't have and nothing in the bot's code path imports
tests/
notebooks/
HYPOTHESIS_v1-4_REJECTED.md, RESEARCH_LOG.md   # history of the abandoned strategy search
.env.example         # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (local/VPS use; Actions uses repo secrets instead)
```

**Retired:** `strategy/`, `risk/`, `execution/` (were empty — no strategy ever reached Phase 4) removed. Those belonged to the auto-execution build-out (position sizing, circuit breakers, paper/live trading) that no longer applies now that the bot only alerts.

## Setup for Telegram delivery

1. Create a bot via @BotFather on Telegram, get the bot token.
2. Message the bot once, then `GET https://api.telegram.org/bot<token>/getUpdates` to find the chat id.
3. Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`. Never commit `.env`.

## History (why v1-v4 were abandoned)

Four independent mechanisms, two timeframes (1H and daily), all tested with an event-driven backtest engine, realistic costs, and walk-forward validation — all rejected. Full detail in `RESEARCH_LOG.md`; short version: intraday mechanisms (v1-v3) died to cost drag from high trade frequency; the daily-bar pivot (v4) dropped frequency as intended but died instead to variance/thin sample size, with the entire aggregate profit riding on one trending window. Four independent rejections across two timeframes was treated as a strong signal that finding a standalone rule-based directional edge on this instrument/data was too hard to keep chasing — hence this pivot to alerts instead of a self-trading strategy.

## Tooling in this repo

- **Obsidian vault:** this folder is also configured as an Obsidian vault (`.obsidian/`) for research notes, strategy journals, and trade post-mortems. Markdown notes belong in `notes/`.
- **Graphify:** a knowledge graph of this folder's content is maintained via the `graphify` skill — see `graphify-out/` once generated. Treat existing `graphify-out/` as a first stop for "how does X relate to Y" questions before re-deriving from scratch.
- **TradingView MCP:** `tradingview-mcp/` (cloned from tradesdontlie/tradingview-mcp) gives Claude tool access to a locally running TradingView Desktop instance via Chrome DevTools Protocol, for chart reading, Pine Script development, and alert management. Requires TradingView Desktop installed and launched with `--remote-debugging-port=9222`; see that folder's README for the exact launch script for this OS.

## Open decisions

- ~~Exchange/broker API~~ — **Resolved:** ccxt against `binanceusdm`, symbol `BTC/USDT:USDT`. Public endpoints only, no API key needed for the signal bot.
- ~~Language/runtime~~ — **Resolved:** Python 3.14, repo-local `.venv/`.
- ~~Standalone tradeable edge~~ — **Abandoned:** four hypotheses (v1-v4) rejected; see History above. Not being chased further.
- ~~Signal logic~~ — **Resolved (v1 of the signal logic, user-designed):** RSI 4H zone (`features/rsi_heatmap.py`, OVERBOUGHT/NEUTRAL/OVERSOLD, standard 70/30 thresholds) is a regime filter; a CRT candle pattern (`features/crt.py`, sweep-and-reclaim over 2 candles) is the trigger, checked on 4H only. OVERBOUGHT -> CRT bearish only; OVERSOLD -> CRT bullish only. Combined in `signals/crt_rsi_signal.py`; a Telegram alert fires only when CRT confirms, deduped per closed candle via `monitoring/dedupe.py`. Not backtested — no historical hit-rate check has been run on this combination yet.
- **NEUTRAL (formerly WEAK) zone excluded from CRT checks (2026-07-16):** the middle RSI band (30-70) is no longer mapped to a CRT scenario in `ZONE_TO_SCENARIO` (`signals/crt_rsi_signal.py`) — only OVERBOUGHT and OVERSOLD tokens are checked now. Deliberate volume reduction, not a bug: the middle band was contributing the bulk of alert volume in the 261-signal/cycle test run and the user wants to focus on the two extreme zones.
- **1H CRT check dropped, 4H only (2026-07-16):** `CRT_TIMEFRAMES` in `signals/crt_rsi_signal.py` is now `("4h",)`, down from `("1h", "4h")` — user's call, further alert-volume reduction on top of the NEUTRAL-zone change above. `features/crt.py`'s `detect_crt`/`find_crt_events` are unchanged and still generically support either timeframe; the restriction lives at the call site, not the CRT detector itself.
- **Universe anomaly filter** — added after a live discrepancy check against Coinglass's own RSI heatmap: top-by-volume selection can pull in a low-liquidity coin mid-pump (one real case: AKE, +197% in a single 4H candle, ~400x normal volume, RSI 90+ as a direct result — not a calculation bug, but likely not in Coinglass's tracked universe or reflective of a broader index price). `is_anomalous_candle()` in `features/rsi_heatmap.py` now drops any symbol whose most recent closed candle moved >30% intrabar from its open, before it ever reaches RSI zoning or CRT.
- **RSI methodology and universe, cross-checked against Coinglass directly (2026-07-16):** (1) Coinglass's heatmap is a *live* tool — it includes the still-forming candle, not just closed ones. `features/rsi_heatmap.py` now does the same (verified to match within ~0.02-0.8 RSI points, down from a 5-15pt gap); CRT (`features/crt.py`) is unaffected and still requires closed candles only, since its own definition needs a candle to have actually finished. (2) Top-30-by-volume was hiding real signal — 11 of Coinglass's own 15 Binance-listed "overbought" coins (e.g. FF, BANK, ENS, RUNE, XVS, ZEN, COW, BEAMX, 0G, SLP, ME) fell outside that cut, because "most overbought right now" doesn't correlate with "highest volume." `get_top_symbols`/`build_rsi_zone_snapshot` now default to the full crypto-perpetual universe (~650+ symbols, ~70-90s per scan, well inside the hourly poll budget).
- ~~Multi-exchange parity with Coinglass~~ — **Resolved, scope is Binance-only:** 4 of Coinglass's coins (GNO, WBETH, GNS, QI, DODO) have no Binance perpetual and were never expected to appear here. Not being chased — the bot's universe is, and stays, "every crypto perpetual Binance USDⓈ-M lists," not Coinglass's full cross-exchange set.
- ~~Telegram bot token/chat id~~ — **Resolved (2026-07-16):** bot is @Pakaki_Bot, `.env` has both values, confirmed working with a live test alert delivered.
- **Polling frequency** — `signal_bot.py` polls hourly (`POLL_SECONDS`). Now that CRT is 4H-only (see above), the 4H RSI zone and 4H CRT check just get re-evaluated redundantly within their own window, which is harmless since alerts are deduped per closed candle; hourly is kept mainly to match the GitHub Actions cron cadence.
- **24/7 hosting (2026-07-16):** runs on a GitHub Actions scheduled workflow (`.github/workflows/signal_bot.yml`, hourly cron + manual `workflow_dispatch`) instead of the local PC, so it keeps running when the PC is off. Chosen over a paid VPS/Oracle Cloud (couldn't create an account) and Render (no genuine free tier for a persistent worker or disk-backed cron job — checked their docs directly rather than assuming). Repo is public: checked every markdown file for secrets/PII first, found none — the token/chat id live only in GitHub's encrypted Actions secrets, never in a committed file.
  - Runs `python signal_bot.py --once` (added `--once` CLI flag — reuses the existing `run_once()`, doesn't touch the local infinite-loop `main()` used when running on a PC/VPS) instead of the infinite loop, since Actions runners don't persist between schedule ticks.
  - Dedupe state and logs (`monitoring/`) round-trip through `actions/cache` (restore at start of each run, save at the end, keyed by run id with a shared restore-keys prefix) so a symbol already alerted on doesn't refire next hour. Small tradeoff accepted: a cache entry unused for ~7 days can get evicted, which would replay a few old confirmations once — bounded by `MAX_SIGNAL_AGE_MS` anyway, so worst case is a handful of stale alerts, not a flood.
  - Installs from `requirements-bot.txt` (slim: ccxt/pandas/numpy/python-dotenv/requests), not the main `requirements.txt` — `ta-lib` in the main file needs a system C library not present on a bare Actions runner, and isn't imported by anything the bot's code path actually uses (it's leftover from the v1-v4 research indicators, unrelated to `features/indicators.py`'s pure numpy/pandas `rsi()`/`atr()`).
  - Known gotcha to watch for: GitHub auto-disables a scheduled workflow after 60 days with no repo activity — if alerts go quiet for a long stretch, check whether the workflow got disabled before assuming the market's just quiet (same spirit as the heartbeat.jsonl check below).
- ~~Reliability audit~~ — **Resolved (2026-07-16):** an adversarial audit of the signal-generation pipeline found 14 real issues, all fixed and covered by 88 tests (up from 57). Highlights: (1) the whole poll loop had zero exception handling -- one bad API call out of ~2000/hour would have killed the bot permanently; both per-symbol fetches and each full cycle are now isolated. (2) `monitoring/dedupe.py` was marking a signal "alerted" *before* confirming the Telegram send succeeded -- a failed send was silently treated as delivered and never retried; `mark_alerted` now only runs after `send_message` succeeds. (3) `data/live_fetch.py` created a brand-new ccxt instance (and thus an uncoordinated rate limiter) on every one of the ~1300 CRT fetches per cycle -- now shares one exchange instance per cycle with the RSI scan. (4) `rsi()` returned 100 (max overbought) for a perfectly flat/dead market instead of neutral -- fixed. (5) the anomaly filter (AKE fix) only ever checked 4H candles, leaving 1H CRT signals unprotected from thin-liquidity spikes -- `features/crt.py`'s `find_crt_events` now checks each trigger candle individually. (6) CRT only ever looked at the latest candle pair, so a missed/delayed poll silently lost any confirmation in between -- it now scans the last 12 candles per timeframe. (7) added a `monitoring/heartbeat.jsonl` line per cycle so a silently-broken pipeline (e.g. `_is_crypto_perpetual`'s Binance-specific schema assumption breaking) isn't indistinguishable from a quiet market.
  Two more real bugs surfaced only by actually running the full pipeline live against real Binance data, not from reading the code: (a) Binance lists perpetuals with non-Latin-script tickers (e.g. Chinese-character meme coins like `币安人生`) that crashed any bare `print()`/file write on this Windows box's default (non-UTF-8) encoding -- every file open now specifies `encoding="utf-8"`, and `signal_bot.py` reconfigures stdout/stderr the same way at startup. (b) the candle-pair backfill fix (6, above) had no staleness bound, so a cold start (empty dedupe state) replayed up to 2 days of 4H history as 2440 simultaneous "new" signals in one live test -- `signals/crt_rsi_signal.py`'s `MAX_SIGNAL_AGE_MS` (3h) now discards confirmations older than that, which brought the same live run down to 261. Lesson: this audit's original 14 findings came from adversarial code reading and were all real, but running the thing end-to-end against live data still found issues that reading alone didn't surface -- both are needed.
