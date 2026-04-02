"""Core backtest engine with strict T+1 enforcement.

Key rules:
- Signal on T → execute on T+1 open
- Commission = max(amount * rate, min_commission)
- Slippage = execution_price * (1 ± slippage)
- No shorting (ETF long-only)
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from engine.types import (
    BacktestConfig,
    BacktestResult,
    PortfolioSnapshot,
    Position,
    Side,
    Signal,
    Trade,
)

logger = logging.getLogger(__name__)

# Type alias for strategy function
StrategyFn = Callable[[pd.DataFrame, dict[str, Position], float, pd.Timestamp], list[Signal]]


def _apply_slippage(price: float, side: Side, slippage: float) -> float:
    """Apply slippage: buy higher, sell lower."""
    if side == Side.BUY:
        return price * (1 + slippage)
    return price * (1 - slippage)


def _calc_commission(amount: float, rate: float, min_commission: float) -> float:
    return max(abs(amount) * rate, min_commission)


def _get_price(
    data: dict[str, pd.DataFrame],
    symbol: str,
    date: pd.Timestamp,
    col: str,
) -> float | None:
    """Safely get a price from the data dict."""
    if symbol not in data:
        return None
    df = data[symbol]
    if date not in df.index:
        return None
    return float(df.loc[date, col])


def run_backtest(
    data: dict[str, pd.DataFrame],
    strategy_fn: StrategyFn,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a backtest over historical data.

    Args:
        data: Dict of symbol → OHLCV DataFrame (DatetimeIndex named 'date').
        strategy_fn: Function(data, positions, cash, current_date) → list[Signal].
                     Called on each trading day with data up to and including that day.
        config: Backtest parameters. Uses defaults if None.

    Returns:
        BacktestResult with equity curve, trades, and snapshots.
    """
    if config is None:
        config = BacktestConfig()

    # Build sorted list of all trading dates
    all_dates: set[pd.Timestamp] = set()
    for df in data.values():
        all_dates.update(df.index)
    dates = sorted(all_dates)

    if not dates:
        return BacktestResult(config=config, snapshots=(), trades=())

    cash = config.initial_cash
    positions: dict[str, Position] = {}
    pending_signals: list[Signal] = []  # Signals waiting for T+1 execution
    all_trades: list[Trade] = []
    snapshots: list[PortfolioSnapshot] = []
    prev_total = config.initial_cash

    for date in dates:
        # ── 1. Execute pending signals from yesterday (T+1 rule) ──
        executed_signals: list[Signal] = []
        for signal in pending_signals:
            open_price = _get_price(data, signal.symbol, date, "open")
            if open_price is None:
                logger.warning("No open price for %s on %s, skipping signal", signal.symbol, date)
                continue

            exec_price = _apply_slippage(open_price, signal.side, config.slippage)

            if signal.side == Side.BUY:
                # Calculate shares based on target weight
                target_value = prev_total * signal.weight
                max_affordable = cash / (exec_price * (1 + config.commission_rate))
                shares = min(int(target_value / exec_price), int(max_affordable))
                if shares <= 0:
                    continue

                cost = shares * exec_price
                commission = _calc_commission(cost, config.commission_rate, config.min_commission)
                cash -= cost + commission

                # Update position (immutable)
                old_pos = positions.get(signal.symbol)
                if old_pos:
                    total_shares = old_pos.shares + shares
                    old_value = old_pos.avg_cost * old_pos.shares
                    avg_cost = (old_value + exec_price * shares) / total_shares
                    positions[signal.symbol] = Position(
                        symbol=signal.symbol,
                        shares=total_shares,
                        avg_cost=avg_cost,
                        entry_date=old_pos.entry_date,
                    )
                else:
                    positions[signal.symbol] = Position(
                        symbol=signal.symbol,
                        shares=shares,
                        avg_cost=exec_price,
                        entry_date=date,
                    )

                all_trades.append(
                    Trade(
                        date=date,
                        symbol=signal.symbol,
                        side=Side.BUY,
                        price=exec_price,
                        shares=shares,
                        commission=commission,
                        signal_date=signal.date,
                    )
                )

            elif signal.side == Side.SELL:
                pos = positions.get(signal.symbol)
                if not pos or pos.shares <= 0:
                    continue

                shares = pos.shares
                proceeds = shares * exec_price
                commission = _calc_commission(
                    proceeds,
                    config.commission_rate,
                    config.min_commission,
                )
                cash += proceeds - commission

                del positions[signal.symbol]

                all_trades.append(
                    Trade(
                        date=date,
                        symbol=signal.symbol,
                        side=Side.SELL,
                        price=exec_price,
                        shares=shares,
                        commission=commission,
                        signal_date=signal.date,
                    )
                )

            executed_signals.append(signal)

        pending_signals = []

        # ── 2. Calculate portfolio value ──
        position_value = 0.0
        for sym, pos in positions.items():
            close_price = _get_price(data, sym, date, "close")
            if close_price is not None:
                position_value += pos.shares * close_price

        total_value = cash + position_value
        daily_return = (total_value / prev_total - 1) if prev_total > 0 else 0.0

        snapshots.append(
            PortfolioSnapshot(
                date=date,
                cash=cash,
                positions=tuple(positions.values()),
                total_value=total_value,
                daily_return=daily_return,
            )
        )
        prev_total = total_value

        # ── 3. Generate new signals (strategy sees data up to today) ──
        # Slice data to prevent look-ahead bias
        data_up_to_today = {sym: df.loc[:date] for sym, df in data.items() if date in df.index}
        new_signals = strategy_fn(data_up_to_today, positions, cash, date)

        # Validate: signals should be for today
        for sig in new_signals:
            if sig.date != date:
                logger.warning("Signal date %s != current date %s, adjusting", sig.date, date)
            pending_signals.append(
                Signal(date=date, symbol=sig.symbol, side=sig.side, weight=sig.weight)
            )

    return BacktestResult(
        config=config,
        snapshots=tuple(snapshots),
        trades=tuple(all_trades),
    )
