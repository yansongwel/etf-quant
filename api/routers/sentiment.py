"""Sentiment / news feed API endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from engine.sentiment import fetch_news

router = APIRouter()

_CST = timezone(timedelta(hours=8))


@router.get("/feed")
def get_news_feed(
    category: str = Query("", description="Filter: global / china / industry. Empty = all."),
    importance: str = Query("", description="Filter: high / medium / low. Empty = all."),
) -> dict:
    """Get latest classified financial news feed."""
    items = fetch_news()

    if category:
        items = [i for i in items if i.category == category]
    if importance:
        items = [i for i in items if i.importance == importance]

    # Compute summary
    bullish = sum(1 for i in items if i.direction == "bullish")
    bearish = sum(1 for i in items if i.direction == "bearish")
    high_imp = sum(1 for i in items if i.importance == "high")

    mood = "偏多" if bullish > bearish * 1.5 else "偏空" if bearish > bullish * 1.5 else "中性"

    return {
        "count": len(items),
        "news": [i.to_dict() for i in items],
        "summary": {
            "bullish": bullish,
            "bearish": bearish,
            "neutral": len(items) - bullish - bearish,
            "high_importance": high_imp,
            "mood": mood,
        },
        "generated_at": datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S"),
    }
