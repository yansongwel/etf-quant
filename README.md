# ETF Quant — 中国 ETF 量化投研平台

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Coverage-93%25-brightgreen.svg)]()

开源的 A 股 ETF 量化投研平台，提供从数据采集、因子建模、策略回测到可视化分析的完整工作流。

**适用人群**：量化爱好者、独立投资者、金融工程学生

> **免责声明**：本项目仅供学习和研究用途，不构成任何投资建议。量化策略存在风险，过往回测表现不代表未来收益。

---

## 特性

- **数据采集** — 基于 [AkShare](https://github.com/akfamily/akshare) 自动采集 ETF 行情，支持增量更新和断点续传
- **因子模型** — 18 个因子覆盖动量、价值、波动率三大维度
- **回测引擎** — 严格 T+1 约束、佣金万2、滑点 1tick、组合管理
- **策略库** — 动量轮动、股债平衡、网格交易、多因子打分 4 种策略
- **实时信号** — 基于多因子分析生成 ETF 买卖信号，含入场价、目标价、止损价
- **机构大单检测** — 通过量价异常检测机构吸筹/出货/放量突破/恐慌抛售
- **风控布局建议** — 多维风险评估 + 提前布局策略 + 止损规则 + 资金管理
- **板块轮动** — 9 大板块轮动时钟，识别复苏/领涨/走弱/底部阶段
- **智能推荐** — 输入资金自动评估最优策略+ETF 组合，给出具体买入方案
- **Dashboard** — 9 个页面：概览、实时信号、大单检测、风控布局、板块轮动、智能推荐、数据、因子、回测

## 架构总览

```
┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌────────────┐
│  数据采集层    │ →  │   存储层       │ →  │  因子/回测引擎 │ →  │  展示层     │
│  AkShare     │    │  Parquet      │    │  VectorBT    │    │  Next.js   │
│  Tushare     │    │  TimescaleDB  │    │  Backtrader  │    │  Dashboard │
└──────────────┘    └───────────────┘    └──────────────┘    └────────────┘
```

```
etf-quant/
├── data/                  # 数据层
│   ├── collectors/        #   采集模块（AkShare 封装、限速、重试）
│   ├── storage/           #   存储模块（Parquet 读写、增量去重）
│   └── cache/             #   缓存模块（Redis 缓存层）
├── factors/               # 因子计算
│   ├── momentum.py        #   动量因子（收益率、RSI、MA比率）
│   ├── value.py           #   价值因子（MA偏离、价格分位、VWAP）
│   └── volatility.py      #   波动率因子（历史波动、ATR、最大回撤）
├── engine/                # 回测引擎 + 信号 + 风控
│   ├── backtest.py        #   核心引擎（T+1 执行、佣金滑点）
│   ├── metrics.py         #   绩效指标（收益、夏普、回撤、胜率）
│   ├── signals.py         #   实时买卖信号生成
│   ├── flow.py            #   机构大单检测（量价异常分析）
│   ├── risk_advisor.py    #   风险评估 + 布局建议
│   ├── sector.py          #   板块轮动分析
│   ├── recommender.py     #   策略智能推荐
│   └── types.py           #   数据类型（Signal、Trade、Position）
├── strategies/            # 策略实现
│   ├── base.py            #   策略基类
│   └── rotation.py        #   动量轮动策略
├── api/                   # FastAPI 后端
│   ├── main.py            #   应用入口
│   └── routers/           #   路由（data、factors、backtest、signals、sector、flow、recommend）
├── web/                   # Next.js 前端 Dashboard（9 页面已上线）
├── scripts/               # 运维脚本（数据采集、初始化）
├── config/                # 配置文件（不含密钥）
└── tests/                 # 测试（unit / integration / e2e）
```

## 快速开始

### 环境要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 运行环境 |
| [uv](https://docs.astral.sh/uv/) | latest | Python 包管理器（替代 pip） |
| Node.js | 20+ | 前端 Dashboard（可选） |
| [pm2](https://pm2.keymetrics.io/) | latest | 进程管理（可选，生产部署） |
| PostgreSQL + TimescaleDB | 16+ | 时序数据库（可选，开发阶段用 Parquet） |
| Redis | 7+ | 缓存 + 任务队列（可选） |

### 安装

```bash
# 克隆项目
git clone https://github.com/your-username/etf-quant.git
cd etf-quant

# 一键安装（推荐）
bash scripts/setup.sh

# 或手动安装
uv sync --dev                        # 安装所有 Python 依赖
cp config/.env.example .env          # 创建配置文件，按需修改
```

### 采集数据

```bash
# 采集默认 ETF 列表（13 只），最近 5 年数据
PYTHONPATH=. uv run python scripts/collect_daily.py

# 指定 ETF 和时间范围
PYTHONPATH=. uv run python scripts/collect_daily.py \
  --symbols 510300 510500 159915 \
  --days 365

# 仅采集历史行情，跳过实时快照
PYTHONPATH=. uv run python scripts/collect_daily.py --skip-spot
```

数据存储在 `data_store/etf_hist/` 目录，每只 ETF 一个 Parquet 文件。

### 开发模式

```bash
bash scripts/dev.sh                  # 启动 API（热重载，端口 8000）
```

### 生产部署（pm2）

```bash
pm2 start ecosystem.config.cjs      # 启动全部服务
pm2 status                           # 查看进程状态
pm2 logs                             # 查看日志
pm2 save && pm2 startup              # 开机自启
```

| 服务名 | 端口 | 说明 |
|--------|------|------|
| `etf-api` | 8000 | FastAPI 后端 |
| `etf-worker` | — | Celery 异步任务 |
| `etf-scheduler` | — | 定时数据采集 |
| `etf-web` | 3001 | Next.js 前端 |

## 默认 ETF 列表

| 代码 | 名称 | 类型 |
|------|------|------|
| 510300 | 沪深300ETF | 宽基 |
| 510500 | 中证500ETF | 宽基 |
| 510050 | 上证50ETF | 宽基 |
| 159915 | 创业板ETF | 宽基 |
| 512010 | 医药ETF | 行业 |
| 512880 | 证券ETF | 行业 |
| 515030 | 新能源ETF | 行业 |
| 512690 | 酒ETF | 行业 |
| 512660 | 军工ETF | 行业 |
| 159869 | 游戏ETF | 行业 |
| 513100 | 纳指ETF | 跨境 |
| 518880 | 黄金ETF | 商品 |
| 159985 | 豆粕ETF | 商品 |
| 511010 | 国债ETF | 债券 |

## 策略库

| 策略 | 说明 | 状态 |
|------|------|------|
| 行业轮动 | 按动量排名在行业 ETF 间定期切换 | **已实现** |
| 股债平衡 | 股票/债券 ETF 按目标比例漂移触发再平衡 | **已实现** |
| 网格交易 | 在价格网格内高抛低吸 | **已实现** |
| 多因子打分 | 综合动量+价值+波动率因子排序选 ETF | **已实现** |

## 因子库

| 类别 | 因子 |
|------|------|
| 动量 | 5/10/20/60 日收益率、相对强弱（RSI） |
| 价值 | PE、PB、股息率（对应指数） |
| 波动率 | 历史波动率、ATR、最大回撤 |
| 资金流 | 北向资金、ETF 份额变化、成交额比 |
| 宏观 | PMI、社融、M2 增速、利率 |

## 回测参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 佣金 | 万2（0.02%） | 单笔交易手续费 |
| 滑点 | 0.001 | 1 tick |
| T+1 | 启用 | T 日信号，T+1 日开盘执行 |
| 基准 | 沪深300（510300） | 策略对比基准 |
| 验证方式 | Walk-forward | 3 年训练 / 1 年测试滚动窗口 |

## API 接口

启动 API 后，可访问 `http://localhost:8000/docs` 查看 Swagger 文档。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查（含 Redis 状态） |
| `/etf/list` | GET | 获取默认 ETF 列表 |
| `/api/data/hist/{symbol}` | GET | 查询历史行情（支持日期过滤） |
| `/api/data/symbols` | GET | 列出已有数据的 ETF 代码 |
| `/api/data/quality/{symbol}` | GET | 单只 ETF 数据质量报告 |
| `/api/data/quality` | GET | 全部 ETF 数据质量报告 |
| `/api/factors/{symbol}` | GET | 计算因子值（momentum/value/volatility） |
| `/api/factors/compare` | POST | 多 ETF 因子横向对比 |
| `/api/signals/current` | GET | **实时买卖信号**（全部 ETF） |
| `/api/signals/detail/{symbol}` | GET | 单只 ETF 详细信号 |
| `/api/signals/positions` | POST | **持仓建议**（输入资金，返回具体买入方案） |
| `/api/signals/recommend` | POST | **策略推荐**（自动评估最优策略+参数） |
| `/api/backtest/strategies` | GET | 列出所有可用策略 |
| `/api/backtest/rotation` | POST | 动量轮动回测 |
| `/api/backtest/balance` | POST | 股债平衡回测 |
| `/api/backtest/grid` | POST | 网格交易回测 |
| `/api/backtest/multifactor` | POST | 多因子打分回测 |
| `/api/sector/rotation` | GET | 板块轮动分析（9 大板块） |
| `/api/sector/plan` | POST | 板块配置方案（输入资金） |
| `/api/flow/scan` | GET | **机构大单扫描**（全市场异常检测） |
| `/api/flow/detail/{symbol}` | GET | 单只 ETF 资金流详情 |
| `/api/risk/report` | POST | **综合风险报告**（风险评估+布局建议+规则） |
| `/api/risk/etf/{symbol}` | GET | 单只 ETF 风险评估 |
| `/api/risk/layout` | POST | **提前布局建议**（板块轮动×资金流×风险） |
| `/api/recommend/proven` | POST | 验证盈利的策略推荐 |

### 回测请求示例

```bash
curl -X POST http://localhost:8000/api/backtest/rotation \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["510300", "510500", "510050", "159915", "512010"],
    "lookback": 20,
    "top_k": 3,
    "rebalance_days": 20,
    "initial_cash": 1000000
  }'
```

## 测试

```bash
# 运行全部测试
PYTHONPATH=. uv run python -m pytest

# 单元测试
PYTHONPATH=. uv run python -m pytest tests/unit/ -v

# 带覆盖率
PYTHONPATH=. uv run python -m pytest --cov

# 集成测试（调用真实 API，较慢）
PYTHONPATH=. uv run python -m pytest tests/integration/ -m slow

# 代码检查
uv run ruff check . && uv run ruff format .
```

覆盖率目标：**80%+**（当前：80%，204 个测试用例）

## 技术选型说明

| 决策 | 选择 | 原因 |
|------|------|------|
| 数据源 | AkShare | 免费开源、维护活跃、覆盖沪深交易所全部 ETF |
| 因子研究引擎 | VectorBT | 向量化计算，参数扫描比事件驱动引擎快 100 倍 |
| 策略验证引擎 | Backtrader | 事件驱动，能真实模拟 T+1、滑点等执行细节 |
| 本地存储 | Parquet | 列式存储，读取速度比 CSV 快 10 倍，体积小 90% |
| 包管理 | uv | Rust 实现，比 pip 快 10-100 倍，自带 venv 管理 |
| 进程管理 | pm2 | 自动重启、日志管理、开机自启、监控面板 |

## 开发路线图

- [x] Phase 1：数据采集 — AkShare ETF 行情 + 基金净值 + Parquet 存储
- [x] Phase 2：因子计算 — 动量、价值、波动率三类因子
- [x] Phase 3：回测引擎 — 自研引擎 + 严格 T+1 + 佣金滑点
- [x] Phase 4：策略实现 — 行业轮动 MVP（动量排名轮换）
- [x] Phase 5：API — FastAPI 后端（数据查询、因子计算、4 种策略回测）
- [x] Phase 6：Dashboard — Next.js 前端（概览、数据、因子、回测 4 页面）
- [x] Phase 7：高级策略 — 多因子打分、股债平衡、网格交易
- [x] Phase 8：信号系统 — 实时信号、板块轮动、智能推荐、信号准确率追踪
- [x] Phase 9：风控系统 — 机构大单检测、多维风险评估、提前布局建议
- [ ] Phase 10：高级功能 — Walk-forward 验证、参数优化、实盘对接

## 参与贡献

欢迎贡献代码！请遵循以下流程：

1. Fork 本项目
2. 创建功能分支：`git checkout -b feat/your-feature`
3. 编写代码和测试（覆盖率 >= 80%）
4. 提交：`git commit -m "feat: 你的功能描述"`
5. 推送：`git push origin feat/your-feature`
6. 发起 Pull Request

### 开发规范

- 代码格式化：`uv run ruff format .`
- 代码检查：`uv run ruff check .`
- 类型标注：所有公开函数必须有类型标注
- 提交格式：`<type>: <description>`（type: feat/fix/refactor/docs/test/chore）

## 致谢

- [AkShare](https://github.com/akfamily/akshare) — 优秀的中国金融数据接口
- [VectorBT](https://github.com/polakowo/vectorbt) — 高性能向量化回测框架
- [Backtrader](https://github.com/mementum/backtrader) — 经典的事件驱动回测引擎

## 许可证

[MIT License](LICENSE) — 自由使用，风险自担。
