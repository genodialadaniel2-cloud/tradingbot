# TradingBot

> Status: **pre-code / planning stage**. This file is a starter scaffold — update every section marked TODO as real decisions get made and code lands. Treat this as the source of truth for how Claude should work in this repo; keep it current rather than letting it drift from what's actually built.

## What this is

A BTC trading bot, built in phases that gate each other (see [Build phases](#build-phases-gate-each-other) below). The single biggest failure mode in retail algo trading is skipping straight from "backtest looked good" to "real money" — nothing here should skip a gate.

- **Target market:** BTC (crypto) — spot vs. perpetual futures TBD by the Phase 0 hypothesis
- **Exchange / broker API:** TODO (candidates: Binance, Coinbase, Kraken, or ccxt as an abstraction layer — all have free historical OHLCV endpoints)
- **Strategy style:** TODO — must be written as a specific, falsifiable hypothesis in `HYPOTHESIS.md` before any strategy code is written (Phase 0 gate). A vague hypothesis like "find patterns in price" leads straight to overfitting.
- **Language / runtime:** TODO, but strongly implied to be Python by the toolchain this plan assumes (`notebooks/research.ipynb`, TA-Lib as an indicator reference) — confirm before Phase 1.
- **Execution mode:** staged, not a single setting — `backtest-only` → `paper trading` (mandatory gate, live data feed + simulated fills) → `live` (small size first). No phase may be skipped.

## Working agreements

- **No live trading without explicit, separate confirmation.** Any code path that can place a real order against a real account is high blast-radius — treat it like the destructive-action rules in the system prompt. Default to paper/sandbox endpoints unless told otherwise for a specific run.
- **Secrets never get committed.** API keys, exchange secrets, and account IDs belong in an untracked `.env` (or OS keychain), never in source, config committed to git, or example files with real values.
- **Backtest before proposing any live/paper deployment.** New or changed strategy logic should have a backtest run and results reported before it's suggested for paper/live use.
- **Every strategy change should be explainable.** When editing signal/entry/exit logic, state the reasoning (why this rule, what edge it targets) — this is a domain where silent logic changes are costly and hard to audit later.
- **Walk-forward, not single-window, backtests.** Roll the training window forward and test on the next unseen chunk each time. A strategy that only works on one static historical period is likely overfit.
- **Treat suspiciously good backtests as bugs, not wins.** Win rate above ~70% or Sharpe above 3+ almost always means lookahead bias, data leakage, or unrealistic fill assumptions — audit for those specifically before reporting a strategy as promising. See [Honest expectations](#honest-expectations).
- **Proactively flag lookahead bias, survivorship bias, and overfitting risk** in anything just built — a standing instruction, not something that needs to be re-asked each time.

## Build phases (gate each other)

Each phase has a success criterion that must be met before moving to the next. Don't let scope creep skip a gate because "it'll probably be fine."

0. **Hypothesis.** State a specific, falsifiable rule in plain English in `HYPOTHESIS.md` — timeframe, entry/exit logic, and what would prove it wrong. No strategy code before this exists.
1. **Data pipeline.** Pull historical OHLCV (and funding rate / open interest / order book depth if the hypothesis needs them) from the chosen exchange API. Store raw data untouched; clean/resample in a separate step so it can always be regenerated. Reserve a held-out chunk (e.g. last 6-12 months) untouched until final validation. *Done when:* data is clean, gap-checked, timestamp-aligned, with a documented train/validation/holdout split.
2. **Feature engineering.** Implement only the indicators the hypothesis actually needs — not "40 indicators just in case." Unit test each against a known reference (e.g. TA-Lib) to catch calculation bugs before they poison everything downstream.
3. **Backtesting engine.** Must be **event-driven**, not purely vectorized, so it only uses information available at that point in time (avoids lookahead bias). Model realistic costs: fees, slippage (worse than intuition suggests, especially on stops), funding payments for perpetuals. Compute the full metric suite: Sharpe, Sortino, max drawdown + duration, win rate, avg win/loss ratio, expectancy per trade. Walk-forward test, don't single-window test. *Done when:* positive expectancy holds across multiple walk-forward windows under realistic costs, not just one lucky period.
4. **Risk management.** Build this before getting attached to the signal — mediocre signal + great risk management beats great signal + none. Start with fixed-fractional position sizing (e.g. 1% risk/trade) before anything Kelly-based. Hard circuit breakers: max daily loss %, max drawdown % that halt trading automatically. Test stop-loss logic against gaps/slippage, not just clean fills.
5. **Paper trading (mandatory gate).** Run against a live data feed with simulated fills, no real money, for weeks to a couple months depending on timeframe. Log every signal, every simulated fill, every rejected trade. Compare to backtest expectations — significant divergence means the backtest had a flaw (survivorship bias, lookahead, unrealistic fills) that must be fixed before touching real capital. *Done when:* paper performance is reasonably consistent with backtest expectations over a meaningful sample of trades.
6. **Live execution (small size first).** Real money, tiny size — validating the pipeline (API auth, order placement, error handling, monitoring) under real conditions, not making money yet. Monitoring/alerting must exist before scaling size. Scale gradually, only after sustained consistent live performance.

**Working phase-by-phase with Claude:** start each phase by reading `HYPOTHESIS.md` and the prior phase's output/tests; write tests alongside code, not after; keep a running `RESEARCH_LOG.md` of strategies/parameters tried and their walk-forward results so dead ends aren't re-tested.

## Honest expectations

Realistic outcomes for a solo-built systematic BTC strategy, used as a sanity check against results, not a target:

- Win rate: often 40-55%, with edge coming from risk/reward asymmetry rather than being "right" most of the time.
- Sharpe ratio: sustainably above 1.0-1.5 out-of-sample is respectable for a retail-built system.
- Drawdowns: expect 15-30%+ even in a "working" strategy — crypto is volatile.
- Red flag, not a discovery: backtest win rate above ~70% or Sharpe above 3+ (see working agreements above).

## Structure

Target layout as code lands (this repo root also serves as the Obsidian vault, so `notes/`, `.obsidian/`, `graphify-out/` coexist with the code dirs below):

```
config/       # strategy_config.yaml, exchange_config.yaml (gitignored secrets)
data/
  raw/        # raw OHLCV / order book dumps, untouched
  processed/  # cleaned, resampled, feature-engineered
  fetch_data.py
features/
  indicators.py
strategy/
  base_strategy.py   # abstract interface: on_bar(), signal(), size()
  <strategy_name>.py
backtest/
  engine.py   # event-driven, not vectorized-only
  costs.py    # fees, slippage, funding cost models
  metrics.py  # Sharpe, Sortino, max drawdown, win rate, expectancy
risk/
  position_sizing.py  # fixed-fractional, vol-targeting, Kelly (later)
  risk_limits.py       # max daily loss, max drawdown circuit breaker
execution/
  paper_trader.py  # simulated live execution against live feed
  live_trader.py    # real exchange execution — built LAST
monitoring/
  logger.py
  dashboard.py  # equity curve, open positions
tests/
  test_*.py
notebooks/
  research.ipynb  # exploratory analysis, walk-forward studies
HYPOTHESIS.md      # Phase 0 deliverable
RESEARCH_LOG.md     # running log of strategies/params tried and results
```

## Tooling in this repo

- **Obsidian vault:** This folder is also configured as an Obsidian vault (`.obsidian/`) for research notes, strategy journals, and trade post-mortems. Markdown notes belong in `notes/`.
- **Graphify:** A knowledge graph of this folder's content is maintained via the `graphify` skill — see `graphify-out/` once generated. Treat existing `graphify-out/` as a first stop for "how does X relate to Y" questions before re-deriving from scratch.
- **TradingView MCP:** `tradingview-mcp/` (cloned from tradesdontlie/tradingview-mcp) gives Claude tool access to a locally running TradingView Desktop instance via Chrome DevTools Protocol, for chart reading, Pine Script development, and alert management. Requires TradingView Desktop installed and launched with `--remote-debugging-port=9222`; see that folder's README for the exact launch script for this OS.

## Open decisions

Track unresolved architecture/strategy questions here as they come up, so context isn't lost between sessions.

- Exchange/broker API selection (Binance vs. Coinbase vs. Kraken vs. ccxt abstraction)
- Language/runtime confirmation (Python assumed, not yet explicit)
- The Phase 0 hypothesis itself — not yet written
- Spot vs. perpetual futures (affects whether funding rate data/costs are needed)
