import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import redis as redis_lib
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.db import AsyncSessionLocal, Candle, engine, init_db
from shared.redis_client import redis_client
from shared.time_utils import utc_now, utc_now_naive
from config.settings import TIMEFRAME, REDIS_HOST, REDIS_PORT, REDIS_DB
from dashboard_api.db_models import PaperWalletTransaction, SystemLog, AgentOutputLog, PriceTick
from dashboard_api.models import (
    SystemStatus, PositionResponse, TradeHistoryResponse,
    PaperWalletTransactionRequest, PaperWalletTransactionResponse,
    PaperWalletBalance, AgentOutputResponse, SystemLogResponse,
    ChartDataPoint, StatisticalSnapshotResponse, SystemStartRequest
)

# Global state
DEFAULT_PAPER_BALANCE = 10000.0

_orchestrator_ref = None
_orchestrator_task: Optional[asyncio.Task] = None
_system_paused = False
_system_running = False

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# Redis pub/sub bridge
REDIS_CHANNELS = ("position:opened", "position:closed", "trade_decision", "statistical:snapshot", "candles:new")
_redis_queue: asyncio.Queue = asyncio.Queue()

def _redis_listen_sync(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    while True:
        try:
            client = redis_lib.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
            )
            client.ping()
            pubsub = client.pubsub()
            pubsub.subscribe(*REDIS_CHANNELS)
            logger.info(f"Dashboard Redis listener subscribed to {', '.join(REDIS_CHANNELS)}")
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    data = json.loads(message.get("data", "{}"))
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {
                            "type": message["channel"],
                            "data": data,
                            "timestamp": utc_now().isoformat()
                        }
                    )
                except Exception as e:
                    logger.warning(f"Dashboard Redis listener dropped malformed message: {e}")
        except Exception as e:
            logger.error(f"Dashboard Redis listener error: {e}")
            time.sleep(2)

async def redis_listener():
    loop = asyncio.get_event_loop()
    import threading
    t = threading.Thread(target=_redis_listen_sync, args=(_redis_queue, loop), daemon=True)
    t.start()
    while True:
        msg = await _redis_queue.get()
        await manager.broadcast(msg)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    redis_client.connect()
    # Create paper wallet table if not exists
    async with engine.begin() as conn:
        from dashboard_api.db_models import Base as DashboardBase
        await conn.run_sync(DashboardBase.metadata.create_all)
    # Start Redis listener
    listener_task = asyncio.create_task(redis_listener())
    yield
    listener_task.cancel()

app = FastAPI(title="BTC Trading Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper functions ---

def _get_orchestrator(
    starting_equity: float = DEFAULT_PAPER_BALANCE,
    current_equity: Optional[float] = None,
    fetch_external: bool = False,
):
    global _orchestrator_ref
    task_running = _orchestrator_task is not None and not _orchestrator_task.done()
    needs_new = (
        _orchestrator_ref is None
        or (not task_running and bool(getattr(_orchestrator_ref, "fetch_external", False)) != fetch_external)
    )
    if needs_new:
        try:
            from orchestrator import TradingOrchestrator
            _orchestrator_ref = TradingOrchestrator(
                fetch_external=fetch_external,
                initial_equity=starting_equity,
                paper_mode=True,
            )
            _orchestrator_ref.execution.on_position_closed = _record_trade_pnl
        except Exception:
            pass
    if _orchestrator_ref and current_equity is not None and not task_running:
        _orchestrator_ref.execution.equity = current_equity
    return _orchestrator_ref

def _apply_orchestrator_cash_flow(amount: float):
    if not _orchestrator_ref:
        return
    execution = _orchestrator_ref.execution
    execution.equity = round(execution.equity + amount, 2)
    execution.starting_equity = round(execution.starting_equity + amount, 2)

def _reset_orchestrator_account(balance: float = DEFAULT_PAPER_BALANCE):
    if not _orchestrator_ref:
        return
    execution = _orchestrator_ref.execution
    execution.equity = balance
    execution.starting_equity = balance
    execution.daily_pnl = 0.0
    execution.weekly_pnl = 0.0
    execution.positions.clear()
    execution.closed_trades.clear()
    execution.last_trade_time = None
    execution.safety.open_positions = 0
    execution.safety.daily_pnl = 0.0
    execution.safety.weekly_pnl = 0.0

async def _stop_orchestrator_task():
    global _orchestrator_task
    if _orchestrator_ref:
        _orchestrator_ref.stop()
    task = _orchestrator_task
    if task and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    _orchestrator_task = None

async def _add_wallet_transaction(transaction_type: str, amount: float, description: str) -> float:
    current_balance = await _get_paper_balance()
    new_balance = current_balance + amount
    async with AsyncSessionLocal() as session:
        tx = PaperWalletTransaction(
            transaction_type=transaction_type,
            amount=amount,
            balance_after=new_balance,
            description=description
        )
        session.add(tx)
        await session.commit()
    return new_balance

async def _record_trade_pnl(position, reason: str):
    new_balance = await _add_wallet_transaction(
        "TRADE_PNL",
        position.pnl,
        f"{position.trade_id} closed: {reason}"
    )
    await manager.broadcast({
        "type": "wallet:pnl",
        "data": {
            "trade_id": position.trade_id,
            "amount": position.pnl,
            "balance": new_balance,
        }
    })

async def _get_paper_balance() -> float:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PaperWalletTransaction).order_by(desc(PaperWalletTransaction.id)).limit(1)
        )
        tx = result.scalar_one_or_none()
        if tx:
            return tx.balance_after
    return DEFAULT_PAPER_BALANCE

