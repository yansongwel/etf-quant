"""Record today's signals for accuracy tracking.

Run daily after market close + data collection (e.g., 15:40 CST).
Calls the signal engine and persists results to signal_history/.
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from config.constants import DEFAULT_ETF_LIST
    from config.settings import settings
    from data.storage.parquet_store import load_hist
    from engine.signals import generate_signals_batch
    from engine.tracker import record_signals

    # Load all available ETF data
    data_dir = settings.data.data_dir / "etf_hist"
    if data_dir.exists():
        sym_list = sorted(f.stem for f in data_dir.glob("*.parquet"))
    else:
        sym_list = [e["symbol"] for e in DEFAULT_ETF_LIST]

    data = {}
    for sym in sym_list:
        df = load_hist(sym)
        if not df.empty:
            data[sym] = df

    if not data:
        logger.error("No data available — skipping signal recording")
        sys.exit(1)

    # Generate and record signals
    signals = generate_signals_batch(data)
    path = record_signals(signals)
    logger.info("Recorded %d signals to %s", len(signals), path)

    # Summary
    buys = sum(1 for s in signals if s.direction.value in ("buy", "strong_buy"))
    sells = sum(1 for s in signals if s.direction.value in ("sell", "strong_sell"))
    logger.info("Summary: %d buy, %d sell, %d hold", buys, sells, len(signals) - buys - sells)


if __name__ == "__main__":
    main()
