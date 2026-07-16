# Research Log

Running log of strategies/parameters tried and their results, per `CLAUDE.md`.
Every parameter choice gets an entry here — this is not a changelog of code,
it's a changelog of decisions.

---

## Phase 0 — Hypothesis

Committed in `HYPOTHESIS.md` (commit `922bc00`) before any market data was
pulled. Rule: BTCUSDT.P funding rate extremes (trailing 90-day percentile/z-score,
or a fixed threshold e.g. ±0.05%/8h) predict mean reversion over the following
4-24h. See that file for the full rule and falsification criteria.

## Phase 1 — Data pipeline

**2026-07-14**

### Exchange / language decision

- **Language: Python** (3.14, in a repo-local `.venv/`). Confirms the assumption in
  `CLAUDE.md`'s Open Decisions — no reason to deviate given the ccxt/pandas/TA-lib
  toolchain that section already anticipates.
- **Exchange/API: ccxt against `binanceusdm`** (Binance USDⓈ-M perpetual futures),
  symbol `BTC/USDT:USDT`. Chosen over raw Binance REST because ccxt gives a
  uniform `fetch_ohlcv` / `fetch_funding_rate_history` interface if the exchange
  ever needs to change later, at no real cost here. Both endpoints used are
  public (no API key/secret needed for Phase 1-3 — nothing to keep out of git
  yet).
- Verified live before building the full pipeline: `BTC/USDT:USDT` exists in
  `binanceusdm`'s markets, and both `fetch_ohlcv` and `fetch_funding_rate_history`
  return real data for it.

### Pull parameters

- **Range pulled:** 2022-01-01T00:00:00Z through fetch time (2026-07-14), i.e.
  ~4.5 years — comfortably over the "at least 2 years" minimum, and it spans a
  full bear (2022), bull (2023-24), and chop (2025-26) regime mix, which matters
  for walk-forward diversity in Phase 3.
- **Timeframe:** 1H OHLCV bars (matches the hypothesis's 4-24h forward-return
  horizon). Funding rate history pulled at native 8h granularity (funding
  settles every 8h on Binance perps) — not resampled to 1h, since the hypothesis
  evaluates the signal once per funding interval.
- No open interest / order book depth pulled — the hypothesis as written doesn't
  need them (CLAUDE.md Phase 1 gate: "only the indicators the hypothesis needs").
- Binance caps `fetch_ohlcv`/`fetch_funding_rate_history` responses at 1000 rows
  per call regardless of requested `limit` — pagination in `data/fetch_data.py`
  walks forward by `last_timestamp + 1` until it reaches "now," not by comparing
  batch size to the requested limit (an earlier version of the script assumed
  batch-size-drop meant "done" and silently truncated to a single page — caught
  by eyeballing the row count, fixed before this data was treated as final).

### Holdout split — done first, before any cleaning

Per the session's standing instruction, the holdout carve-out happens inside
`data/fetch_data.py` itself, immediately after the raw pull and before anything
touches the data:

- **Split fraction:** 25% (middle of the instructed 20-30% range), split by
  **time span**, not row count.
- **Split boundary:** `2025-05-26T06:00:00Z` (OHLCV) / funding in-sample ends
  `2025-05-26T00:00:00Z`, holdout starts `2025-05-26T08:00:00Z` — consistent with
  the 8h funding grid, zero overlap.
- **In-sample** (`data/raw/`, then cleaned into `data/processed/`):
  2022-01-01T01:00Z → 2025-05-26T06:00Z. 29,790 hourly bars, 3,724 funding prints.
  This is the ONLY data Phase 3 walk-forward windows may draw from.
- **Holdout** (`data/holdout/`, untouched beyond this pull):
  2025-05-26T07:00Z → 2026-07-14T00:00Z (~13.6 months). 9,930 hourly bars,
  1,242 funding prints. Not to be read, plotted, or summary-statted again until
  the single final validation run at the end of Phase 3, per standing rules —
  no exploratory peeking, including by me, before then.
- `data/raw/_meta.json` and `data/holdout/_meta.json` record the fetch timestamp,
  split boundary, and row counts for reproducibility.

### Cleaning (`data/process_data.py`)

- Dedupe on timestamp, sort ascending, convert to UTC datetime.
- Gap check: OHLCV must be a complete 1h-spaced sequence; funding must be
  complete 8h-spaced (5s tolerance for Binance's occasional millisecond jitter
  on funding timestamps). **Result: 0 gaps found in either series** across the
  full in-sample range — no missing-bar interpolation was needed, so no
  interpolation-induced lookahead risk to flag going forward.
- Convenience join: `ohlcv_1h_with_funding.parquet` forward-fills the last
  *settled* funding print onto the hourly grid via `merge_asof(..., direction="backward")`
  — a print at time T only ever fills bars at or after T, never before, so this
  join itself introduces no lookahead. Phase 2/3 code should still index off of
  `fundingRate` values only at or after the print's own timestamp when computing
  anything trailing (e.g. the 90-day percentile), to be safe.

### Done criteria (per CLAUDE.md Phase 1 gate)

Data is clean, gap-checked (0 gaps), timestamp-aligned (UTC, deduped, sorted),
and the holdout split is fixed and documented above. **Phase 1 complete.**

---

## Phase 2 — Feature engineering

**2026-07-14**

Implemented only what `HYPOTHESIS.md` needs, in `features/indicators.py`:

- **`funding_zscore` / `funding_percentile`**: trailing 90-day (270-print, since
  Binance perp funding settles 3x/day) z-score and percentile rank of each
  funding print vs. its own history, inclusive of itself, `min_periods=30`
  (~10 days) warmup. Both are backward-looking only.
- **`atr`**: standard Wilder-smoothed ATR(14) on 1H bars, matching `ta-lib`
  exactly (cross-checked, see tests below) — used for the hypothesis's
  "ATR-based stop," period fixed at 14 for Phase 2 (the *multiplier* is a
  Phase 3 parameter, tuned/perturbed there).
- No other indicators added.

**Unit tests** (`tests/test_indicators.py`, 5 tests, all passing):
- ATR cross-checked against `ta-lib==0.7.0`'s `ATR()` on synthetic OHLC data
  (installs cleanly on this machine now — 0.7.0 ships prebuilt wheels, no C
  toolchain needed).
- Funding z-score cross-checked against `talib.SMA`/`talib.STDDEV(nbdev=1)`
  (population std, matching `ddof=0`).
- Funding percentile has no ta-lib equivalent — verified against hand-computed
  expected values on a small deterministic series instead.