async def _get_latest_reset_id(session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(func.max(PaperWalletTransaction.id)).where(
            PaperWalletTransaction.transaction_type == "RESET"
        )
    )
    return result.scalar_one_or_none()

async def _get_total_deposited() -> float:
    async with AsyncSessionLocal() as session:
        latest_reset_id = await _get_latest_reset_id(session)
        query = select(func.sum(PaperWalletTransaction.amount)).where(
            PaperWalletTransaction.transaction_type == "DEPOSIT"
        )
        if latest_reset_id is not None:
            query = query.where(PaperWalletTransaction.id > latest_reset_id)
        result = await session.execute(
            query
        )
        return result.scalar() or 0.0

async def _get_total_withdrawn() -> float:
    async with AsyncSessionLocal() as session:
        latest_reset_id = await _get_latest_reset_id(session)
        query = select(func.sum(PaperWalletTransaction.amount)).where(
            PaperWalletTransaction.transaction_type == "WITHDRAW"
        )
        if latest_reset_id is not None:
            query = query.where(PaperWalletTransaction.id > latest_reset_id)
        result = await session.execute(
            query
        )
        return result.scalar() or 0.0

async def _get_total_pnl() -> float:
    async with AsyncSessionLocal() as session:
        latest_reset_id = await _get_latest_reset_id(session)
        query = select(func.sum(PaperWalletTransaction.amount)).where(
            PaperWalletTransaction.transaction_type == "TRADE_PNL"
        )
        if latest_reset_id is not None:
            query = query.where(PaperWalletTransaction.id > latest_reset_id)
        result = await session.execute(
            query
        )
        return result.scalar() or 0.0

async def _get_wallet_account_state() -> tuple[float, float, float]:
    balance = await _get_paper_balance()
    pnl = await _get_total_pnl()
    starting_equity = round(balance - pnl, 2)
    return balance, starting_equity, pnl

async def _log_system_event(level: str, source: str, message: str, metadata: Optional[dict] = None):
    async with AsyncSessionLocal() as session:
        log = SystemLog(level=level, source=source, message=message, meta_data=metadata)
        session.add(log)
        await session.commit()

# --- System Control Endpoints ---

@app.get("/api/status", response_model=SystemStatus)
async def get_status():
    paper_balance, starting_equity, _ = await _get_wallet_account_state()
    orch = _get_orchestrator(starting_equity=starting_equity, current_equity=paper_balance)
    task_running = _orchestrator_task is not None and not _orchestrator_task.done()
    fetch_external = bool(getattr(orch, "fetch_external", False)) if orch else False
    current_price = None
    try:
        current_price = float(redis_client.client.get("latest_price") or 0) or None
    except Exception:
        pass

    if orch:
        status = orch.execution.get_status()
        return SystemStatus(
            running=_system_running and not _system_paused and task_running,
            paused=_system_paused,
            equity=status.get("equity", 10000.0),
            starting_equity=status.get("starting_equity", 10000.0),
            open_positions=status.get("open_positions", 0),
            closed_trades=status.get("closed_trades", 0),
            daily_pnl=status.get("daily_pnl", 0.0),
            weekly_pnl=status.get("weekly_pnl", 0.0),
            current_price=current_price or status.get("current_price"),
            last_cycle=(redis_client.get_json("latest_statistical_snapshot") or {}).get("timestamp") if redis_client.client else None,
            mode="PAPER",
            fetch_external=fetch_external
        )
    return SystemStatus(
        running=_system_running and not _system_paused and task_running,
        paused=_system_paused,
        equity=paper_balance,
        starting_equity=starting_equity,
        open_positions=0,
        closed_trades=0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        current_price=current_price,
        last_cycle=None,
        mode="PAPER",
        fetch_external=fetch_external
    )

