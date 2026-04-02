"""Tests for engine/sentiment.py — news classification and fetching."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from engine.sentiment import (
    NewsItem,
    _classify_news,
    fetch_news,
)

# ─── NewsItem ──────────────────────────────────────────


class TestNewsItem:
    def test_to_dict_basic(self) -> None:
        item = NewsItem(
            title="测试标题",
            content="短内容",
            time="10:30",
            date="2026-04-01",
            category="china",
            sectors=["科技成长"],
            direction="bullish",
            importance="high",
        )
        d = item.to_dict()
        assert d["title"] == "测试标题"
        assert d["content"] == "短内容"
        assert d["sectors"] == ["科技成长"]
        assert d["direction"] == "bullish"

    def test_to_dict_truncates_long_content(self) -> None:
        long_content = "A" * 500
        item = NewsItem(
            title="t",
            content=long_content,
            time="",
            date="",
            category="china",
            sectors=[],
            direction="neutral",
            importance="low",
        )
        assert len(item.to_dict()["content"]) == 200

    def test_frozen_dataclass(self) -> None:
        item = NewsItem(
            title="t",
            content="c",
            time="",
            date="",
            category="china",
            sectors=[],
            direction="neutral",
            importance="low",
        )
        with pytest.raises(AttributeError):
            item.title = "new"  # type: ignore[misc]


# ─── _classify_news ────────────────────────────────────


class TestClassifyNews:
    def test_tech_sector_detection(self) -> None:
        cat, sectors, direction, importance = _classify_news("芯片行业迎来突破", "半导体产业链利好")
        assert "科技成长" in sectors

    def test_multiple_sectors(self) -> None:
        _, sectors, _, _ = _classify_news("黄金和芯片同时大涨", "")
        assert "商品" in sectors
        assert "科技成长" in sectors

    def test_no_sector_match(self) -> None:
        _, sectors, _, _ = _classify_news("今天天气不错", "适合出门")
        assert sectors == []

    def test_bullish_direction(self) -> None:
        _, _, direction, _ = _classify_news("市场大涨创新高", "利好消息不断，复苏趋势明确")
        assert direction == "bullish"

    def test_bearish_direction(self) -> None:
        _, _, direction, _ = _classify_news("暴跌跳水", "恐慌抛售，制裁消息冲击市场")
        assert direction == "bearish"

    def test_neutral_direction(self) -> None:
        _, _, direction, _ = _classify_news("普通新闻", "没有明显方向的信息")
        assert direction == "neutral"

    def test_high_importance(self) -> None:
        _, _, _, importance = _classify_news("美联储宣布降息", "央行跟进")
        assert importance == "high"

    def test_medium_importance(self) -> None:
        _, _, _, importance = _classify_news("某公司财报超预期", "")
        assert importance == "medium"

    def test_low_importance(self) -> None:
        _, _, _, importance = _classify_news("普通消息", "没有重要关键词")
        assert importance == "low"

    def test_global_category(self) -> None:
        cat, _, _, _ = _classify_news("美国经济数据公布", "美联储关注通胀")
        assert cat == "global"

    def test_industry_category(self) -> None:
        cat, _, _, _ = _classify_news("某公司发布财报", "企业业绩超预期")
        assert cat == "industry"

    def test_china_category_default(self) -> None:
        cat, _, _, _ = _classify_news("今天天气很好", "")
        assert cat == "china"

    def test_all_sector_keywords_are_lists(self) -> None:
        from engine.sentiment import SECTOR_KEYWORDS

        for sector, keywords in SECTOR_KEYWORDS.items():
            assert isinstance(keywords, list), f"{sector} keywords must be list"
            assert len(keywords) > 0, f"{sector} must have keywords"

    def test_medical_sector(self) -> None:
        _, sectors, _, _ = _classify_news("创新药研发突破", "生物医药板块")
        assert "医药健康" in sectors

    def test_new_energy_sector(self) -> None:
        _, sectors, _, _ = _classify_news("光伏装机量创新高", "储能需求激增")
        assert "新能源" in sectors

    def test_finance_sector(self) -> None:
        _, sectors, _, _ = _classify_news("降准释放流动性", "银行板块受益")
        assert "金融地产" in sectors

    def test_consumer_sector(self) -> None:
        _, sectors, _, _ = _classify_news("白酒消费旺季", "")
        assert "消费" in sectors

    def test_cross_border_sector(self) -> None:
        _, sectors, _, _ = _classify_news("纳斯达克指数创新高", "")
        assert "跨境" in sectors

    def test_safe_haven_sector(self) -> None:
        _, sectors, _, _ = _classify_news("国债收益率下行", "避险情绪升温")
        assert "避险" in sectors

    def test_broad_index_sector(self) -> None:
        _, sectors, _, _ = _classify_news("沪深300成分股调整", "")
        assert "宽基指数" in sectors

    def test_commodity_sector(self) -> None:
        _, sectors, _, _ = _classify_news("原油价格飙升", "铜铝价格上涨")
        assert "商品" in sectors

    def test_cycle_manufacturing_sector(self) -> None:
        _, sectors, _, _ = _classify_news("钢铁产量创新高", "基建投资加速")
        assert "周期制造" in sectors


# ─── fetch_news ────────────────────────────────────────


def _make_mock_akshare() -> MagicMock:
    """Create a mock akshare module."""
    mock = MagicMock()
    mock.stock_info_global_cls.return_value = pd.DataFrame()
    mock.news_economic_baidu.return_value = pd.DataFrame()
    return mock


def _make_cls_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "标题": ["芯片大涨创新高", "美联储宣布降息"],
            "内容": ["半导体产业链利好", "全球市场震动"],
            "发布时间": ["10:30", "08:00"],
            "发布日期": ["2026-04-01", "2026-04-01"],
        }
    )


def _make_baidu_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "事件": ["非农就业", "CPI数据"],
            "地区": ["美国", "中国"],
            "重要性": ["高", "中"],
            "公布": ["25.6万", "2.1%"],
            "预期": ["20万", "2.0%"],
            "时间": ["20:30", "09:30"],
            "日期": ["2026-04-01", "2026-04-01"],
        }
    )


class TestFetchNews:
    def setup_method(self) -> None:
        """Reset module-level cache before each test."""
        import engine.sentiment as mod

        mod._news_cache = None

    def test_fetch_news_cls_source(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = _make_cls_df()

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 2
        assert any("芯片" in i.title for i in items)

    def test_fetch_news_baidu_source(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = _make_baidu_df()

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 2
        assert any("非农" in i.title for i in items)

    def test_fetch_news_both_sources(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = _make_cls_df()
        mock_ak.news_economic_baidu.return_value = _make_baidu_df()

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 4

    def test_fetch_news_cls_failure_graceful(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.side_effect = Exception("network error")
        mock_ak.news_economic_baidu.return_value = _make_baidu_df()

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 2

    def test_fetch_news_baidu_failure_graceful(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = _make_cls_df()
        mock_ak.news_economic_baidu.side_effect = Exception("timeout")

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 2

    def test_fetch_news_both_fail(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.side_effect = Exception("fail")
        mock_ak.news_economic_baidu.side_effect = Exception("fail")

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert items == []

    def test_fetch_news_cache_hit(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = _make_cls_df()

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            first = fetch_news()
            second = fetch_news()
        assert first == second
        assert mock_ak.stock_info_global_cls.call_count == 1

    def test_fetch_news_cache_expired(self) -> None:
        import engine.sentiment as mod

        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = _make_cls_df()

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            fetch_news()
            # Expire the cache by shifting timestamp back
            assert mod._news_cache is not None
            mod._news_cache = (mod._news_cache[0] - 600, mod._news_cache[1])
            fetch_news()
        assert mock_ak.stock_info_global_cls.call_count == 2

    def test_fetch_news_sorted_by_importance(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            {
                "标题": ["普通消息", "美联储降息"],
                "内容": ["无关紧要", "央行跟进全球影响"],
                "发布时间": ["12:00", "08:00"],
                "发布日期": ["2026-04-01", "2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert items[0].importance == "high"

    def test_fetch_news_skips_empty_title(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            {
                "标题": ["", "有效标题"],
                "内容": ["被跳过", "有效内容"],
                "发布时间": ["10:00", "11:00"],
                "发布日期": ["2026-04-01", "2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 1
        assert items[0].title == "有效标题"

    def test_fetch_news_baidu_skips_nan_event(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = pd.DataFrame(
            {
                "事件": ["nan", "GDP发布"],
                "地区": ["", "中国"],
                "重要性": ["低", "高"],
                "公布": ["", "6.5%"],
                "预期": ["", "6.3%"],
                "时间": ["", "10:00"],
                "日期": ["", "2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 1

    def test_fetch_news_baidu_importance_levels(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = pd.DataFrame(
            {
                "事件": ["EventA", "EventB", "EventC"],
                "地区": ["美国", "日本", "中国大陆"],
                "重要性": ["3星", "2星", "1星"],
                "公布": ["1", "2", "3"],
                "预期": ["1", "2", "3"],
                "时间": ["08:00", "09:00", "10:00"],
                "日期": ["2026-04-01", "2026-04-01", "2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        importances = [i.importance for i in items]
        assert "high" in importances
        assert "medium" in importances
        assert "low" in importances

    def test_fetch_news_baidu_china_category(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = pd.DataFrame(
            {
                "事件": ["PMI数据"],
                "地区": ["中国"],
                "重要性": ["高"],
                "公布": ["51.2"],
                "预期": ["50.5"],
                "时间": ["09:00"],
                "日期": ["2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert items[0].category == "china"

    def test_fetch_news_baidu_global_category(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = pd.DataFrame(
            {
                "事件": ["就业数据"],
                "地区": ["美国"],
                "重要性": ["高"],
                "公布": ["25.6万"],
                "预期": ["20万"],
                "时间": ["20:30"],
                "日期": ["2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert items[0].category == "global"

    def test_fetch_news_baidu_content_format(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = pd.DataFrame(
            {
                "事件": ["就业数据"],
                "地区": ["美国"],
                "重要性": ["高"],
                "公布": ["25.6万"],
                "预期": ["20万"],
                "时间": ["20:30"],
                "日期": ["2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert "公布: 25.6万" in items[0].content
        assert "预期: 20万" in items[0].content

    def test_fetch_news_baidu_no_pub_value(self) -> None:
        mock_ak = _make_mock_akshare()
        mock_ak.news_economic_baidu.return_value = pd.DataFrame(
            {
                "事件": ["待公布数据"],
                "地区": ["中国"],
                "重要性": ["中"],
                "公布": ["nan"],
                "预期": ["nan"],
                "时间": ["10:00"],
                "日期": ["2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert len(items) == 1
        # content should be empty when pub_val is "nan"
        assert items[0].content == ""

    def test_fetch_news_cls_classifies_correctly(self) -> None:
        """Verify CLS items get classified through _classify_news."""
        mock_ak = _make_mock_akshare()
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            {
                "标题": ["光伏装机大涨创新高"],
                "内容": ["新能源产业利好，储能需求激增"],
                "发布时间": ["10:00"],
                "发布日期": ["2026-04-01"],
            }
        )

        with patch.dict(sys.modules, {"akshare": mock_ak}):
            items = fetch_news()
        assert items[0].direction == "bullish"
        assert "新能源" in items[0].sectors