- Two explicit no-lookahead tests: mutating only the *last* value of an input
  series and asserting every earlier output is byte-for-byte unchanged, for
  both `funding_zscore` and `atr`.

Ran `features/build_features.py` on the in-sample data only
(`data/processed/`, never `data/holdout/`): ATR valid for 29,776/29,790 bars
(first 14 are warmup NaN), funding features valid for 3,695/3,724 prints
(first 29 are warmup NaN). Output: `ohlcv_features_1h.parquet`,
`funding_features_8h.parquet`, and a convenience `features_1h.parquet` that
forward-fills funding features onto the hourly grid via
`merge_asof(direction="backward")` — a print at time T only ever fills bars
`>= T`, never before, so the join itself adds no lookahead.

**Phase 2 done** per the CLAUDE.md gate: only the needed indicators, each unit
tested against a reference.

## Phase 3 — Backtest

**2026-07-14**

### Engine design (`backtest/engine.py`) — logged because these conventions materially affect results

- Signal evaluated **only on exact funding-settlement bars** (every 8h), using
  that bar's own trailing percentile/ATR (both known as of that bar's close).
- Entry fills at the **open of the next bar** — a realistic "can't trade the
  exact close tick" assumption, not lookahead (the decision itself never uses
  data from that next bar or later).