@app.get("/api/health")
async def health_check():
    redis_ok = False
    database_ok = False

    try:
        redis_ok = bool(redis_client.client.ping())
    except Exception as e:
        logger.warning(f"Health check Redis ping failed: {e}")

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
        database_ok = True
    except Exception as e:
        logger.warning(f"Health check database query failed: {e}")

    return {
        "status": "ok" if redis_ok and database_ok else "degraded",
        "redis": redis_ok,
        "database": database_ok,
        "timestamp": utc_now().isoformat(),
    }

@app.get("/health")
async def root_health_check():
    return await health_check()

@app.post("/api/system/start")
async def start_system(req: Optional[SystemStartRequest] = Body(default=None)):
    global _system_running, _system_paused, _orchestrator_task
    paper_balance, starting_equity, _ = await _get_wallet_account_state()
    fetch_external = req.fetch_external if req else False
    orch = _get_orchestrator(
        starting_equity=starting_equity,
        current_equity=paper_balance,
        fetch_external=fetch_external,
    )
    if not orch:
        raise HTTPException(status_code=500, detail="Orchestrator not available")
    if _orchestrator_task and not _orchestrator_task.done():
        _system_running = True
        _system_paused = False
        return {"message": "System already running"}
    _system_running = True
    _system_paused = False
    _orchestrator_task = asyncio.create_task(orch.run(cycle_interval_seconds=60))
    await _log_system_event("INFO", "DASHBOARD", "System started")
    await manager.broadcast({"type": "system:start", "data": {"running": True}})
    return {"message": "System started"}

@app.post("/api/system/pause")
async def pause_system():
    global _system_paused
    _system_paused = True
    await _log_system_event("INFO", "DASHBOARD", "System paused")
    await manager.broadcast({"type": "system:pause", "data": {"paused": True}})
    return {"message": "System paused"}

@app.post("/api/system/resume")
async def resume_system():
    global _system_paused
    _system_paused = False
    await _log_system_event("INFO", "DASHBOARD", "System resumed")
    await manager.broadcast({"type": "system:resume", "data": {"paused": False}})
    return {"message": "System resumed"}

@app.post("/api/system/shutdown")
async def shutdown_system():
    global _system_running, _system_paused
    await _stop_orchestrator_task()
    _system_running = False
    _system_paused = False
    await _log_system_event("INFO", "DASHBOARD", "System shutdown")
    await manager.broadcast({"type": "system:shutdown", "data": {"running": False}})
    return {"message": "System shutdown"}

@app.post("/api/system/reset")
async def reset_system():
    global _system_running, _system_paused
    await _stop_orchestrator_task()
    _system_running = False
    _system_paused = False
    _reset_orchestrator_account()
    # Reset paper wallet
    async with AsyncSessionLocal() as session:
        tx = PaperWalletTransaction(
            transaction_type="RESET",
            amount=0.0,
            balance_after=10000.0,
            description="System reset"
        )
        session.add(tx)
        await session.commit()
    await _log_system_event("INFO", "DASHBOARD", "System reset")
    await manager.broadcast({"type": "system:reset", "data": {"balance": 10000.0}})
    return {"message": "System reset"}

# --- Positions & Trades ---

@app.get("/api/positions/open", response_model=List[PositionResponse])
async def get_open_positions():
    paper_balance, starting_equity, _ = await _get_wallet_account_state()
    orch = _get_orchestrator(starting_equity=starting_equity, current_equity=paper_balance)
    if not orch:
        return []
    positions = [p for p in orch.execution.positions if p.status == "OPEN"]
    return [
        PositionResponse(
            trade_id=p.trade_id,
            symbol=p.symbol,
            action=p.action,
            entry_price=p.entry_price,
            size=p.size,
            stop_loss=p.stop_loss,
            take_profit=p.take_profit,
            opened_at=p.opened_at.isoformat(),
            closed_at=p.closed_at.isoformat() if p.closed_at else None,
            conviction=p.conviction,
            reasoning=p.reasoning,
            pnl=round(p.pnl, 2),
            pnl_pct=round(p.pnl_pct, 4),
            status=p.status,
            exit_reason=None
        )
        for p in positions
    ]

