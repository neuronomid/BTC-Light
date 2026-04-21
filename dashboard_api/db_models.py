from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, JSON, Index, Text
from datetime import datetime
from shared.db import Base

class PaperWalletTransaction(Base):
    __tablename__ = "paper_wallet_transactions"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_type = Column(String(20), nullable=False)  # DEPOSIT, WITHDRAW, TRADE_PNL, RESET
    amount = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    level = Column(String(20), nullable=False)  # INFO, WARNING, ERROR, CRITICAL
    source = Column(String(50), nullable=False)  # ORCHESTRATOR, AGENT, EXECUTION, SAFETY, DASHBOARD
    message = Column(Text, nullable=False)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_system_logs_created_at", "created_at"),
        Index("ix_system_logs_level", "level"),
        Index("ix_system_logs_source", "source"),
    )

class AgentOutputLog(Base):
    __tablename__ = "agent_output_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), nullable=False)  # market_context, news_sentiment, trade_decision, risk_monitor
    cycle_timestamp = Column(DateTime, nullable=False)
    output_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_agent_output_logs_agent_name", "agent_name"),
        Index("ix_agent_output_logs_cycle_timestamp", "cycle_timestamp"),
    )

class PriceTick(Base):
    __tablename__ = "price_ticks"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    __table_args__ = (
        Index("ix_price_ticks_symbol_timestamp", "symbol", "timestamp"),
    )
