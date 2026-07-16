"""
Cost model for Binance USDⓈ-M perpetual futures (BTC/USDT:USDT), VIP0 tier.
Every number here is a modeling assumption, not a measured fill -- logged in
RESEARCH_LOG.md alongside the strategy parameters it's paired with.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    taker_fee: float = 0.0005       # Binance USDM futures VIP0 taker fee, both entry and time-exit assumed market orders
    slippage_normal: float = 0.0002  # estimated slippage on a normal (time-exit) market fill
    slippage_stop: float = 0.0010    # stops fill worse -- modeled 5x normal slippage per CLAUDE.md's "worse than intuition" warning


def round_trip_cost_pct(cost_model: CostModel, exit_is_stop: bool) -> float:
    """Total fee+slippage drag as a fraction of notional, both legs combined."""
    entry_cost = cost_model.taker_fee + cost_model.slippage_normal
    exit_slippage = cost_model.slippage_stop if exit_is_stop else cost_model.slippage_normal
    exit_cost = cost_model.taker_fee + exit_slippage
    return entry_cost + exit_cost


def funding_pnl_pct(direction: int, funding_rate: float) -> float:
    """
    PnL (as a fraction of notional) from one funding settlement crossed while
    holding a position. Sign convention: positive funding rate means longs pay
    shorts; negative means shorts pay longs.

    direction: +1 for long, -1 for short.
    """
    return -direction * funding_rate