- Stop-loss level fixed at entry (`entry_price -/+ atr_multiplier * ATR@signal`),
  checked against each subsequent bar's high/low, starting with the entry bar
  itself (its open is the fill; its own high/low can still trigger the stop
  within the same bar — the open precedes the high/low chronologically, so
  this isn't lookahead).
- If no stop is hit, exit is **time-boxed**: close of the bar exactly
  `exit_horizon_hours` after entry. This is the "TBD" exit from
  `HYPOTHESIS.md` — the VWAP-reversion-target alternative it also mentions was
  **not implemented or tested** this session (see "biggest remaining risk"
  below).
- **One position at a time** — a new signal is ignored while a trade is open.
  No pyramiding/concurrent positions. This is a Phase 3 simplification, not a
  Phase 4 risk-management recommendation.
- A signal is skipped entirely if there isn't enough remaining data for the
  trade to reach its full exit horizon (avoids counting an artificially
  truncated trade at the dataset's end).
- Verified with 6 unit tests (`tests/test_engine.py`): correct long/short PnL
  sign, correct stop-trigger price and worse stop slippage, correct funding
  accrual sign (short position *receives* positive funding — verified
  explicitly, since getting this backwards would flip the sign of a real
  mechanism the hypothesis leans on), no-trade-if-truncated, and costs
  strictly reducing net vs. gross PnL.

### Cost model (`backtest/costs.py`) — Binance USDM VIP0, all modeling assumptions, not measured fills

- Taker fee 0.05%/side (entry assumed market order reacting to the funding
  print; exit assumed market order whether time-exit or stop).
- Slippage: 0.02% normal (time-exit), **0.10% on stops** — 5x normal, per
  CLAUDE.md's explicit warning that stop fills are worse than intuition
  suggests.
- Funding: `-direction * funding_rate` per settlement crossed *while holding*
  (not double-counting the triggering print itself, since entry happens one
  bar after that print already settled). Sign convention verified by unit
  test. Because the strategy fades the crowded side, it is mechanically on the
  *receiving* end of funding at entry and typically continues to receive it if
  the extreme persists — this is a real, intentional part of the hypothesis's
  proposed edge, not an accounting error, but it also means part of any
  apparent profit could be pure funding carry rather than genuine price
  reversion. Reported separately below to check this.

### Base case (percentile_tail=0.05, atr_stop_multiplier=2.0, exit_horizon_hours=12h) — full in-sample, 2022-01-01 → 2025-05-26

| metric | value |
|---|---|
| trades | 495 |
| win rate | 42.6% |
| avg win / avg loss | 1.523% / -1.110% (ratio 1.37) |
| expectancy/trade (net) | **0.0126%** |
| profit factor | 1.02 |
| Sharpe (trade-freq annualized) | 0.08 |
| Sortino | 0.18 |
| max drawdown | -45.92% (339 trades underwater) |
| longest losing streak | 10 |
| trades/year | 145.7 |
| gross expectancy (pre-cost) | 0.1717% |
| funding-carry contribution to expectancy | 0.0047% |

Sample size: 495 trades clears the 100-trade minimum. One-sample t-test on net
per-trade returns: **t = 0.152, p = 0.879** — expectancy is not statistically
distinguishable from zero. Gross expectancy (0.17%) is mostly consumed by
round-trip costs (~0.14-0.22% depending on stop vs. time exit), and the
funding-carry tailwind (0.0047%) is small relative to price-PnL noise, i.e.
this is not simply "collecting the funding spread" in disguise — but there's
also no reversion signal strong enough to survive costs.

Neither the >70% win rate nor >3 Sharpe red flag applies — if anything the
opposite: this already looks like a marginal-to-no-edge result before any
further scrutiny, consistent with `HYPOTHESIS.md`'s own falsification
condition ("forward returns... not statistically distinguishable... no
measurable reversion premium").

### Walk-forward (6 consecutive 207-day windows within in-sample, same frozen params, no per-window fitting)

| window | dates | trades | expectancy/trade | Sharpe | profit factor | max DD |
|---|---|---|---|---|---|---|
| 1 | 2022-01-01 → 2022-07-26 | 75 | **+0.509%** | 2.27 | 1.78 | -10.7% |
| 2 | 2022-07-26 → 2023-02-18 | 60 | -0.081% | -0.42 | 0.89 | -19.8% |
| 3 | 2023-02-18 → 2023-09-13 | 95 | +0.067% | 0.58 | 1.15 | -7.7% |
| 4 | 2023-09-13 → 2024-04-07 | 97 | **-0.349%** | -3.12 | 0.54 | -31.0% |
| 5 | 2024-04-07 → 2024-10-31 | 82 | +0.111% | 0.69 | 1.19 | -13.8% |
| 6 | 2024-10-31 → 2025-05-26 | 84 | -0.113% | -0.90 | 0.83 | -17.7% |

3 of 6 windows negative, alternating with no persistent regime pattern, and
window 4's Sharpe of -3.12 is itself a red flag magnitude (in the negative
direction) that got specifically checked for a bug (re-ran with cost_model
zeroed out — window 4 is still net negative gross, so it's a real
signal-quality problem in that period, not a cost-model artifact). **This is
the walk-forward inconsistency the standing rules call a rejection signal on
its own.**

### Parameter sensitivity (±20% each, one at a time, base case held fixed otherwise)

| variant | expectancy/trade | Sharpe | profit factor |
|---|---|---|---|
| BASE | +0.0126% | 0.08 | 1.02 |
| percentile_tail 0.05→0.04 (-20%) | -0.0392% | -0.25 | 0.94 |
| percentile_tail 0.05→0.06 (+20%) | -0.0307% | -0.22 | 0.95 |
| atr_stop_multiplier 2.0→1.6 (-20%) | -0.0322% | -0.23 | 0.95 |
| atr_stop_multiplier 2.0→2.4 (+20%) | +0.0210% | 0.13 | 1.03 |
| exit_horizon 12h→10h (-17%) | +0.0273% | 0.19 | 1.05 |
| exit_horizon 12h→14h (+17%) | +0.0241% | 0.15 | 1.03 |

Expectancy **flips sign** under two of three ±20% perturbations
(percentile_tail either direction, atr_stop_multiplier down). None of the 7
variants (base + 6 perturbations) has a Sharpe magnitude above ~0.25 in either
direction — this isn't "fragile but real," it's "indistinguishable from noise
in every direction tried."

### Holdout — single, final, frozen-parameter run (2025-05-26 → 2026-07-14, 414 days)

Run **once**, with the base-case parameters exactly as specified above,
never re-tuned based on this or any other result:

| metric | value |
|---|---|
| trades | 90 |
| win rate | 43.3% |
| expectancy/trade (net) | 0.0132% |
| profit factor | 1.03 |
| Sharpe | 0.09 |
| max drawdown | -12.65% |
| t-stat / p-value vs. zero | t=0.093, p=0.926 |

Holdout expectancy (0.0132%) is nearly identical to the in-sample aggregate
(0.0126%) — the aggregate itself didn't overfit to in-sample noise in a way
that collapsed out-of-sample. But what it's consistent *with* is a near-zero,
statistically insignificant result, not a real edge. Holdout drawdown (-12.7%)
was milder than several in-sample windows, but that's not something to lean
on given the near-zero central estimate.

One disclosed limitation: the holdout's funding percentile/z-score warm up
using **only holdout-period data** (not bridged from the in-sample tail), so
the first ~10 days of holdout have no valid signal. This was a deliberate
choice to keep `data/holdout/` fully self-contained and untouched by anything
in-sample, at the minor cost of a short warmup gap — logged here rather than
silently absorbed.

### Verdict: **REJECTED**

The funding-rate-extreme mean-reversion rule in `HYPOTHESIS.md`, as
operationalized here (percentile-based extreme, ATR(14) stop, fixed
12h/±20% time-boxed exit), shows:
- Net expectancy statistically indistinguishable from zero, in-sample AND
  holdout (p > 0.85 both).
- Walk-forward windows alternate sign with no persistent regime story (half
  positive, half negative, similar magnitudes).
- Parameter sensitivity flips the sign of expectancy under most ±20%
  perturbations — no stable region of the parameter space was found.
- In-sample drawdowns (up to -58% under perturbation) exceed even the wide
  "honest expectations" band in CLAUDE.md.

This matches `HYPOTHESIS.md`'s own stated falsification condition almost
exactly: forward returns following funding-rate extremes are not
distinguishable from a no-edge baseline. Per the standing rules, this is
logged as a genuine negative result, not reworded and retested, and no
alternative/replacement hypothesis is being proposed in this session — a new
hypothesis goes back through Phase 0.

**Single biggest remaining risk to this verdict:** only one specific
operationalization of the hypothesis was tested — percentile-based extreme
detection with a fixed time-boxed exit. `HYPOTHESIS.md` explicitly also
allows a fixed absolute funding-rate threshold (±0.05%/8h) and a
VWAP-reversion-target exit as alternatives; neither was tried. It's possible
(though the walk-forward/sensitivity fragility makes it seem unlikely) that
one of those untried variants behaves differently. That would need to be
scoped as explicit, disclosed additional parameter search against this same
hypothesis and same in-sample data — never against the holdout — in a future
session, not as grounds to reverse this verdict now.

---

**This verdict (REJECTED) was generated and self-graded in a single session
with no independent check.** Recommend a personal re-read of this file and a
sanity check of the walk-forward numbers above (especially window 4's -3.12
Sharpe and the parameter-sensitivity sign flips) before treating this as
final, and before any Phase 4 work begins. Phase 4 (position sizing / risk
limits) is out of scope for this session's deliverables regardless of this
verdict.

---

# HYPOTHESIS v2 — Volatility-Compression Breakout Continuation

**2026-07-14, continued.** After v1's rejection, the user asked me to iterate
autonomously ("go back to Phase 0... until you have confidence"). I pushed
back on unbounded iteration — repeatedly generating and testing hypotheses
against the same dataset until one "passes" is a multiple-comparisons/
data-snooping process, not hypothesis testing, and produces exactly the kind
of manufactured-looking edge CLAUDE.md's "suspiciously good backtest = bug"
rule warns against. The user agreed to a **one-shot** approach: one new
hypothesis, reasoned from a different mechanism than v1 (not a reworded
retest), tested once through the full pipeline, reported honestly regardless
of outcome. What follows is that one shot.

`HYPOTHESIS.md` v1 was renamed to `HYPOTHESIS_v1_REJECTED.md` (preserved, not
deleted) and a new `HYPOTHESIS.md` written: **volatility-compression breakout
continuation** — momentum, not reversion; realized-volatility-based, not
funding-based — reasoned from stop-cascade/liquidation mechanics rather than
crowded-positioning unwind. See that file for the full rule and falsification
criteria. Explicitly not shaped by v1's specific backtest output (e.g. no
attempt to fit which historical windows were favorable in v1's run).

### Phase 2 (v2 features)

Added to `features/indicators.py`, both unit tested (`tests/test_indicators.py`,
4 new tests — 8 total in that file now):

- **`rolling_prior_range`**: trailing N-hour high/low computed from the N bars
  *strictly before* the current one (`shift(1)` before `rolling()`) — a bar's
  own high/low is never part of the range it's tested for breaking out of.
  Verified explicitly with a test that a bar's own extreme value doesn't leak
  into its own range check, plus a no-lookahead mutation test.
- **`volatility_percentile`**: trailing 30-day (720-bar) percentile rank of
  ATR(14)-as-%-of-price vs. its own history, same pattern as v1's funding
  percentile. Reuses the already-tested `atr()` function.

`features/build_features_v2.py` also merges in funding rate data (from the
same `data/processed/funding_rate_8h.parquet` v1 already built) — v2's signal
doesn't use funding at all, but funding payments while holding a perp position
are a real cost/tailwind regardless of entry signal, and CLAUDE.md requires
modeling them. Ran on in-sample data only: ATR valid 29,776/29,790 bars,
vol-percentile valid 29,609/29,790 bars (181 warmup).

### Phase 3 (v2 engine)

`backtest/engine_v2.py` reuses v1's execution conventions exactly (signal
decided at bar close, entry fills at next bar's open, stop checked from the
entry bar's own H/L onward, time-boxed exit, one position at a time, funding
accrual, skip-if-truncated-by-dataset-end) — only the signal itself differs:
checked on *every* bar (not gated to 8h funding settlements, since volatility/
breakouts aren't tied to the funding cycle), entering **with** the breakout
direction (continuation) rather than fading it. 4 unit tests
(`tests/test_engine_v2.py`): no signal when not compressed, correct long/short
direction on a genuine breakout, no signal without an actual range break.

### Base case (vol_percentile_threshold=0.15, breakout_window_hours=24,
atr_stop_multiplier=2.0, exit_horizon_hours=12) — full in-sample

| metric | value |
|---|---|
| trades | 153 |
| win rate | 36.6% |
| avg win / avg loss | 1.537% / -0.972% (ratio 1.58) |
| expectancy/trade (net) | **-0.0532%** |
| profit factor | 0.91 |
| Sharpe (trade-freq annualized) | -0.23 |
| Sortino | -0.89 |
| max drawdown | -21.35% (96 trades underwater) |
| trades/year | 45.0 |
| gross expectancy (pre-cost) | +0.1289% |
| funding contribution | -0.0008% (negligible, as expected — not a funding-driven signal) |

153 trades clears the 100-trade minimum. One-sample t-test on net per-trade
returns: **t = -0.415, p = 0.679** — not statistically distinguishable from
zero, and the point estimate is negative. Gross (pre-cost) expectancy is
positive (+0.13%) but costs (~0.14-0.22%/round-trip, same cost model as v1)
consume it entirely and then some.

### Walk-forward (same 6 consecutive 207-day windows as v1, same frozen params)

| window | dates | trades | expectancy/trade | Sharpe | profit factor |
|---|---|---|---|---|---|
| 1 | 2022-01-01 → 2022-07-26 | 18 | -0.107% | -0.32 | 0.88 |
| 2 | 2022-07-26 → 2023-02-18 | 34 | -0.051% | -0.22 | 0.92 |
| 3 | 2023-02-18 → 2023-09-13 | 23 | **-0.508%** | **-5.07** | **0.20** |
| 4 | 2023-09-13 → 2024-04-07 | 17 | +0.009% | 0.04 | 1.02 |
| 5 | 2024-04-07 → 2024-10-31 | 25 | -0.032% | -0.15 | 0.94 |
| 6 | 2024-10-31 → 2025-05-26 | 34 | +0.078% | 0.39 | 1.15 |

4 of 6 windows negative; the 2 positive windows are both economically
negligible (near breakeven). Window 3's Sharpe of -5.07 is a red-flag
magnitude and got the same scrutiny v1's window 4 did: re-ran with the cost
model zeroed out (`gross_pnl_pct` mean still -0.31bps — a real signal problem,
not a cost artifact) and inspected the trade log directly. Almost every trade
in that window was a fast stop-out within a few hours of entry — i.e. the
"breakout" repeatedly faked out and reverted, rather than continuing. That's
a real, economically sensible finding (not every breakout from low volatility
continues — many are false breakouts, especially in a choppy Mar-Aug 2023
BTC regime), not a computational bug.

### Parameter sensitivity (±20% each, one at a time, base case held fixed otherwise)

| variant | expectancy/trade | Sharpe | profit factor |
|---|---|---|---|
| BASE | -0.0532% | -0.23 | 0.91 |
| vol_percentile_threshold 0.15→0.12 (-20%) | -0.0834% | -0.33 | 0.87 |
| vol_percentile_threshold 0.15→0.18 (+20%) | +0.0030% | 0.01 | 1.00 |
| breakout_window_hours 24→19 (-20%) | -0.0590% | -0.28 | 0.90 |
| breakout_window_hours 24→29 (+20%) | -0.0785% | -0.32 | 0.87 |
| atr_stop_multiplier 2.0→1.6 (-20%) | -0.0857% | -0.38 | 0.86 |
| atr_stop_multiplier 2.0→2.4 (+20%) | -0.0283% | -0.12 | 0.95 |
| exit_horizon 12h→10h (-17%) | -0.1397% | -0.65 | 0.77 |
| exit_horizon 12h→14h (+17%) | +0.0184% | 0.07 | 1.03 |

7 of 9 variants (base + 8 perturbations) are net negative; the 2 positive
ones are both within noise of zero (Sharpe 0.01 and 0.07). Unlike v1 (which
alternated sign roughly evenly), v2 is **consistently negative** across
nearly the entire parameter grid tried — a stronger, more decisive rejection
signal than v1's "hovers around zero."

### Holdout: not run for v2, by design

Per the standing rule, the holdout gets exactly one look, ever, and it exists
to give a final confirmation to a rule that has *passed* its in-sample gates.
v2 did not pass them — in-sample expectancy is negative and statistically
indistinguishable from zero, walk-forward is majority-negative with one
severely negative window that checked out as a real effect (not a bug), and
parameter sensitivity is negative almost everywhere it was tried. Spending
the one-time, non-repeatable holdout look to confirm an already-clear
in-sample rejection would consume it for no real decision value, at the cost
of not having it available should a future, better-supported hypothesis reach
this gate. This is a deliberate choice, not an oversight — flagged here
explicitly rather than silently skipped.

### Verdict: **REJECTED**

The volatility-compression breakout-continuation rule, as operationalized
here, shows a consistently negative-to-zero net expectancy in-sample, a
majority-negative and internally inconsistent walk-forward record, and no
parameter region tried that clears statistical or economic significance.
Gross (pre-cost) returns are marginally positive, meaning there may be a
tiny real continuation effect, but it does not survive realistic Binance
perp costs. Logged as a genuine negative result per the standing rules — no
further hypothesis is being proposed in this session.

**Single biggest remaining risk to this verdict:** the exit mechanism (fixed
12h time-box) and stop convention (ATR multiplier from entry) were the only
ones tested — a tighter, volatility-adaptive stop or a "exit on first sign of
stall" rule might behave differently, since several of the losing trades in
the window-3 inspection were fast fakeout reversals that a tighter stop might
have cut smaller, or a momentum-confirmation filter (e.g. requiring the
breakout to hold for 1-2 bars before entering, rather than triggering
instantly on the breakout bar) might filter out. That's a legitimate
follow-on idea, but per the same discipline applied to v1's "untried
variants" risk, it would need to be scoped as explicit, disclosed additional
work against this same hypothesis and same in-sample data in a future
session — not grounds to reverse this verdict now, and not something to
chase by immediately trying more variants in this session.

### Overall session outcome: two hypotheses tested, two rejected

Neither `HYPOTHESIS_v1_REJECTED.md` (funding-extreme mean reversion) nor
`HYPOTHESIS.md` v2 (volatility-compression breakout continuation) survived
the Phase 3 gate on BTCUSDT.P 1H/8h data, 2022-01-01 through 2025-05-26
in-sample. No strategy is being recommended for Phase 4. This is the
honest, disclosed state of the research — including the two full dead ends —
not a failure to hide.

---

**Both verdicts above were generated and self-graded in a single session with
no independent check.** The same recommendation from v1 applies to v2: a
personal re-read of this file, specifically the walk-forward and sensitivity
tables, before treating either REJECTED verdict as final. Given two
consecutive rejections on the mechanisms tried so far, the honest options
from here are (a) a genuinely fresh Phase 0 in a new session/context, with a
hypothesis reasoned independently of everything observed in this session's
two backtests, or (b) stepping back from rule-based signal-hunting on this
specific instrument/timeframe entirely and reconsidering the approach at a
higher level. Continuing to generate variant after variant in search of a
passing result is the one path that should specifically be avoided, for the
reasons discussed with the user before v2 was written.

---

# HYPOTHESIS v3 — Liquidity-Regime Overshoot Reversion

**2026-07-14, new session, continued from handoff.** Per the standing
"one hypothesis, one shot" rule (see above), this session's context was
explicitly treated as a fresh Phase 0: three candidate mechanisms (time-series
momentum, session/liquidity-regime reversion, open-interest-divergence
squeeze) were reasoned independently of v1/v2's specific backtest outputs and
presented to the user, who chose **session/liquidity-regime reversion**.

`HYPOTHESIS.md` v2 was renamed to `HYPOTHESIS_v2_REJECTED.md` (preserved) and
a new `HYPOTHESIS.md` written: BTC 1H bars, a large move (top ~20% of trailing
30-day |1h return| distribution) occurring during a **low-liquidity window**
(Asian session 00:00-08:00 UTC, or any hour on a weekend) partially reverts
once higher-liquidity hours resume — order-book depth is thinner in those
windows, so a given order-flow shock moves price further, and better-informed/
better-capitalized flow arbitrages part of it back out once liquidity
returns. This is a microstructure/liquidity-provision story, distinct from
both v1 (funding-driven crowd unwind) and v2 (stop-cascade continuation).

Critically, the hypothesis was written with a **required control condition**
baked in from the start: the identical rule applied to triggers during
high-liquidity hours is run side by side as a control group. The hypothesis
is only supported if the low-liquidity group is both profitable in its own
right AND meaningfully better than the high-liquidity control — not just
"big moves revert" relabeled. See `HYPOTHESIS.md` for the full rule and
falsification criteria.

### Phase 2 (v3 features)

Added to `features/indicators.py`, both unit tested (`tests/test_indicators.py`,
4 new tests — 31 total in the suite now):

- **`is_low_liquidity_window`**: pure calendar flag (hour-of-day + day-of-week
  in UTC) derived only from a bar's own timestamp — zero lookahead risk by
  construction, no warmup needed. Verified against hand-picked timestamps
  covering all four combinations of {Asian/non-Asian hour} x {weekday/weekend}.
- **`abs_return_percentile`**: trailing 30-day (720-bar) percentile rank of
  `|1h return|` vs. its own history, same `_pct_rank` pattern as v1's funding
  percentile and v2's volatility percentile. Reuses `close.pct_change()`.

`features/build_features_v3.py` also merges in funding data for cost modeling
(same reasoning as v2 — funding is a real cost/tailwind on any held perp
position regardless of entry signal). Ran on in-sample data only: ATR valid
29,776/29,790 bars, abs-return-percentile valid 29,622/29,790 (168 warmup),
**low-liquidity bars: 15,630/29,790 (52.5%)** — matches the arithmetic
expectation for "8h Asian session daily + full weekend" almost exactly
(5 weekdays x 8h + 2 weekend days x 24h = 88/168 hours/week = 52.4%).

### Phase 3 (v3 engine)

`backtest/engine_v3.py` reuses v1/v2's execution conventions exactly (signal
decided at bar close, entry fills at next bar's open, stop checked from the
entry bar's own H/L onward, time-boxed exit, one position at a time, funding
accrual, skip-if-truncated) — signal checked on every bar, direction **fades**
the triggering bar's own return sign (reversion, like v1). A `regime_filter`
parameter (`"low_liquidity"` / `"high_liquidity"` / `"all"`) implements the
required control-group comparison directly in the engine rather than as a
separate script, so every run (base case, walk-forward, sensitivity) reports
treatment and control side by side. 6 unit tests (`tests/test_engine_v3.py`):
no signal below the move-magnitude threshold, correct fade direction both
ways, and all three `regime_filter` values correctly include/exclude bars by
their `is_low_liquidity` flag.

