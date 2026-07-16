# Hypothesis (v4)

> Phase 0 deliverable, fourth iteration -- but a genuinely different kind of
> iteration from v1→v2→v3. `HYPOTHESIS_v1_REJECTED.md` (funding-extreme mean
> reversion), `HYPOTHESIS_v2_REJECTED.md` (volatility-compression breakout
> continuation), and `HYPOTHESIS_v3_REJECTED.md` (liquidity-regime overshoot
> reversion) were all tested on **1H bars** and all rejected, each with a
> common failure pattern: gross (pre-cost) edges were thin-to-near-zero, and
> high trade frequency (145-716 trades/year) let realistic Binance perp costs
> dominate whatever edge existed. See `RESEARCH_LOG.md`'s v3 entry for the
> full cross-hypothesis postmortem that motivated this pivot.
>
> This is not a fourth single-bar-frequency mechanism chasing a passing
> result -- it's a structural pivot to a **lower-frequency timeframe** (daily
> bars, multi-day holds), made explicitly to test whether trade frequency
> itself, not signal quality, was the dominant obstacle in v1-v3. Per the
> project's standing "one hypothesis, one shot" rule, this is tested once and
> reported honestly regardless of outcome.

## The rule

On **BTCUSDT.P** (Binance perpetual), **daily bars** (UTC): when the trailing
K-day cumulative return is positive, go/stay **long**; when it is negative,
go/stay **short**. Hold the position as long as the sign of the trailing
K-day return persists, reversing direction whenever it flips (checked once
per day, at the daily close) -- a classic time-series momentum / trend-following
rule, not a discrete event-driven trigger like v1-v3. A position also exits
early on an ATR-based stop if hit intraday.

## Why this edge might exist

This is a different, more established mechanism than any of v1-v3: **time-series
momentum**, documented across asset classes (Moskowitz, Ooi & Pedersen 2012)
and specifically in crypto (e.g. Liu & Tsyvinski find momentum effects in
large-cap cryptocurrencies at weekly-to-monthly horizons). The proposed
driver is slow-moving capital and systematic trend-following flows (CTA-style
funds, momentum-chasing retail) that enter gradually over days-to-weeks
rather than instantaneously, causing price to continue trending in the
direction it's already moving, plus underreaction to new information that
gets priced in gradually rather than all at once. This is unrelated to
funding extremes, volatility compression, or session liquidity -- it is a
claim about persistence of established trends, at a timeframe (days-weeks)
too slow for any of v1-v3's mechanisms (crowd unwind, stop cascades,
liquidity regime) to be the driver.

## Timeframe

- **Daily bars** (UTC, midnight-to-midnight), resampled from the same clean,
  gap-checked in-sample hourly data already in `data/processed/` -- no new
  data pull needed. Signal checked once per day, at that day's close.
- Trade/measurement horizon: days to a few weeks per trade (position held
  until the trend signal flips or a stop is hit) -- an order of magnitude
  longer than v1-v3's 4-24h horizon, by design.

## Entry / exit sketch (to be made precise in Phase 3, not fixed yet)

- **Trend signal:** trailing K-day cumulative return of daily close.
  K is TBD in Phase 3 (sketch range 20-45 days, i.e. roughly 1-6 weeks).
- **Entry/reversal direction:** long if trailing K-day return > 0, short if
  < 0. Position changes direction (closes + reopens) whenever the sign
  flips; unlike v1-v3 there is no fixed time-boxed exit -- the position
  rides as long as the trend signal agrees.
- **Invalidation:** ATR-based stop on daily bars (ATR(14) computed on daily
  OHLC), multiplier TBD in Phase 3. If stopped out, the position goes flat
  and only re-enters on the next day the signal is (re-)checked -- this can
  mean an immediate next-day re-entry in the same direction if the trend
  signal still agrees, which is realistic trend-following-with-stops
  behavior, not a bug.
- **Execution convention:** consistent with v1-v3 -- a decision made using
  information known as of a bar's close is executed at the next bar's open,
  never the same bar's own close.

## What would prove this wrong

Across a walk-forward test spanning the same in-sample window used for v1-v3
(resampled to daily bars): net expectancy per trade (per trend segment) is
**not** statistically distinguishable from zero, OR walk-forward windows
alternate sign with no persistent pattern, OR parameter sensitivity flips the
sign of expectancy under most ±20% perturbations of K or the stop multiplier.
If any of these hold consistently, the hypothesis is rejected and logged as
such in `RESEARCH_LOG.md`, exactly as v1-v3 were.

**Disclosed in advance, not after the fact:** daily bars over the ~3.4-year
in-sample window produce far fewer trades than v1-v3's hourly signals did
(roughly tens, not hundreds, depending on K) -- walk-forward windows may not
individually clear the ~100-trade sample-size comfort level v1-v3 achieved.
This is an inherent tradeoff of the lower-frequency pivot, not something to
paper over; per-window trade counts and wider confidence intervals will be
reported explicitly rather than treated as equivalent evidence to v1-v3's.

## Explicitly not the source of this hypothesis

As with v1-v3: no TradingView chart, live market data, or current price
action was consulted to write this rule. It is reasoned from published
momentum literature and the specific cross-hypothesis cost/frequency
postmortem in `RESEARCH_LOG.md`'s v3 entry -- not from any attempt to find a
timeframe that would have made v1, v2, or v3 pass. Any live market/chart
tooling remains out of scope until Phase 5.