@app.get("/api/positions/closed", response_model=TradeHistoryResponse)
async def get_closed_trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    paper_balance, starting_equity, _ = await _get_wallet_account_state()
    orch = _get_orchestrator(starting_equity=starting_equity, current_equity=paper_balance)
    if not orch:
        return TradeHistoryResponse(trades=[], total_count=0, total_pnl=0.0, win_count=0, loss_count=0, win_rate=0.0)
    all_closed = list(reversed(orch.execution.closed_trades))
    total = len(all_closed)
    trades = all_closed[offset:offset + limit]
    total_pnl = sum(t.pnl for t in all_closed)
    wins = sum(1 for t in all_closed if t.pnl > 0)
    losses = sum(1 for t in all_closed if t.pnl <= 0)
    win_rate = (wins / total * 100) if total > 0 else 0.0
    return TradeHistoryResponse(
        trades=[
            PositionResponse(
                trade_id=p.trade_id,
                symbol=p.symbol,
                action=p.action,
                entry_price=p.entry_price,
                size=p.size,
                stop_loss=p.stop_loss,
                take_profit=p.take_profit,
                opened_at=p.opened_at.isoformat(),
                closed_at=p.closed_at.isoformat() if p.closed_at else None,
                conviction=p.conviction,
                reasoning=p.reasoning,
                pnl=round(p.pnl, 2),
                pnl_pct=round(p.pnl_pct, 4),
                status=p.status,
                exit_reason=getattr(p, "exit_reason", None)
            )
            for p in trades
        ],
        total_count=total,
        total_pnl=round(total_pnl, 2),
        win_count=wins,
        loss_count=losses,
        win_rate=round(win_rate, 2)
    )

# --- Paper Wallet ---

@app.get("/api/wallet/balance", response_model=PaperWalletBalance)
async def get_wallet_balance():
    balance = await _get_paper_balance()
    deposited = await _get_total_deposited()
    withdrawn = await _get_total_withdrawn()
    pnl = await _get_total_pnl()
    return PaperWalletBalance(
        balance=balance,
        total_deposited=deposited,
        total_withdrawn=withdrawn,
        total_pnl=pnl
    )

@app.get("/api/wallet/transactions", response_model=List[PaperWalletTransactionResponse])
async def get_wallet_transactions(limit: int = Query(50, ge=1, le=500)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PaperWalletTransaction).order_by(desc(PaperWalletTransaction.id)).limit(limit)
        )
        txs = result.scalars().all()
        return [
            PaperWalletTransactionResponse(
                id=t.id,
                transaction_type=t.transaction_type,
                amount=t.amount,
                balance_after=t.balance_after,
                description=t.description,
                created_at=t.created_at.isoformat()
            )
            for t in txs
        ]