### Base case (move_percentile_threshold=0.80, atr_stop_multiplier=2.0,
exit_horizon_hours=8) — full in-sample, all three regimes

| regime | trades | win rate | expectancy/trade | profit factor | Sharpe | max DD | final equity |
|---|---|---|---|---|---|---|---|
| **low_liquidity (treatment)** | 1141 | 46.7% | **-0.1353%** | 0.79 | -1.60 | -86.7% | 0.186x |
| high_liquidity (control) | 1550 | 42.6% | -0.2574% | 0.68 | -3.06 | -98.7% | 0.014x |
| all (unconditional) | 2432 | 44.0% | -0.2197% | 0.70 | -3.52 | -99.7% | 0.003x |

One-sample t-test on net per-trade returns vs. zero:

| regime | n | t | p |
|---|---|---|---|
| low_liquidity | 1141 | -2.948 | **0.0033** |
| high_liquidity | 1550 | -5.633 | <0.0001 |
| all | 2432 | -6.480 | <0.0001 |

Unlike v1/v2 (both "indistinguishable from zero"), v3's base case is
**statistically significantly negative** in all three regimes — a more
decisive result, just in the wrong direction for the hypothesis. Gross
(pre-cost) expectancy for low_liquidity is barely positive (+0.0279%) but
trade frequency is extremely high (335.8 trades/year — roughly one per day)
because the trigger (top 20% of a 30-day rolling distribution, checked every
bar) fires often; realistic round-trip costs (~0.14-0.22%) consume the tiny
gross edge many times over per year, compounding into an -86.7% max drawdown
and a final equity multiple of 0.186x (i.e. simulated account down ~81%).
Re-ran with `CostModel(0,0,0)` to confirm this isn't purely a cost-model
artifact: gross expectancy is still only +0.0279%/trade, i.e. even with zero
costs the raw edge is too thin relative to trade frequency to be interesting.

