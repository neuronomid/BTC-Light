import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, JSON, Index
from config.settings import DATABASE_URL
from loguru import logger
from shared.time_utils import utc_now_naive

Base = declarative_base()

ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        Index("ix_candles_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp"),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trade_id = Column(String(64), unique=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    action = Column(String(10), nullable=False)
    entry_price = Column(Float)
    exit_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    size = Column(Float)
    pnl = Column(Float)
    pnl_pct = Column(Float)
    conviction = Column(Integer)
    reasoning = Column(String)
    agent_outputs = Column(JSON)
    statistical_outputs = Column(JSON)
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)
    status = Column(String(20), default="OPEN")
    created_at = Column(DateTime, default=utc_now_naive)

class StatisticalSnapshot(Base):
    __tablename__ = "statistical_snapshots"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    regime_data = Column(JSON)
    trend_data = Column(JSON)
    volatility_data = Column(JSON)
    change_point_data = Column(JSON)
    tail_risk_data = Column(JSON)
    probability_data = Column(JSON)
    efficiency_data = Column(JSON)
    correlation_data = Column(JSON)
    created_at = Column(DateTime, default=utc_now_naive)

async def init_db():
    try:
        from dashboard_api import db_models  # noqa: F401
    except ImportError:
        pass
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
