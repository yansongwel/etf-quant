"""Project-wide constants — column mappings, default ETF lists, date formats."""

from __future__ import annotations

# ─── Version ──────────────────────────────────────────
PLATFORM_VERSION = "3.6"
# V4.3: dual-tier — STRONG_BUY(70%+) needs score>=16+confirm, BUY(60%) at score>=8
SIGNAL_ENGINE_VERSION = "4.3"

# ─── Column name mapping: AkShare Chinese → internal English ────────────
# Used by collectors to normalize raw DataFrames before storage.

ETF_HIST_COLUMNS: dict[str, str] = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover",
}

ETF_SPOT_COLUMNS: dict[str, str] = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌额": "change",
    "涨跌幅": "pct_change",
    "成交量": "volume",
    "成交额": "amount",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "昨收": "prev_close",
    "换手率": "turnover",
}

# ─── Default ETF watchlist for backtesting ──────────────────────────────

DEFAULT_ETF_LIST: list[dict[str, str]] = [
    # ── 宽基 ────────────────────────────────────
    {"symbol": "510300", "name": "沪深300ETF", "category": "宽基", "sector": "大盘"},
    {"symbol": "510500", "name": "中证500ETF", "category": "宽基", "sector": "中盘"},
    {"symbol": "510050", "name": "上证50ETF", "category": "宽基", "sector": "大盘"},
    {"symbol": "159915", "name": "创业板ETF", "category": "宽基", "sector": "成长"},
    {"symbol": "159901", "name": "深证100ETF", "category": "宽基", "sector": "大盘"},
    {"symbol": "588000", "name": "科创50ETF", "category": "宽基", "sector": "科技"},
    {"symbol": "560010", "name": "中证2000ETF", "category": "宽基", "sector": "小盘"},
    # ── 科技/半导体 ─────────────────────────────
    {"symbol": "512480", "name": "半导体ETF", "category": "行业", "sector": "半导体"},
    {"symbol": "515050", "name": "5GETF", "category": "行业", "sector": "通信"},
    {"symbol": "159992", "name": "创新药ETF", "category": "行业", "sector": "医药"},
    {"symbol": "516160", "name": "新能源车ETF", "category": "行业", "sector": "新能源"},
    {"symbol": "515790", "name": "光伏ETF", "category": "行业", "sector": "新能源"},
    {"symbol": "159819", "name": "人工智能ETF", "category": "行业", "sector": "AI"},
    {"symbol": "562800", "name": "芯片ETF", "category": "行业", "sector": "半导体"},
    # ── 消费 ────────────────────────────────────
    {"symbol": "159928", "name": "消费ETF", "category": "行业", "sector": "消费"},
    {"symbol": "512690", "name": "酒ETF", "category": "行业", "sector": "白酒"},
    {"symbol": "515170", "name": "食品饮料ETF", "category": "行业", "sector": "消费"},
    {"symbol": "159869", "name": "游戏ETF", "category": "行业", "sector": "传媒"},
    # ── 金融/地产 ───────────────────────────────
    {"symbol": "512880", "name": "证券ETF", "category": "行业", "sector": "券商"},
    {"symbol": "512800", "name": "银行ETF", "category": "行业", "sector": "银行"},
    {"symbol": "512200", "name": "房地产ETF", "category": "行业", "sector": "地产"},
    {"symbol": "515080", "name": "非银ETF", "category": "行业", "sector": "保险"},
    # ── 周期/制造 ───────────────────────────────
    {"symbol": "512010", "name": "医药ETF", "category": "行业", "sector": "医药"},
    {"symbol": "515030", "name": "新能源ETF", "category": "行业", "sector": "新能源"},
    {"symbol": "512660", "name": "军工ETF", "category": "行业", "sector": "军工"},
    {"symbol": "516950", "name": "基建ETF", "category": "行业", "sector": "基建"},
    {"symbol": "515220", "name": "煤炭ETF", "category": "行业", "sector": "煤炭"},
    {"symbol": "159611", "name": "电力ETF", "category": "行业", "sector": "电力"},
    {"symbol": "512400", "name": "有色金属ETF", "category": "行业", "sector": "有色"},
    {"symbol": "159870", "name": "化工ETF", "category": "行业", "sector": "化工"},
    # ── 红利/价值 ───────────────────────────────
    {"symbol": "510880", "name": "红利ETF", "category": "风格", "sector": "红利"},
    {"symbol": "515180", "name": "中证红利ETF", "category": "风格", "sector": "红利"},
    # ── 主题 ────────────────────────────────────
    {"symbol": "562500", "name": "机器人ETF", "category": "行业", "sector": "机器人"},
    {"symbol": "159828", "name": "医疗ETF", "category": "行业", "sector": "医疗"},
    # ── 跨境 ────────────────────────────────────
    {"symbol": "513100", "name": "纳指ETF", "category": "跨境", "sector": "美股"},
    {"symbol": "513500", "name": "标普ETF", "category": "跨境", "sector": "美股"},
    {"symbol": "513050", "name": "中概互联ETF", "category": "跨境", "sector": "港股"},
    {"symbol": "159866", "name": "日经ETF", "category": "跨境", "sector": "日股"},
    {"symbol": "513180", "name": "恒生科技ETF", "category": "跨境", "sector": "港股"},
    {"symbol": "159920", "name": "恒生ETF", "category": "跨境", "sector": "港股"},
    # ── 商品/债券 ───────────────────────────────
    {"symbol": "518880", "name": "黄金ETF", "category": "商品", "sector": "黄金"},
    {"symbol": "161226", "name": "白银基金", "category": "商品", "sector": "白银"},
    {"symbol": "159985", "name": "豆粕ETF", "category": "商品", "sector": "农产品"},
    {"symbol": "511010", "name": "国债ETF", "category": "债券", "sector": "债券"},
    {"symbol": "511260", "name": "十年国债ETF", "category": "债券", "sector": "债券"},
]

# ── Sector grouping for rotation analysis ─────────────────
SECTOR_GROUPS: dict[str, list[str]] = {
    "科技成长": ["512480", "562800", "159819", "515050", "588000", "562500"],
    "新能源": ["515030", "516160", "515790", "159611"],
    "消费": ["159928", "512690", "515170", "159869"],
    "医药健康": ["512010", "159992", "159828"],
    "金融地产": ["512880", "512800", "512200", "515080"],
    "红利价值": ["510880", "515180"],
    "周期制造": ["512660", "516950", "515220", "512400", "159870"],
    "宽基指数": ["510300", "510500", "510050", "159915", "560010"],
    "跨境": ["513100", "513500", "513050", "159866", "513180", "159920"],
    "商品": ["518880", "161226", "159985"],
    "避险": ["511010", "511260"],
}

# ─── Date format ────────────────────────────────────────────────────────

DATE_FORMAT = "%Y-%m-%d"
AKSHARE_DATE_FORMAT = "%Y%m%d"  # AkShare uses YYYYMMDD for API params