**The relative (treatment vs. control) comparison the hypothesis requires
does hold directionally** — low_liquidity's expectancy (-0.1353%) is less
negative than high_liquidity's (-0.2574%) in the base case — but the
hypothesis's own falsification criteria require the treatment group to be
profitable in its own right, not merely "less unprofitable than control,"
and it is not.

### Walk-forward (same 6 consecutive 207-day windows as v1/v2, treatment vs. control every window)

| window | dates | low_liq expectancy | low_liq Sharpe | high_liq expectancy | high_liq Sharpe |
|---|---|---|---|---|---|
| 1 | 2022-01-01 → 2022-07-26 | -0.1398% | -1.20 | -0.2514% | -2.22 |
| 2 | 2022-07-26 → 2023-02-18 | -0.1409% | -2.01 | -0.2733% | -3.26 |
| 3 | 2023-02-18 → 2023-09-13 | -0.1553% | -2.71 | -0.1757% | -2.42 |
| 4 | 2023-09-13 → 2024-04-07 | -0.1493% | -1.95 | **-0.4411%** | **-6.58** |
| 5 | 2024-04-07 → 2024-10-31 | -0.2395% | -2.87 | -0.1559% | -2.04 |
| 6 | 2024-10-31 → 2025-05-26 | +0.0155% | 0.17 | -0.2303% | -2.58 |

