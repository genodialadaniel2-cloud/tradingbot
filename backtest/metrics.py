"""Trade-level metrics for a backtest run. Operates on the DataFrame returned by backtest.engine.run_backtest."""

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, sample_days: float, pnl_col: str = "net_pnl_pct") -> dict:
    if len(trades) == 0:
        return {"total_trades": 0}

    returns = trades[pnl_col].to_numpy()
    n = len(returns)
    wins = returns[returns > 0]
    losses = returns[returns < 0]

    win_rate = len(wins) / n
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    avg_win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else np.nan
    expectancy = returns.mean()
    profit_factor = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else np.inf

    trades_per_year = n / (sample_days / 365.25) if sample_days > 0 else np.nan
    std = returns.std(ddof=1) if n > 1 else np.nan
    sharpe = (expectancy / std) * np.sqrt(trades_per_year) if std and std > 0 else np.nan

    downside = returns[returns < 0]
    downside_std = downside.std(ddof=1) if len(downside) > 1 else np.nan
    sortino = (expectancy / downside_std) * np.sqrt(trades_per_year) if downside_std and downside_std > 0 else np.nan

    equity = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(equity)
    drawdown = (equity - running_max) / running_max
    max_drawdown = drawdown.min()
    max_dd_end_idx = drawdown.argmin()
    max_dd_start_idx = np.argmax(equity[: max_dd_end_idx + 1]) if max_dd_end_idx > 0 else 0
    max_dd_duration_trades = max_dd_end_idx - max_dd_start_idx

    losing_streak = 0
    longest_losing_streak = 0
    for r in returns:
        if r < 0:
            losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, losing_streak)
        else:
            losing_streak = 0

    return {
        "total_trades": n,
        "win_rate": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "avg_win_loss_ratio": avg_win_loss_ratio,
        "expectancy_pct": expectancy,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_drawdown,
        "max_drawdown_duration_trades": int(max_dd_duration_trades),
        "longest_losing_streak": longest_losing_streak,
        "trades_per_year": trades_per_year,
        "final_equity_multiple": equity[-1] if n else np.nan,
    }


def format_metrics(m: dict, label: str = "") -> str:
    if m.get("total_trades", 0) == 0:
        return f"{label}: 0 trades"
    lines = [
        f"{label}",
        f"  trades:              {m['total_trades']}",
        f"  win rate:            {m['win_rate']:.1%}",
        f"  avg win / avg loss:  {m['avg_win_pct']:.3%} / {m['avg_loss_pct']:.3%}  (ratio {m['avg_win_loss_ratio']:.2f})",
        f"  expectancy/trade:    {m['expectancy_pct']:.4%}",
        f"  profit factor:       {m['profit_factor']:.2f}",
        f"  Sharpe (trade-freq annualized): {m['sharpe']:.2f}",
        f"  Sortino:             {m['sortino']:.2f}",
        f"  max drawdown:        {m['max_drawdown_pct']:.2%}  (duration {m['max_drawdown_duration_trades']} trades)",
        f"  longest losing streak: {m['longest_losing_streak']}",
        f"  trades/year:         {m['trades_per_year']:.1f}",
        f"  final equity multiple: {m['final_equity_multiple']:.3f}x",
    ]
    return "\n".join(lines)
