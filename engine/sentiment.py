"""Market sentiment aggregator — collects news and tags with ETF impact.

Sources:
1. 财联社全球快讯 (CLS) — real-time financial news
2. 百度财经日历 — economic data releases

Each news item is tagged with:
- category: global / china / industry
- impact_sectors: list of affected ETF sectors
- direction: bullish / bearish / neutral
- importance: high / medium / low
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Keyword → sector/direction mapping ──────────────────

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "科技成长": [
        "芯片",
        "半导体",
        "AI",
        "人工智能",
        "算力",
        "大模型",
        "5G",
        "通信",
        "机器人",
        "华为",
        "英伟达",
        "NVIDIA",
    ],
    "医药健康": ["医药", "医疗", "创新药", "集采", "生物", "疫苗", "CXO"],
    "新能源": ["新能源", "光伏", "锂电", "储能", "风电", "碳中和", "电动车", "特斯拉"],
    "金融地产": ["银行", "地产", "房地产", "LPR", "降息", "降准", "MLF", "利率", "券商", "保险"],
    "消费": ["消费", "白酒", "食品", "零售", "旅游", "免税", "家电"],
    "周期制造": ["钢铁", "煤炭", "有色", "化工", "建材", "基建", "制造"],
    "商品": ["黄金", "白银", "原油", "石油", "豆粕", "大宗商品", "铜", "铝"],
    "跨境": ["美股", "纳斯达克", "标普", "恒生", "港股", "中概股", "日经"],
    "避险": ["国债", "债券", "避险", "VIX"],
    "宽基指数": ["沪深300", "上证50", "中证500", "创业板", "科创板", "A股"],
}

BEARISH_KEYWORDS = [
    "下跌",
    "暴跌",
    "大跌",
    "跳水",
    "制裁",
    "关税",
    "贸易战",
    "战争",
    "冲突",
    "加息",
    "紧缩",
    "衰退",
    "裁员",
    "亏损",
    "违约",
    "暴雷",
    "退市",
    "罚款",
    "减持",
    "抛售",
    "恐慌",
    "熔断",
    "黑天鹅",
    "风险",
    "监管",
    "整顿",
    "收紧",
]

BULLISH_KEYWORDS = [
    "上涨",
    "大涨",
    "暴涨",
    "新高",
    "突破",
    "利好",
    "刺激",
    "降息",
    "降准",
    "回购",
    "增持",
    "买入",
    "抄底",
    "复苏",
    "反弹",
    "放量",
    "突围",
    "补贴",
    "减税",
    "宽松",
    "改革",
    "开放",
    "合作",
    "订单",
    "盈利",
    "超预期",
]

IMPORTANCE_KEYWORDS = {
    "high": [
        "央行",
        "美联储",
        "国务院",
        "战争",
        "制裁",
        "熔断",
        "降息",
        "加息",
        "关税",
        "PMI",
        "GDP",
        "CPI",
    ],
    "medium": ["财报", "减持", "增持", "IPO", "回购", "政策", "监管", "数据"],
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    content: str
    time: str
    date: str
    category: str  # global / china / industry
    sectors: list[str]
    direction: str  # bullish / bearish / neutral
    importance: str  # high / medium / low

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content[:200],
            "time": self.time,
            "date": self.date,
            "category": self.category,
            "sectors": self.sectors,
            "direction": self.direction,
            "importance": self.importance,
        }


def _classify_news(title: str, content: str) -> tuple[str, list[str], str, str]:
    """Classify a news item by category, sectors, direction, importance."""
    text = title + " " + content

    # Detect sectors
    sectors = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            sectors.append(sector)

    # Detect direction
    bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    if bear_count > bull_count:
        direction = "bearish"
    elif bull_count > bear_count:
        direction = "bullish"
    else:
        direction = "neutral"

    # Detect importance
    importance = "low"
    for level in ("high", "medium"):
        if any(kw in text for kw in IMPORTANCE_KEYWORDS[level]):
            importance = level
            break

    # Detect category
    global_keywords = [
        "美国",
        "欧洲",
        "日本",
        "美联储",
        "美股",
        "纳指",
        "标普",
        "黄金",
        "原油",
        "战争",
        "伊朗",
        "俄罗斯",
    ]
    industry_keywords = ["公司", "企业", "个股", "财报", "业绩", "订单"]
    if any(kw in text for kw in global_keywords):
        category = "global"
    elif any(kw in text for kw in industry_keywords):
        category = "industry"
    else:
        category = "china"

    return category, sectors, direction, importance


# ─── News fetching ─────────────────────────────────────

_news_cache: tuple[float, list[NewsItem]] | None = None
_NEWS_CACHE_TTL = 300  # 5 minutes


def fetch_news() -> list[NewsItem]:
    """Fetch and classify latest financial news."""
    global _news_cache
    now = time.monotonic()
    if _news_cache is not None and now - _news_cache[0] < _NEWS_CACHE_TTL:
        return _news_cache[1]

    items: list[NewsItem] = []

    # Source 1: 财联社全球快讯
    try:
        import akshare as ak

        df = ak.stock_info_global_cls()
        if not df.empty:
            for _, row in df.iterrows():
                title = str(row.get("标题", ""))
                content = str(row.get("内容", ""))
                pub_time = str(row.get("发布时间", ""))
                pub_date = str(row.get("发布日期", ""))

                if not title:
                    continue

                category, sectors, direction, importance = _classify_news(title, content)
                items.append(
                    NewsItem(
                        title=title,
                        content=content,
                        time=pub_time,
                        date=pub_date,
                        category=category,
                        sectors=sectors,
                        direction=direction,
                        importance=importance,
                    )
                )
    except Exception as e:
        logger.warning("Failed to fetch CLS news: %s", e)

    # Source 2: 百度财经日历 (economic events)
    try:
        import akshare as ak

        df2 = ak.news_economic_baidu()
        if not df2.empty:
            for _, row in df2.head(20).iterrows():
                event = str(row.get("事件", ""))
                region = str(row.get("地区", ""))
                importance_raw = str(row.get("重要性", ""))
                pub_val = str(row.get("公布", ""))
                expect_val = str(row.get("预期", ""))

                if not event or event == "nan":
                    continue

                title = f"[{region}] {event}"
                content = ""
                if pub_val and pub_val != "nan":
                    content = f"公布: {pub_val}"
                    if expect_val and expect_val != "nan":
                        content += f" (预期: {expect_val})"

                imp = (
                    "high"
                    if "高" in importance_raw or "3" in importance_raw
                    else "medium"
                    if "中" in importance_raw or "2" in importance_raw
                    else "low"
                )
                cat = "global" if region not in ("中国", "中国大陆", "") else "china"

                items.append(
                    NewsItem(
                        title=title,
                        content=content,
                        time=str(row.get("时间", "")),
                        date=str(row.get("日期", "")),
                        category=cat,
                        sectors=[],
                        direction="neutral",
                        importance=imp,
                    )
                )
    except Exception as e:
        logger.warning("Failed to fetch Baidu economic calendar: %s", e)

    # Sort by importance (high first) then time (newest first)
    importance_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (importance_order.get(x.importance, 3), x.time), reverse=False)
    items.sort(key=lambda x: importance_order.get(x.importance, 3))

    _news_cache = (now, items)
    return items