**low_liquidity is negative in 5 of 6 windows** (window 6 is ~breakeven, not
meaningfully positive: Sharpe 0.17 on 182 trades). **high_liquidity is
negative in all 6 windows**, and low_liquidity beats high_liquidity's
expectancy in **6 of 6 windows** — the treatment-vs-control ordering the
hypothesis predicts is remarkably consistent, but consistency of "less bad"
is not the same as "profitable," which is what the hypothesis actually
requires. Window 4's high_liquidity Sharpe of -6.58 is a red-flag magnitude;
checked with zeroed costs (still gross-negative that window, a real signal
issue tied to the Sep 2023-Apr 2024 regime, not a cost or engine artifact).

### Parameter sensitivity (±20-25% each, one at a time, base case held fixed otherwise, regime=low_liquidity)

| variant | expectancy/trade | Sharpe | profit factor |
|---|---|---|---|
| BASE | -0.1353% | -1.60 | 0.79 |
| move_percentile_threshold 0.80→0.64 (-20%) | -0.1306% | -2.04 | 0.77 |
| move_percentile_threshold 0.80→0.96 (+20%) | -0.3201% | -1.62 | 0.65 |
| atr_stop_multiplier 2.0→1.6 (-20%) | -0.1475% | -1.94 | 0.76 |
| atr_stop_multiplier 2.0→2.4 (+20%) | -0.1374% | -1.54 | 0.79 |
| exit_horizon_hours 8→6 (-25%) | -0.1182% | -1.63 | 0.79 |
| exit_horizon_hours 8→10 (+25%) | -0.1774% | -1.91 | 0.75 |

**All 7 variants (base + 6 perturbations) are negative** — no sign flips
anywhere in the grid tried, and Sharpe stays in a tight -1.5 to -2.0 band
throughout except the tighter move-threshold variant (-0.3201%, still just
more negative). This is the most decisive parameter-sensitivity result of
the three hypotheses tested this project: v1 flipped sign under most
perturbations (noise), v2 was mostly negative with two near-zero exceptions,
v3 is negative everywhere, consistently, by a statistically significant
margin.

### Holdout: not run for v3, by design

Same reasoning as v2: the holdout gets exactly one look, ever, reserved for a
rule that has *passed* its in-sample gates. v3's base case, all 6
walk-forward windows (bar one near-breakeven), and all 7 sensitivity variants
are negative, several with p<0.01 and Sharpe beyond -2 — a materially clearer
rejection than v1 or v2 had at this same checkpoint. Spending the one-time
holdout look here would confirm an already-unambiguous result at zero
decision value. Flagged explicitly, not silently skipped.

### Verdict: **REJECTED**

The liquidity-regime overshoot-reversion rule, as operationalized here
(top-20%-of-30-day move magnitude, ATR(14) stop, 8h time-boxed exit, fading
the triggering bar), shows statistically significant **negative** net
expectancy in-sample (p=0.0033), negative expectancy in 5 of 6 walk-forward
windows, and negative expectancy in all 7 parameter-sensitivity variants
tried. The required treatment-vs-control comparison (low-liquidity fade vs.
high-liquidity fade) does show the predicted direction consistently (6/6
windows, base case, sensitivity) — there may be a small, real liquidity-regime
effect on *relative* reversion strength — but it is nowhere near large enough
to overcome realistic trade frequency and Binance perp round-trip costs, so
the hypothesis as stated (a profitable, tradeable edge) is rejected.

**Single biggest remaining risk to this verdict:** the trigger as specified
(checked on every bar, top-20% threshold) produces very high trade frequency
(300-500 trades/year), which is itself likely why costs dominate — a stricter
trigger (higher percentile threshold, or a minimum-bars-between-signals
cooldown to stop re-triggering on the same dislocation repeatedly) might
change the cost/edge ratio materially. The +20% threshold variant
(move_percentile_threshold=0.96, 318 trades, still -0.32% expectancy) points
against this mattering much, but a cooldown/de-duplication mechanic specifically
was not tried and is a different lever than the threshold. Per the same
discipline applied to v1's and v2's "untried variants" risk, this would need
to be scoped as explicit, disclosed additional work against this same
hypothesis and same in-sample data in a future session — not grounds to
reverse this verdict now, and not something to chase immediately in this
session.

### Overall project status: three hypotheses tested, three rejected

