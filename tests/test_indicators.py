import numpy as np
import pandas as pd
import talib

from features.indicators import (
    abs_return_percentile,
    atr,
    funding_percentile,
    funding_zscore,
    is_low_liquidity_window,
    rolling_prior_range,
    rsi,
    trailing_return,
    volatility_percentile,
)


def test_atr_matches_talib_on_synthetic_data():
    rng = np.random.default_rng(42)
    n = 500
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 2.0, n)
    low = close - rng.uniform(0.1, 2.0, n)
    df = pd.DataFrame({"high": high, "low": low, "close": close})

    mine = atr(df["high"], df["low"], df["close"], period=14)
    reference = talib.ATR(df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(), timeperiod=14)

    both_valid = mine.notna().to_numpy() & ~np.isnan(reference)
    assert both_valid.sum() > 400
    assert np.allclose(mine.to_numpy()[both_valid], reference[both_valid], rtol=1e-6, atol=1e-8)


def test_funding_zscore_matches_manual_rolling_stats():
    rng = np.random.default_rng(7)
    fr = pd.Series(rng.normal(0, 0.0003, 400))
    window = 90

    mine = funding_zscore(fr, window=window, min_periods=window)

    ref_mean = talib.SMA(fr.to_numpy(), timeperiod=window)
    ref_std = talib.STDDEV(fr.to_numpy(), timeperiod=window, nbdev=1)  # population std, matches ddof=0
    ref_zscore = (fr.to_numpy() - ref_mean) / ref_std

    both_valid = mine.notna().to_numpy() & ~np.isnan(ref_zscore)
    assert both_valid.sum() > 300
    assert np.allclose(mine.to_numpy()[both_valid], ref_zscore[both_valid], rtol=1e-6, atol=1e-8)


def test_funding_percentile_known_values():
    # Deterministic series: percentile rank has no ta-lib equivalent, so this
    # is a hand-computed reference instead of a library cross-check.
    fr = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = funding_percentile(fr, window=5, min_periods=1)

    # window=1 -> value is always its own only member -> rank 1.0
    assert result.iloc[0] == 1.0
    # first 3 values [1,2,3] -> current=3 is the max -> rank 3/3 = 1.0
    assert result.iloc[2] == 1.0
    # full window [1,2,3,4,5] -> current=5 is the max -> rank 5/5 = 1.0
    assert result.iloc[4] == 1.0

    fr_desc = pd.Series([5.0, 4.0, 3.0, 2.0, 1.0])
    result_desc = funding_percentile(fr_desc, window=5, min_periods=1)
    # full window [5,4,3,2,1] -> current=1 is the min -> rank 1/5 = 0.2
    assert result_desc.iloc[4] == 0.2


def test_no_lookahead_funding_zscore_stable_under_future_mutation():
    fr = pd.Series([0.0001, 0.0002, -0.0001, 0.0003, 0.0005, -0.0002, 0.0001, 0.0004] * 10)
    window = 20
    before = funding_zscore(fr, window=window, min_periods=5)

    mutated = fr.copy()
    mutated.iloc[-1] = 999.0  # change only the very last value
    after = funding_zscore(mutated, window=window, min_periods=5)

    # every value except the last (and any window that now includes the mutated
    # tail) must be unchanged -- a value at row i must never depend on row > i.
    assert np.allclose(before.iloc[: len(fr) - window].to_numpy(), after.iloc[: len(fr) - window].to_numpy(), equal_nan=True)


def test_rolling_prior_range_excludes_current_bar():
    # window=3, bar at index 4 (value 100) must be judged against bars [1,2,3]
    # only (values 10,20,30) -- NOT against its own value, or every bar would
    # trivially "break out" of a range that includes itself.
    high = pd.Series([10.0, 20.0, 30.0, 100.0, 5.0])
    low = high.copy()
    prior_high, prior_low = rolling_prior_range(high, low, window=3)

    assert prior_high.iloc[3] == 30.0  # max of bars 0,1,2 -- not bar 3's own 100
    assert prior_low.iloc[3] == 10.0
    assert prior_high.iloc[4] == 100.0  # max of bars 1,2,3 -- not bar 4's own 5
    assert prior_low.iloc[4] == 20.0


def test_no_lookahead_rolling_range_stable_under_future_mutation():
    rng = np.random.default_rng(3)
    n = 100
    high = pd.Series(100 + rng.normal(0, 2, n))
    low = high - rng.uniform(0.5, 2.0, n)

    before_high, before_low = rolling_prior_range(high, low, window=10)

    mutated_high = high.copy()
    mutated_high.iloc[-1] = 10000.0
    after_high, after_low = rolling_prior_range(mutated_high, low, window=10)

    assert np.allclose(before_high.iloc[: n - 1].to_numpy(), after_high.iloc[: n - 1].to_numpy(), equal_nan=True)
    assert np.allclose(before_low.iloc[: n - 1].to_numpy(), after_low.iloc[: n - 1].to_numpy(), equal_nan=True)


def test_volatility_percentile_known_values():
    close = pd.Series([100.0] * 5)
    atr_series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])  # atr/close is just atr since close=100... scale doesn't matter for rank
    result = volatility_percentile(atr_series, close, window=5, min_periods=1)
    assert result.iloc[4] == 1.0  # current (5.0) is the max of the trailing window -> rank 1.0
    assert result.iloc[0] == 1.0  # window of 1 -> always rank 1.0


