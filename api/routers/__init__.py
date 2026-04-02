from api.routers.backtest import router as backtest_router
from api.routers.data import router as data_router
from api.routers.factors import router as factor_router
from api.routers.flow import router as flow_router
from api.routers.portfolio import router as portfolio_router
from api.routers.recommend import router as recommend_router
from api.routers.sector import router as sector_router
from api.routers.sentiment import router as sentiment_router
from api.routers.signals import router as signal_router
from api.routers.system import router as system_router
from api.routers.websocket import router as ws_router

__all__ = [
    "system_router",
    "data_router",
    "factor_router",
    "backtest_router",
    "signal_router",
    "sector_router",
    "recommend_router",
    "flow_router",
    "portfolio_router",
    "sentiment_router",
    "ws_router",
]