`HYPOTHESIS_v1_REJECTED.md` (funding-extreme mean reversion),
`HYPOTHESIS_v2_REJECTED.md` (volatility-compression breakout continuation),
and `HYPOTHESIS.md` v3 (liquidity-regime overshoot reversion) have now all
failed the Phase 3 gate on BTCUSDT.P 1H/8h data, 2022-01-01 through
2025-05-26 in-sample. No strategy is being recommended for Phase 4. Per the
one-hypothesis-one-shot rule, no v4 is being proposed in this session.

---

**This verdict (REJECTED) was generated and self-graded in a single session
with no independent check.** Recommend a personal re-read of this entry,
specifically the walk-forward and sensitivity tables and the t-test results,
before treating it as final. Given three consecutive rejections across three
independently-reasoned mechanisms (crowd-unwind, stop-cascade, liquidity
regime) on the same instrument/timeframe, the honest recommendation is now
weighted more toward **stepping back to reconsider the approach at a higher
level** (different timeframe, different instrument, or a fundamentally
different research method) rather than continuing to search this specific
BTCUSDT.P 1H space for a fourth mechanism — three independent, reasonably
well-motivated ideas failing is itself evidence about the space being
searched, not just about the specific rules tried.

---

# HYPOTHESIS v4 — Daily-Bar Time-Series Momentum (structural pivot, not a 4th same-frequency mechanism)

**2026-07-14, same session, continued.** Discussed the cross-hypothesis
pattern across v1-v3 with the user directly: all three traded frequently
(145-716 trades/year) with thin gross edges that realistic costs consistently
dominated. Presented four higher-level pivot options (lower frequency,
trend/regime filter, different edge source entirely, or reconsidering
signal-trading as the goal) with honest tradeoffs for each; user chose
**lower frequency / longer holds**. This is explicitly framed as a structural
pivot to test whether trade frequency itself (not signal quality) was the
dominant obstacle in v1-v3 — not a fourth intraday mechanism chasing a
passing result. Per the one-hypothesis-one-shot rule, this is still tested
once and reported honestly.

`HYPOTHESIS.md` v3 renamed to `HYPOTHESIS_v3_REJECTED.md`; new `HYPOTHESIS.md`
written: **daily-bar time-series momentum** — trailing K-day cumulative
return determines long/short direction, held until the signal flips or an
ATR stop hits. Mechanism: documented time-series momentum (Moskowitz, Ooi &
Pedersen 2012; crypto-specific momentum findings e.g. Liu & Tsyvinski) driven
by slow-moving trend-following capital, not any of v1-v3's fast mechanisms.
The hypothesis explicitly disclosed in advance that daily bars over a
~3.4-year in-sample window would produce far fewer trades than v1-v3's
hourly signals, and that walk-forward windows might not clear the ~100-trade
comfort level v1-v3 achieved — flagged before running anything, not after.

### Phase 1 (daily resample, no new data pull)

`data/resample_daily.py` resamples the already-cleaned, gap-checked in-sample
hourly data (`data/processed/ohlcv_1h.parquet`, `funding_rate_8h.parquet`) to
UTC daily bars: standard OHLC aggregation (open=first/high=max/low=min/close=last),
funding summed per day (3 settlements/day). **29,790 hourly bars → 1,242
daily bars**, 2022-01-01 → 2025-05-26. One disclosed limitation: the first
and last calendar days of the range are partial (in-sample starts 01:00 UTC,
ends 06:00 UTC), so those two bars' OHLC reflect a partial day, not a full
24h — negligible given 1,242 total bars, but not silently hidden.

### Phase 2 (v4 features)

Added `trailing_return(close, k)` to `features/indicators.py` (simple
`close.pct_change(periods=k)`, no lookahead by construction), unit tested
against hand-computed values for k=1 and k=2 plus a no-lookahead mutation
test (`tests/test_indicators.py`, 3 new tests — 34 total in the suite now).
`features/build_features_v4.py` computes daily ATR(14) (same `atr()` function
already tested for v1-v3, just fed daily instead of hourly OHLC) — 1,228/1,242
bars valid, 14-bar warmup. The lookback K is a swept Phase 3 parameter, same
pattern as v2/v3's swept windows.

### Phase 3 (v4 engine) — structurally different from v1-v3

`backtest/engine_v4.py` has no fixed time-boxed exit — a position holds as
long as the trend signal (trailing K-day return) agrees with its direction,
and reverses (closes + reopens) the day after the signal flips, in addition
to an ATR-based stop. This required a "pending action" state machine (decide
at bar close, execute at next bar's open, same convention as v1-v3, but a
reversal both closes and reopens in the same executed bar). A position still
open at the dataset's end is dropped, not force-closed — no fixed horizon to
check truncation against, unlike v1-v3. 4 unit tests (`tests/test_engine_v4.py`):
profitable long/short trend-catch-then-flip scenarios (hand-computed exact
entry/exit prices), correct ATR-stop price and early exit, and open positions
at data-end correctly excluded from output.

