# Hypothesis

> Phase 0 deliverable. Written and committed before any TradingView/market data was pulled for this project, so the rule is not shaped by recent price action. See `CLAUDE.md` for the phase-gate methodology this is a gate for.

## The rule

On **BTCUSDT.P** (Binance perpetual), when the funding rate reaches an extreme relative to its own recent history (e.g., outside the top/bottom ~5% of its trailing 90-day distribution, or a single print beyond a fixed threshold such as ±0.05% per 8h interval), price mean-reverts over the following 4-24 hours.

## Why this edge might exist

Perpetual funding is a periodic payment between longs and shorts that keeps the perp price anchored to spot. A funding rate extreme means one side of the market (usually longs, during a melt-up, or shorts during a capitulation) is paying heavily to stay in a crowded, momentum-chasing position. That crowd is over-levered by construction — funding extremes only happen when positioning is one-sided — so it is disproportionately vulnerable to being forced out by ordinary volatility: liquidations and funding bleed push the crowded side to close, and closing a crowded directional position mechanically pushes price the other way. The counterparty is retail momentum/leverage chasing a move that has already extended; the edge, if real, is being willing to fade that crowd once it's identifiable in the funding print rather than the price action itself.

## Timeframe

- Signal evaluated once per funding interval (every 8h) on BTCUSDT.P funding rate history.
- Trade/measurement horizon: forward returns over the next 4-24 hours, measured on 1H bars.

## Entry / exit sketch (to be made precise in Phase 0→3, not fixed yet)

- Entry trigger: funding rate print crosses the extreme threshold (direction: fade the crowded side — short when funding is extreme positive, long when extreme negative).
- Invalidation: TBD in Phase 3 — likely an ATR-based stop, since "wrong" here looks like the crowd's move continuing rather than reverting.
- Exit: TBD — likely time-boxed (e.g., exit by end of horizon window) or reversion-to-VWAP style target, whichever backtests honestly.

## What would prove this wrong

Across a walk-forward test spanning 2+ years of BTCUSDT.P funding-rate and price history: forward returns following funding-rate extremes are **not** statistically distinguishable from forward returns following non-extreme funding (i.e., no measurable reversion premium), OR price systematically continues in the direction of the crowded position rather than reverting (momentum, not mean reversion, dominates at these extremes). If either holds consistently across walk-forward windows — not just in one lucky window — the hypothesis is rejected and logged as such in `RESEARCH_LOG.md`, not quietly reworded and retested.

## Explicitly not the source of this hypothesis

No TradingView chart, live market data, or current price action was consulted to write this rule — it's derived from documented perpetual-futures funding mechanics, not from "what BTC looks like right now." Any live market/chart tooling (e.g., TradingView MCP) is intentionally out of scope until Phase 5, where it may be used as a live regime-match check before paper trading goes live — never as an input to hypothesis formation.