@app.post("/api/wallet/deposit")
async def deposit_funds(req: PaperWalletTransactionRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    new_balance = await _add_wallet_transaction("DEPOSIT", req.amount, req.description or "Manual deposit")
    _apply_orchestrator_cash_flow(req.amount)
    await _log_system_event("INFO", "DASHBOARD", f"Deposited {req.amount} paper funds", {"balance_after": new_balance})
    await manager.broadcast({"type": "wallet:deposit", "data": {"amount": req.amount, "balance": new_balance}})
    return {"message": f"Deposited {req.amount}", "balance": new_balance}

@app.post("/api/wallet/withdraw")
async def withdraw_funds(req: PaperWalletTransactionRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    current_balance = await _get_paper_balance()
    if req.amount > current_balance:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    new_balance = await _add_wallet_transaction("WITHDRAW", -req.amount, req.description or "Manual withdrawal")
    _apply_orchestrator_cash_flow(-req.amount)
    await _log_system_event("INFO", "DASHBOARD", f"Withdrew {req.amount} paper funds", {"balance_after": new_balance})
    await manager.broadcast({"type": "wallet:withdraw", "data": {"amount": req.amount, "balance": new_balance}})
    return {"message": f"Withdrew {req.amount}", "balance": new_balance}

# --- Agent Outputs ---

@app.get("/api/agents/outputs", response_model=List[AgentOutputResponse])
async def get_agent_outputs(
    agent: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    async with AsyncSessionLocal() as session:
        query = select(AgentOutputLog).order_by(desc(AgentOutputLog.cycle_timestamp))
        if agent:
            query = query.where(AgentOutputLog.agent_name == agent)
        query = query.limit(limit)
        result = await session.execute(query)
        logs = result.scalars().all()
        return [
            AgentOutputResponse(
                agent_name=l.agent_name,
                cycle_timestamp=l.cycle_timestamp.isoformat(),
                output_data=l.output_data
            )
            for l in logs
        ]

# --- System Logs ---

@app.get("/api/logs", response_model=List[SystemLogResponse])
async def get_system_logs(
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    async with AsyncSessionLocal() as session:
        query = select(SystemLog).order_by(desc(SystemLog.created_at))
        if level:
            query = query.where(SystemLog.level == level)
        if source:
            query = query.where(SystemLog.source == source)
        query = query.limit(limit)
        result = await session.execute(query)
        logs = result.scalars().all()
        return [
            SystemLogResponse(
                id=l.id,
                level=l.level,
                source=l.source,
                message=l.message,
                metadata=l.meta_data,
                created_at=l.created_at.isoformat()
            )
            for l in logs
        ]

# --- Chart Data ---

def _parse_chart_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

def _float_from_payload(payload: Dict[str, Any], key: str, fallback: float) -> float:
    value = payload.get(key, fallback)
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

def _latest_candle_point(
    symbol: str,
    timeframe: str,
    since: datetime,
) -> Optional[ChartDataPoint]:
    try:
        latest = redis_client.get_json("latest_candle")
    except Exception:
        return None
    if not latest:
        return None
    if latest.get("symbol", symbol) != symbol or latest.get("timeframe", timeframe) != timeframe:
        return None

    timestamp = _parse_chart_timestamp(latest.get("timestamp"))
    if timestamp is None or timestamp < since:
        return None

    close = _float_from_payload(latest, "close", 0.0)
    open_price = _float_from_payload(latest, "open", close)
    high = max(_float_from_payload(latest, "high", max(open_price, close)), open_price, close)
    low = min(_float_from_payload(latest, "low", min(open_price, close)), open_price, close)

    return ChartDataPoint(
        timestamp=timestamp.isoformat(),
        price=close,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=_float_from_payload(latest, "volume", 0.0),
        timeframe=timeframe,
        trade_marker=None
    )

def _merge_latest_candle(
    points: List[ChartDataPoint],
    symbol: str,
    timeframe: str,
    since: datetime,
) -> List[ChartDataPoint]:
    latest = _latest_candle_point(symbol, timeframe, since)
    if latest is None:
        return points

    latest_ts = _parse_chart_timestamp(latest.timestamp)
    merged = list(points)
    replaced = False
    for index, point in enumerate(merged):
        if _parse_chart_timestamp(point.timestamp) == latest_ts:
            merged[index] = latest
            replaced = True
            break
    if not replaced:
        merged.append(latest)

    return sorted(
        merged,
        key=lambda point: _parse_chart_timestamp(point.timestamp) or datetime.min
    )

@app.get("/api/chart/data", response_model=List[ChartDataPoint])
async def get_chart_data(
    symbol: str = Query("BTC-USD"),
    hours: int = Query(24, ge=1, le=168),
    timeframe: str = Query(TIMEFRAME)
):
    async with AsyncSessionLocal() as session:
        since = utc_now_naive() - timedelta(hours=hours)
        result = await session.execute(
            select(Candle).where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= since
            ).order_by(Candle.timestamp)
        )
        candles = result.scalars().all()
        if candles:
            candle_points = [
                ChartDataPoint(
                    timestamp=c.timestamp.isoformat(),
                    price=c.close,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                    timeframe=c.timeframe,
                    trade_marker=None
                )
                for c in candles
            ]
            return _merge_latest_candle(candle_points, symbol, timeframe, since)

        latest_points = _merge_latest_candle([], symbol, timeframe, since)
        if latest_points:
            return latest_points

        result = await session.execute(
            select(PriceTick).where(
                PriceTick.symbol == symbol,
                PriceTick.timestamp >= since
            ).order_by(PriceTick.timestamp)
        )
        ticks = result.scalars().all()
        return [
            ChartDataPoint(
                timestamp=t.timestamp.isoformat(),
                price=t.price,
                open=t.price,
                high=t.price,
                low=t.price,
                close=t.price,
                volume=0.0,
                timeframe="tick",
                trade_marker=None
            )
            for t in ticks
        ]

# --- Statistical Snapshot ---

@app.get("/api/statistics/latest", response_model=Optional[StatisticalSnapshotResponse])
async def get_latest_statistics():
    data = redis_client.get_json("latest_statistical_snapshot")
    if not data:
        return None
    return StatisticalSnapshotResponse(**data)

# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back or handle client messages
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": utc_now().isoformat()})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