One engine subtlety worth logging: walk-forward computes `trend_return` on
the **full in-sample history before slicing into windows** (`walk_forward_v4.py`),
not per-window — with a 30-day lookback and ~207-day windows, recomputing
per-window (as v2/v3's swept parameters do, since their warmup loss is ~1 day
out of 207) would have wasted ~14.5% of each window's start on avoidable
warmup NaN. `engine_v4.run_backtest` was written to reuse a precomputed
`trend_return` column when present (base case/sensitivity still compute it
per-run on the fly, since those don't need windowing).

### Base case (lookback_days=30, atr_stop_multiplier=2.5) — full in-sample

| metric | value |
|---|---|
| trades | 115 |
| win rate | 35.7% |
| avg win / avg loss | 8.738% / -4.279% (ratio 2.04) |
| expectancy/trade (net) | **+0.3614%** |
| profit factor | 1.13 |
| Sharpe (trade-freq annualized) | 0.19 |
| Sortino | 0.58 |
| max drawdown | -49.09% (duration 15 trades) |
| longest losing streak | 8 |
| trades/year | 33.8 (an order of magnitude below v1-v3's 45-716/year, as intended) |
| gross expectancy (pre-cost) | 0.6101% |
| funding contribution | -0.1038% |
| final equity multiple | 0.867x |

115 trades clears the 100-trade minimum, barely. One-sample t-test: **t=0.359,
p=0.7203** — despite a positive point estimate, not statistically
distinguishable from zero (return std of 16.96% vs. a 0.36% mean — enormous
dispersion). The classic low-win-rate/high-payoff trend-following signature
is visible (35.7% win rate, 2.04 avg win/loss ratio) — consistent with
CLAUDE.md's "honest expectations" for this style — but the **final equity
multiple (0.867x) is below 1** despite positive arithmetic expectancy: a
geometric-compounding/volatility-drag effect from the -49% max drawdown
occurring before later gains had a full capital base to compound on. Median
holding period was only 3 days (mean 10, max 99) despite the 30-day signal
lookback — BTC's daily-return noise flips the 30-day cumulative-return sign
more often than the lookback length might suggest.

### Walk-forward (same 6 consecutive 207-day windows as v1-v3)

| window | dates | trades | expectancy/trade | Sharpe | max DD |
|---|---|---|---|---|---|
| 1 | 2022-01-01 → 2022-07-26 | 18 | -0.906% | -0.46 | -45.9% |
| 2 | 2022-07-26 → 2023-02-18 | 23 | -1.370% | -1.99 | -34.3% |
| 3 | 2023-02-18 → 2023-09-13 | 11 | +1.250% | 0.64 | -7.7% |
| 4 | 2023-09-13 → 2024-04-07 | 15 | **+3.680%** | **1.02** | -32.1% |
| 5 | 2024-04-07 → 2024-10-31 | 23 | -2.183% | -2.51 | -49.1% |
| 6 | 2024-10-31 → 2025-05-26 | 24 | -0.135% | -0.10 | -35.1% |

**4 of 6 windows negative**; window 4 (Sep 2023-Apr 2024, BTC's major
pre-halving rally) is the standout, and is almost entirely responsible for
the positive base-case aggregate — remove it and the other 5 windows sum to
clearly negative. Per-window trade counts (11-24) are far below v1-v3's
per-window counts (60-97), exactly the sample-size tradeoff disclosed in
`HYPOTHESIS.md` in advance — individual window Sharpe/expectancy figures
here carry much wider uncertainty than the equivalent v1-v3 numbers and
should be read accordingly.

### Parameter sensitivity (lookback_days ±20%, atr_stop_multiplier ±20%) with t-tests

| variant | n | expectancy/trade | Sharpe | t-stat | p-value |
|---|---|---|---|---|---|
| BASE (30d, 2.5) | 115 | +0.361% | 0.19 | 0.359 | 0.720 |
| lookback_days=24 (-20%) | 121 | -0.273% | -0.16 | -0.298 | 0.766 |
| lookback_days=36 (+20%) | 84 | +1.567% | 0.65 | 1.206 | 0.231 |
| atr_stop_multiplier=2.0 (-20%) | 117 | +0.477% | 0.25 | 0.467 | 0.642 |
| atr_stop_multiplier=3.0 (+20%) | 114 | +0.423% | 0.23 | 0.420 | 0.676 |

**None of the 5 variants (base + 4 perturbations) reach conventional
statistical significance** — the best (lookback_days=36, p=0.231) is still
far from a defensible edge. Direction flips once (lookback_days=24 goes
negative) but magnitudes throughout are small relative to their own standard
errors — this reads as "indistinguishable from zero, with high variance,"
not "fragile but real" (v1's pattern) or "consistently negative" (v3's
pattern). It's its own, third kind of null result.

### Holdout: not run for v4, by design

Same reasoning as v2/v3. No variant (base or any of 4 perturbations) reaches
statistical significance, walk-forward is majority-negative and dominated by
a single trending window, and there is no parameter region that looks
different from noise. Spending the one-time holdout look here would confirm
an already-unclear result at zero decision value.

### Verdict: **REJECTED**

The daily-bar time-series momentum rule, as operationalized here (K-day
trailing return sign, signal-flip + ATR-stop exits), does **not** show a
statistically significant edge in-sample (best p=0.231 across 5
configurations tried), is majority-negative across walk-forward windows with
the entire aggregate profit attributable to one strong trending period
(Sep 2023-Apr 2024), and shows no parameter region that clears noise. The
structural pivot's own premise gets a partial, informative answer: trade
frequency dropped by an order of magnitude as intended (33.8/year vs. v1-v3's
45-716/year) and the classic trend-following payoff shape did appear (low
win rate, high win/loss ratio) — but variance/tail risk (max DD up to -64%
under perturbation, geometric-vs-arithmetic drag pulling the base case's
final equity below 1x despite positive average) replaced "cost drag" as the
dominant obstacle to statistical significance, rather than eliminating the
obstacle entirely. Lower frequency alone did not turn v1-v3's problem into a
working strategy; it traded a cost problem for a variance/sample-size
problem.

**Single biggest remaining risk to this verdict:** only trend-following with
symmetric long/short exposure was tested. BTC's realized returns over
2022-2025 are asymmetric (a severe 2022 bear, a strong 2023-24 bull) — a
long-only or long-biased variant, or vol-targeted position sizing (explicitly
out of scope here per CLAUDE.md's Phase 3/4 boundary — sizing belongs to
Phase 4), might behave differently, particularly given how much of the
aggregate result rode on window 4's uptrend specifically. That is a
legitimate follow-on question, but per the same discipline applied to v1-v3's
"untried variants" risk, it is scoped as explicit future work, not grounds to
reverse this verdict or to chase immediately in this session.

### Overall project status: four hypotheses tested, four rejected, across two timeframes

Three intraday (1H) mechanisms — funding-extreme reversion, volatility-breakout
continuation, liquidity-regime reversion — and one daily-bar mechanism —
time-series momentum — have now all failed the Phase 3 gate on BTCUSDT.P,
2022-01-01 through 2025-05-26 in-sample. The four failures are not
redundant: v1-v3 died to cost drag from high trade frequency; v4, run at an
order of magnitude lower frequency specifically to test that diagnosis, died
instead to variance/sample-size (thin statistical power, one trending window
carrying the whole aggregate). No strategy is being recommended for Phase 4.

---

**This verdict (REJECTED) was generated and self-graded in a single session
with no independent check**, same caveat as v1-v3. Given four independent
rejections spanning two timeframes and four distinct mechanisms, the honest
recommendation is to treat this as a strong signal about the difficulty of
finding a standalone, rule-based directional edge on BTCUSDT.P with ~4.5
years of OHLCV+funding data specifically — not to immediately try a fifth
variant. The options presented before v4 (different edge source entirely —
spot-perp basis, cross-exchange spreads, on-chain flow — or reconsidering
whether standalone signal-trading is the right goal vs. a risk-managed
strategic-exposure approach) remain the most honest next steps, now with more
evidence behind them than when first raised.
