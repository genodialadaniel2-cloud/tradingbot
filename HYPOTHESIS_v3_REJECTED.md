# Hypothesis (v3)

> Phase 0 deliverable, third iteration. `HYPOTHESIS_v1_REJECTED.md`
> (funding-rate-extreme mean reversion) and `HYPOTHESIS_v2_REJECTED.md`
> (volatility-compression breakout continuation) were each tested through the
> full Phase 1-3 pipeline and **REJECTED** — see `RESEARCH_LOG.md` for the
> complete record. This is a third, independently-reasoned mechanism —
> **liquidity regime**, not funding or realized volatility — and per the
> project's standing "one hypothesis, one shot" rule it will be tested once
> and reported honestly regardless of outcome, with no immediate v4 chained
> onto a rejection.

## The rule

On **BTCUSDT.P** (Binance USDⓈ-M perpetual), 1H bars: an unusually large 1H
move (top ~10-20% of trailing 30-day absolute-return magnitude) that occurs
during a **low-liquidity window** — the Asian session (00:00-08:00 UTC) or a
weekend (Saturday/Sunday, any hour, UTC) — partially **reverts** once
higher-liquidity participation resumes, more than an equally large move
occurring during high-liquidity hours does.

This is explicitly a claim about *when* a move happens, not just *how big* it
is. A generic "big moves mean-revert" effect (regardless of session) would
NOT confirm this hypothesis — see the control condition below, which exists
specifically to separate a real liquidity-regime effect from that confound.

## Why this edge might exist

Binance BTC perpetual order-book depth is measurably thinner during the
Asian session and on weekends — fewer market makers and institutional
desks active, lower resting liquidity to absorb market orders. A given
notional of order flow (a large stop cascade, a whale order, a liquidation
wave) therefore moves price further during these windows than the same flow
would during London/US hours, purely as a function of thin order books
rather than new information. When higher-liquidity participants return
(weekday session opens), better-informed and better-capitalized flow has an
opportunity to trade against the dislocation, arbitraging part of the
thin-liquidity overshoot back out. This is a liquidity-provision/microstructure
mechanism — distinct from v1's crowded-positioning-unwind story and v2's
stop-cascade-continuation story, and pointing toward reversion rather than
continuation, but for a different reason than v1 (v1 was about funding-driven
crowd unwind; this is about order-book depth, unrelated to funding at all).

## Timeframe

- Signal checked on every 1H bar (not gated to funding settlements or any
  fixed cycle — liquidity regime is purely a function of hour-of-day and
  day-of-week).
- Trade/measurement horizon: forward returns over the following few hours to
  roughly one trading day, measured on 1H bars — consistent with v1/v2's
  4-24h scale for comparability, not because the mechanism demands this
  exact window.

## Entry / exit sketch (to be made precise in Phase 3, not fixed yet)

- **Low-liquidity window definition (fixed, not swept):** hour-of-day in
  `[00:00, 08:00)` UTC on any day, OR day-of-week is Saturday/Sunday (UTC).
  This is a definitional choice based on documented session structure, not a
  fitted parameter — though a variant boundary (e.g. `[00:00, 06:00)`) may be
  checked in sensitivity as a robustness check on the boundary choice itself.
- **Move-magnitude trigger:** the bar's absolute 1H return is at or above the
  P-th percentile of its own trailing 30-day (720-bar) distribution of
  absolute 1H returns. P is TBD in Phase 3 (sketch range 80-90th percentile).
- **Entry direction:** **fade** the triggering bar's move (opposite
  direction) — a reversion rule, like v1, but triggered by session/liquidity
  timing rather than funding.
- **Invalidation:** ATR-based stop, multiplier TBD in Phase 3 (reusing the
  same ATR(14) feature already built and unit-tested for v1/v2).
- **Exit:** time-boxed within the multi-hour horizon, exact value TBD in
  Phase 3.
- **Control condition (required, not optional):** the identical rule
  (same trigger, same fade direction, same stop/exit) applied to triggers
  occurring during **high-liquidity hours** (weekday, `[08:00, 24:00)` UTC)
  is run as a control group. The hypothesis is only supported if the
  low-liquidity group's expectancy is both statistically distinguishable
  from zero AND meaningfully better than the high-liquidity control group's
  — not just "positive in isolation."

## What would prove this wrong

Across a walk-forward test spanning the same in-sample window used for v1/v2:
EITHER (a) forward returns following a low-liquidity-window large move are
not statistically distinguishable from zero (no reversion premium at all),
OR (b) the low-liquidity group's expectancy is not meaningfully better than
the high-liquidity control group's expectancy (i.e., any reversion observed
is generic post-shock mean reversion, not a liquidity-regime-specific
effect as claimed). Either failure, held consistently across walk-forward
windows, rejects the hypothesis as stated and it gets logged as such in
`RESEARCH_LOG.md`, exactly as v1 and v2 were.

## Explicitly not the source of this hypothesis

As with v1 and v2: no TradingView chart, live market data, or current price
action was consulted to write this rule. It is also **not** reasoned from
anything observed in v1's or v2's backtest output — it targets a third,
independently-motivated mechanism (order-book depth / liquidity regime by
time-of-day and day-of-week) rather than a retuned version of either
rejected idea. The control-group requirement above exists precisely to keep
this hypothesis honest and falsifiable rather than a relabeled version of
"big moves tend to revert," which would be a much weaker and less specific
claim. Any live market/chart tooling remains out of scope until Phase 5.
