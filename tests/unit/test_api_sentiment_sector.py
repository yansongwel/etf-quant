"""Tests for sentiment and sector API endpoints."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.deps import require_api_key
from api.main import app
from engine.sentiment import NewsItem

app.dependency_overrides[require_api_key] = lambda: "test-key"
client = TestClient(app)


# ─── helpers ──────────────────────────────────────────


def _make_news_items() -> list[NewsItem]:
    return [
        NewsItem(
            title="芯片大涨",
            content="半导体利好",
            time="10:30",
            date="2026-04-01",
            category="china",
            sectors=["科技成长"],
            direction="bullish",
            importance="high",
        ),
        NewsItem(
            title="美股暴跌",
            content="恐慌抛售",
            time="08:00",
            date="2026-04-01",
            category="global",
            sectors=["跨境"],
            direction="bearish",
            importance="high",
        ),
        NewsItem(
            title="普通新闻",
            content="没什么大事",
            time="12:00",
            date="2026-04-01",
            category="china",
            sectors=[],
            direction="neutral",
            importance="low",
        ),
    ]


# ─── Sentiment Feed ──────────────────────────────────


class TestSentimentFeed:
    @patch("api.routers.sentiment.fetch_news")
    def test_get_all_news(self, mock_fetch):
        mock_fetch.return_value = _make_news_items()
        resp = client.get("/api/sentiment/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert len(data["news"]) == 3
        assert "summary" in data
        assert "generated_at" in data

    @patch("api.routers.sentiment.fetch_news")
    def test_filter_by_category(self, mock_fetch):
        mock_fetch.return_value = _make_news_items()
        resp = client.get("/api/sentiment/feed?category=global")
        data = resp.json()
        assert data["count"] == 1
        assert data["news"][0]["title"] == "美股暴跌"

    @patch("api.routers.sentiment.fetch_news")
    def test_filter_by_importance(self, mock_fetch):
        mock_fetch.return_value = _make_news_items()
        resp = client.get("/api/sentiment/feed?importance=low")
        data = resp.json()
        assert data["count"] == 1
        assert data["news"][0]["title"] == "普通新闻"

    @patch("api.routers.sentiment.fetch_news")
    def test_summary_mood_bullish(self, mock_fetch):
        # 2 bullish, 0 bearish → 偏多
        mock_fetch.return_value = [
            NewsItem("a", "c", "", "", "china", [], "bullish", "low"),
            NewsItem("b", "c", "", "", "china", [], "bullish", "low"),
        ]
        resp = client.get("/api/sentiment/feed")
        data = resp.json()
        assert data["summary"]["mood"] == "偏多"

    @patch("api.routers.sentiment.fetch_news")
    def test_summary_mood_bearish(self, mock_fetch):
        mock_fetch.return_value = [
            NewsItem("a", "c", "", "", "china", [], "bearish", "low"),
            NewsItem("b", "c", "", "", "china", [], "bearish", "low"),
        ]
        resp = client.get("/api/sentiment/feed")
        data = resp.json()
        assert data["summary"]["mood"] == "偏空"

    @patch("api.routers.sentiment.fetch_news")
    def test_summary_mood_neutral(self, mock_fetch):
        mock_fetch.return_value = [
            NewsItem("a", "c", "", "", "china", [], "bullish", "low"),
            NewsItem("b", "c", "", "", "china", [], "bearish", "low"),
        ]
        resp = client.get("/api/sentiment/feed")
        data = resp.json()
        assert data["summary"]["mood"] == "中性"

    @patch("api.routers.sentiment.fetch_news")
    def test_summary_counts(self, mock_fetch):
        mock_fetch.return_value = _make_news_items()
        resp = client.get("/api/sentiment/feed")
        summary = resp.json()["summary"]
        assert summary["bullish"] == 1
        assert summary["bearish"] == 1
        assert summary["neutral"] == 1
        assert summary["high_importance"] == 2

    @patch("api.routers.sentiment.fetch_news")
    def test_empty_feed(self, mock_fetch):
        mock_fetch.return_value = []
        resp = client.get("/api/sentiment/feed")
        data = resp.json()
        assert data["count"] == 0
        assert data["summary"]["mood"] == "中性"


# ─── Sector Groups ───────────────────────────────────


class TestSectorGroups:
    @patch("api.routers.sector.analyze_all_sectors")
    def test_get_sector_groups(self, mock_analyze):
        from unittest.mock import MagicMock

        sector = MagicMock()
        sector.to_dict.return_value = {
            "sector_name": "科技成长",
            "phase": "recovery",
            "phase_label": "复苏期",
            "etf_symbols": ["512480", "159611"],
            "best_etf": "512480",
        }
        mock_analyze.return_value = [sector]

        resp = client.get("/api/sector/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        group = data["groups"][0]
        assert group["sector"] == "科技成长"
        assert group["phase"] == "recovery"
        assert len(group["etfs"]) == 2

    @patch("api.routers.sector.analyze_all_sectors")
    def test_get_sector_groups_empty(self, mock_analyze):
        mock_analyze.return_value = []

        resp = client.get("/api/sector/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["groups"] == []
