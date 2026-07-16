"""
Phase 3 parameter sensitivity: perturb each numeric TBD parameter +-20% one at
a time (holding the others at base case) and report degradation. This is a
disclosed parameter search, not silent retuning -- every value tried here is
logged in RESEARCH_LOG.md, win or lose.
"""

from backtest.engine import StrategyParams, run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.run_backtest import load_in_sample, sample_days

BASE = StrategyParams()


def main():
    df = load_in_sample()
    days = sample_days(df)

    variants = {
        "BASE (percentile_tail=0.05, atr_mult=2.0, horizon=12h)": BASE,
        "percentile_tail=0.04 (-20%)": StrategyParams(percentile_tail=0.04),
        "percentile_tail=0.06 (+20%)": StrategyParams(percentile_tail=0.06),
        "atr_stop_multiplier=1.6 (-20%)": StrategyParams(atr_stop_multiplier=1.6),
        "atr_stop_multiplier=2.4 (+20%)": StrategyParams(atr_stop_multiplier=2.4),
        "exit_horizon_hours=10 (-17%)": StrategyParams(exit_horizon_hours=10),
        "exit_horizon_hours=14 (+17%)": StrategyParams(exit_horizon_hours=14),
    }

    for label, params in variants.items():
        trades = run_backtest(df, params)
        m = compute_metrics(trades, days)
        print(format_metrics(m, label))
        print()


if __name__ == "__main__":
    main()