def test_no_lookahead_atr_stable_under_future_mutation():
    rng = np.random.default_rng(1)
    n = 100
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + 1
    low = close - 1
    df = pd.DataFrame({"high": high, "low": low, "close": close})

    before = atr(df["high"], df["low"], df["close"], period=14)

    mutated = df.copy()
    mutated.loc[n - 1, ["high", "low", "close"]] = [10000, 9000, 9500]
    after = atr(mutated["high"], mutated["low"], mutated["close"], period=14)

    assert np.allclose(before.iloc[: n - 1].to_numpy(), after.iloc[: n - 1].to_numpy(), equal_nan=True)


def test_rsi_matches_talib_on_synthetic_data():
    rng = np.random.default_rng(21)
    n = 500
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)))

    mine = rsi(close, period=14)
    reference = talib.RSI(close.to_numpy(), timeperiod=14)

    both_valid = mine.notna().to_numpy() & ~np.isnan(reference)
    assert both_valid.sum() > 400
    assert np.allclose(mine.to_numpy()[both_valid], reference[both_valid], rtol=1e-6, atol=1e-8)


def test_rsi_bounded_zero_to_hundred():
    rng = np.random.default_rng(22)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    result = rsi(close, period=14).dropna()
    assert (result >= 0).all() and (result <= 100).all()


def test_no_lookahead_rsi_stable_under_future_mutation():
    rng = np.random.default_rng(23)
    n = 100
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)))

    before = rsi(close, period=14)

    mutated = close.copy()
    mutated.iloc[-1] = 10000.0
    after = rsi(mutated, period=14)

    assert np.allclose(before.iloc[: n - 1].to_numpy(), after.iloc[: n - 1].to_numpy(), equal_nan=True)


def test_rsi_flat_market_is_neutral_not_overbought():
    # zero price movement for period+ bars (e.g. a dead/illiquid pair) must
    # be neutral (50), not maximally overbought -- avg_gain==0 and
    # avg_loss==0 is 0/0, not "all gains no losses".
    flat = pd.Series([100.0] * 25)
    result = rsi(flat, period=14)
    assert result.iloc[-1] == 50.0


def test_rsi_all_losses_is_zero_not_neutral():
    # sanity check the flat-market fix doesn't clobber the genuine
    # all-losses-no-gains case, which should still be 0 (maximally oversold).
    declining = pd.Series([100.0 - i for i in range(25)])
    result = rsi(declining, period=14)
    assert result.iloc[-1] == 0.0


def test_rsi_returns_all_nan_for_too_short_input_instead_of_raising():
    close = pd.Series([100.0, 101.0, 99.0, 102.0])
    result = rsi(close, period=14)
    assert len(result) == len(close)
    assert result.isna().all()


def test_is_low_liquidity_window_flags_asian_session_and_weekend():
    # Mon 2024-01-01 03:00 UTC -> Asian session (hour<8) -> low-liquidity.
    # Mon 2024-01-01 12:00 UTC -> weekday, high-liquidity hours -> NOT low-liquidity.
    # Sat 2024-01-06 15:00 UTC -> weekend, non-Asian hour -> still low-liquidity (weekend rule).
    # Sun 2024-01-07 02:00 UTC -> weekend AND Asian hour -> low-liquidity (both rules agree).
    dt = pd.to_datetime(
        ["2024-01-01T03:00:00Z", "2024-01-01T12:00:00Z", "2024-01-06T15:00:00Z", "2024-01-07T02:00:00Z"]
    )
    result = is_low_liquidity_window(pd.Series(dt))
    assert result.tolist() == [True, False, True, True]


def test_abs_return_percentile_known_values():
    # Deterministic price series where |return| is monotonically increasing --
    # the current (largest-so-far) return should always rank at the top of its
    # window. window=2 keeps pct_change()'s leading NaN (index 0) out of the
    # windows checked below, so it isn't counted against the rank.
    close = pd.Series([100.0, 101.0, 103.0, 107.0, 115.0])  # returns: -, 1%, ~1.98%, ~3.88%, ~7.48%
    result = abs_return_percentile(close, window=2, min_periods=1)
    assert result.iloc[2] == 1.0  # window [idx1, idx2] -> current (idx2) is the max -> rank 1.0
    assert result.iloc[4] == 1.0  # window [idx3, idx4] -> current (idx4) is the max -> rank 1.0


def test_no_lookahead_abs_return_percentile_stable_under_future_mutation():
    rng = np.random.default_rng(11)
    n = 100
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)))

    before = abs_return_percentile(close, window=20, min_periods=5)

    mutated = close.copy()
    mutated.iloc[-1] = 10000.0
    after = abs_return_percentile(mutated, window=20, min_periods=5)

    assert np.allclose(before.iloc[: n - 1].to_numpy(), after.iloc[: n - 1].to_numpy(), equal_nan=True)


def test_trailing_return_known_values():
    close = pd.Series([100.0, 110.0, 121.0, 108.9])
    result = trailing_return(close, k=1)
    assert np.isnan(result.iloc[0])
    assert np.isclose(result.iloc[1], 0.10)  # 110/100 - 1
    assert np.isclose(result.iloc[2], 0.10)  # 121/110 - 1
    assert np.isclose(result.iloc[3], -0.10)  # 108.9/121 - 1

    result_k2 = trailing_return(close, k=2)
    assert np.isnan(result_k2.iloc[1])
    assert np.isclose(result_k2.iloc[2], 0.21)  # 121/100 - 1
    assert np.isclose(result_k2.iloc[3], -0.01)  # 108.9/110 - 1


def test_no_lookahead_trailing_return_stable_under_future_mutation():
    rng = np.random.default_rng(5)
    n = 60
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)))

    before = trailing_return(close, k=10)

    mutated = close.copy()
    mutated.iloc[-1] = 10000.0
    after = trailing_return(mutated, k=10)

    assert np.allclose(before.iloc[: n - 1].to_numpy(), after.iloc[: n - 1].to_numpy(), equal_nan=True)
