"""Price alert monitor — checks if positions hit stop-loss or take-profit.

Reads the latest signal record, compares target/stop prices against current data.
Generates alerts when triggered.

Storage: data_store/alerts/{date}.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from config.settings import settings
from data.storage.parquet_store import load_hist
from engine.tracker import HISTORY_DIR, _load_record

logger = logging.getLogger(__name__)

ALERTS_DIR = settings.data.data_dir / "alerts"


class AlertType(StrEnum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    APPROACHING_STOP = "approaching_stop"
    APPROACHING_TARGET = "approaching_target"


@dataclass(frozen=True)
class PriceAlert:
    symbol: str
    alert_type: AlertType
    signal_price: float
    trigger_price: float  # Target or stop price
    current_price: float
    distance_pct: float  # How close (negative = breached)
    message: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "alert_type": self.alert_type.value,
            "signal_price": round(self.signal_price, 4),
            "trigger_price": round(self.trigger_price, 4),
            "current_price": round(self.current_price, 4),
            "distance_pct": round(self.distance_pct, 2),
            "message": self.message,
        }


def check_alerts(signal_date: date | None = None) -> list[PriceAlert]:
    """Check all active signals for stop-loss and take-profit triggers.

    Args:
        signal_date: Which signal record to check. Default = most recent.

    Returns:
        List of triggered alerts, sorted by urgency.
    """
    # Find most recent signal record
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    if signal_date is None:
        files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
        if not files:
            return []
        signal_date = date.fromisoformat(files[0].stem)

    record = _load_record(signal_date)
    if not record:
        return []

    alerts: list[PriceAlert] = []

    for sig in record["signals"]:
        symbol = sig["symbol"]
        direction = sig["direction"]

        # Only check buy signals (we care about positions we might hold)
        if direction not in ("strong_buy", "buy"):
            continue

        df = load_hist(symbol)
        if df.empty:
            continue

        current_price = float(df["close"].iloc[-1])
        target = sig["target_price"]
        stop = sig["stop_loss"]
        entry = sig["entry_price"]

        # Check stop-loss
        if current_price <= stop:
            alerts.append(
                PriceAlert(
                    symbol=symbol,
                    alert_type=AlertType.STOP_LOSS,
                    signal_price=entry,
                    trigger_price=stop,
                    current_price=current_price,
                    distance_pct=(current_price / stop - 1) * 100,
                    message=f"已触发止损! 当前{current_price:.3f} < 止损{stop:.3f}",
                )
            )
        elif current_price <= stop * 1.02:
            alerts.append(
                PriceAlert(
                    symbol=symbol,
                    alert_type=AlertType.APPROACHING_STOP,
                    signal_price=entry,
                    trigger_price=stop,
                    current_price=current_price,
                    distance_pct=(current_price / stop - 1) * 100,
                    message=(
                        f"接近止损! 当前{current_price:.3f}, "
                        f"止损{stop:.3f} (距离{(current_price / stop - 1) * 100:.1f}%)"
                    ),
                )
            )

        # Check take-profit
        if current_price >= target:
            alerts.append(
                PriceAlert(
                    symbol=symbol,
                    alert_type=AlertType.TAKE_PROFIT,
                    signal_price=entry,
                    trigger_price=target,
                    current_price=current_price,
                    distance_pct=(current_price / target - 1) * 100,
                    message=f"已到目标价! 当前{current_price:.3f} >= 目标{target:.3f}",
                )
            )
        elif current_price >= target * 0.97:
            alerts.append(
                PriceAlert(
                    symbol=symbol,
                    alert_type=AlertType.APPROACHING_TARGET,
                    signal_price=entry,
                    trigger_price=target,
                    current_price=current_price,
                    distance_pct=(1 - current_price / target) * 100,
                    message=(
                        f"接近目标! 当前{current_price:.3f}, "
                        f"目标{target:.3f} (距离{(1 - current_price / target) * 100:.1f}%)"
                    ),
                )
            )

    # Sort: triggered alerts first, then approaching
    priority = {
        AlertType.STOP_LOSS: 0,
        AlertType.TAKE_PROFIT: 1,
        AlertType.APPROACHING_STOP: 2,
        AlertType.APPROACHING_TARGET: 3,
    }
    alerts.sort(key=lambda a: priority[a.alert_type])

    # Save alerts
    if alerts:
        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        alert_file = ALERTS_DIR / f"{date.today().isoformat()}.json"
        alert_file.write_text(
            json.dumps(
                [a.to_dict() for a in alerts],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info("Generated %d alerts → %s", len(alerts), alert_file)

    return alerts
