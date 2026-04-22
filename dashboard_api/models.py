from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime

class SystemStartRequest(BaseModel):
    fetch_external: bool = False

class SystemStatus(BaseModel):
    running: bool
    paused: bool
    equity: float
    starting_equity: float
    open_positions: int
    closed_trades: int
    daily_pnl: float
    weekly_pnl: float
    current_price: Optional[float]
    last_cycle: Optional[str]
    mode: str = "PAPER"
    fetch_external: bool = False

class PositionResponse(BaseModel):
    trade_id: str
    symbol: str
    action: str
    entry_price: float
    size: float
    stop_loss: float
    take_profit: float
    opened_at: str
    closed_at: Optional[str]
    conviction: int
    reasoning: str
    pnl: float
    pnl_pct: float
    status: str
    exit_reason: Optional[str]

class TradeHistoryResponse(BaseModel):
    trades: List[PositionResponse]
    total_count: int
    total_pnl: float
    win_count: int
    loss_count: int
    win_rate: float

class PaperWalletTransactionRequest(BaseModel):
    amount: float
    description: Optional[str] = ""

class PaperWalletTransactionResponse(BaseModel):
    id: int
    transaction_type: str
    amount: float
    balance_after: float
    description: Optional[str]
    created_at: str

class PaperWalletBalance(BaseModel):
    balance: float
    total_deposited: float
    total_withdrawn: float
    total_pnl: float

class AgentOutputResponse(BaseModel):
    agent_name: str
    cycle_timestamp: str
    output_data: Dict[str, Any]

class SystemLogResponse(BaseModel):
    id: int
    level: str
    source: str
    message: str
    metadata: Optional[Dict]
    created_at: str

class ChartDataPoint(BaseModel):
    timestamp: str
    price: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    timeframe: str
    trade_marker: Optional[Dict[str, Any]]

class StatisticalSnapshotResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str
    latest_close: Optional[float]
    regime: Dict[str, Any]
    trend: Dict[str, Any]
    volatility: Dict[str, Any]
    change_point: Dict[str, Any]
    tail_risk: Dict[str, Any]
    efficiency: Dict[str, Any]
    correlation: Dict[str, Any]
    probability: Optional[Dict[str, Any]] = None
