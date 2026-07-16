# Hypothesis (v2)

> Phase 0 deliverable, second iteration. `HYPOTHESIS.md` v1 (funding-rate-extreme
> mean reversion) was tested through the full Phase 1-3 pipeline and
> **REJECTED** — see `HYPOTHESIS_v1_REJECTED.md` and `RESEARCH_LOG.md` for the
> full record, including every parameter tried and the walk-forward/holdout
> results. This is a genuinely different mechanism (continuation, not
> reversion; volatility-based, not funding-based), reasoned independently —
> not a reworded retest of v1, and not fit to any pattern observed in v1's
> backtest output. Per this project's standing rules, v1's failure is logged
> as a true negative and not quietly compensated for; this is a fresh Phase 0.

## The rule

On **BTCUSDT.P** (Binance perpetual), 1H bars: when realized volatility
(ATR(14) expressed as a percentage of price) compresses to an extreme low
relative to its own trailing 30-day distribution (e.g., bottom ~10-20th
percentile), and price subsequently **breaks out** of its recent N-hour
trading range (closes above the trailing N-hour high, or below the trailing
N-hour low), price tends to **continue moving in the breakout direction**
over the following hours — this is a momentum/continuation rule, the
opposite behavior from v1's mean-reversion rule.

## Why this edge might exist

Low realized volatility in a leveraged perpetual futures market reflects a
compressed, low-participation range — market makers tightening spreads,
directional traders sidelined, open interest often building quietly within
the range. When price finally breaks that range, two leveraged-market-specific
mechanics can compound the move rather than dampen it: (1) stop-loss orders
clustered just outside the compressed range trigger on the break, adding
forced flow in the breakout direction; (2) the break itself squeezes
under-margined positions on the wrong side (liquidation cascade), which is a
forced market order in the same direction as the break, mechanically extending
it. Both mechanisms are specific to leveraged/perpetual markets rather than
generic technical-analysis pattern-matching — the same underlying
"leverage/positioning creates its own price mechanics" logic as v1, but
pointing the opposite direction (continuation from a squeeze/cascade, not
reversion from crowd unwind).

## Timeframe

- Signal checked continuously on 1H bars (not gated to an 8h funding cycle
  like v1 — volatility and range breakouts aren't tied to funding
  settlement).
- Trade/measurement horizon: forward returns over the next 4-24 hours,
  measured on 1H bars — kept comparable to v1's horizon for consistency in
  how "reversion" vs. "continuation" get measured, not because the mechanism
  demands this specific window.

## Entry / exit sketch (to be made precise in Phase 3, not fixed yet)

- **Compression filter:** ATR(14)/close in the bottom P-th percentile of its
  own trailing 30-day (≈720-bar) distribution. P is TBD in Phase 3 (sketch
  range 10-20%).
- **Breakout trigger:** close breaks above the trailing N-hour high (long) or
  below the trailing N-hour low (short), where N is TBD in Phase 3 (sketch
  range 12-48h).
- **Entry direction:** with the breakout (long on upside break, short on
  downside break) — continuation, not fade.
- **Invalidation:** ATR-based stop on the opposite side of the breakout level,
  multiplier TBD in Phase 3 (reusing the same ATR(14) feature already built
  and unit-tested for v1).
- **Exit:** time-boxed within the 4-24h horizon, exact value TBD in Phase 3 —
  same discipline as v1: any exit-mechanism choice beyond what's stated here
  is a logged parameter search, not a silent hypothesis change.

## What would prove this wrong

Across a walk-forward test spanning the same in-sample window used for v1:
forward returns following a volatility-compression breakout are **not**
statistically distinguishable from forward returns following a random or
non-compressed breakout (no measurable continuation premium), OR price
systematically reverts back into the prior range rather than continuing
(mean reversion dominates instead of momentum at these setups). If either
holds consistently across walk-forward windows — not just in one lucky
window — the hypothesis is rejected and logged as such in `RESEARCH_LOG.md`,
exactly as v1 was.

## Explicitly not the source of this hypothesis

As with v1: no TradingView chart, live market data, or current price action
was consulted to write this rule. It is also **not** reasoned from anything
observed in v1's backtest output (e.g. which historical windows were
favorable) — it targets a different, independently-motivated mechanism
(volatility-compression breakout continuation, driven by stop cascades and
liquidations) rather than a retuned version of the funding-crowding-reversion
idea that was just rejected. Any live market/chart tooling remains out of
scope until Phase 5.
