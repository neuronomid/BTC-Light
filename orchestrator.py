import asyncio
import json
import os
import socket
import uuid
from datetime import UTC, datetime
from typing import Optional
from shared.db import AsyncSessionLocal, init_db
from shared.redis_client import redis_client
from shared.time_utils import utc_now_naive
from data.ingest_yahoo import YahooFinanceIngestor
from data.external_feeds import ExternalFeedManager
from statistical_engine.engine import StatisticalEngine
from agent_layer.agents import MockAgentLayer
from rules_engine.safety import SafetyEngine
from rules_engine.execution import PaperExecutionEngine
from config.settings import SYMBOL, TIMEFRAME
from loguru import logger

ORCHESTRATOR_LOCK_KEY = "orchestrator:active"
MIN_ORCHESTRATOR_LOCK_TTL_SECONDS = 300

class TradingOrchestrator:
    def __init__(
        self,
        use_real_agents: bool = False,
        fetch_external: bool = False,
        initial_equity: float = 10000.0,
        paper_mode: bool = True
    ):
        self.engine = StatisticalEngine()
        self.safety = SafetyEngine()
        self.execution = PaperExecutionEngine(initial_equity=initial_equity)
        self.use_real_agents = use_real_agents
        self.fetch_external = fetch_external
        self._running = False
        self._agents = None
        self._lock_token: Optional[str] = None
        self._lock_ttl_seconds = MIN_ORCHESTRATOR_LOCK_TTL_SECONDS

    def _build_lock_token(self) -> str:
        return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"

    def _acquire_run_lock(self) -> bool:
        self._lock_token = self._build_lock_token()
        acquired = redis_client.client.set(
            ORCHESTRATOR_LOCK_KEY,
            self._lock_token,
            nx=True,
            ex=self._lock_ttl_seconds,
        )
        if acquired:
            return True

        owner = redis_client.client.get(ORCHESTRATOR_LOCK_KEY)
        logger.error(f"Another Python orchestrator is already active: {owner}")
        self._lock_token = None
        return False

    def _refresh_run_lock(self) -> bool:
        if not self._lock_token:
            return False
        owner = redis_client.client.get(ORCHESTRATOR_LOCK_KEY)
        if owner != self._lock_token:
            logger.error(f"Python orchestrator lock lost to: {owner}")
            return False
        redis_client.client.expire(ORCHESTRATOR_LOCK_KEY, self._lock_ttl_seconds)
        return True

    def _release_run_lock(self):
        if not self._lock_token:
            return
        try:
            redis_client.client.eval(
                """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                end
                return 0
                """,
                1,
                ORCHESTRATOR_LOCK_KEY,
                self._lock_token,
            )
        finally:
            self._lock_token = None

    def _cycle_timestamp(self, snapshot: dict) -> datetime:
        raw = snapshot.get("timestamp")
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    return parsed.astimezone(UTC).replace(tzinfo=None)
                return parsed
            except ValueError:
                pass
        return utc_now_naive()

    async def _record_agent_outputs(self, cycle_timestamp: datetime, ctx, news, dec):
        try:
            from dashboard_api.db_models import AgentOutputLog

            rows = [
                AgentOutputLog(
                    agent_name="market_context",
                    cycle_timestamp=cycle_timestamp,
                    output_data=ctx.model_dump(mode="json"),
                ),
                AgentOutputLog(
                    agent_name="news_sentiment",
                    cycle_timestamp=cycle_timestamp,
                    output_data=news.model_dump(mode="json"),
                ),
                AgentOutputLog(
                    agent_name="trade_decision",
                    cycle_timestamp=cycle_timestamp,
                    output_data=dec.model_dump(mode="json"),
                ),
            ]
            async with AsyncSessionLocal() as session:
                session.add_all(rows)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to record agent outputs: {e}")

    def _get_agents(self):
        if self._agents is None:
            if self.use_real_agents:
                try:
                    from agent_layer.openrouter_agents import OpenRouterAgentLayer
                    logger.info("Using OpenRouterAgentLayer")
                    self._agents = OpenRouterAgentLayer()
                except Exception as e:
                    logger.warning(f"Failed to load OpenRouterAgentLayer: {e}. Using MockAgentLayer.")
                    self._agents = MockAgentLayer()
            else:
                self._agents = MockAgentLayer()
        return self._agents

    async def _cycle(self):
        try:
            snapshot = await self.engine.run_cycle(fetch_external=self.fetch_external)
            latest_price = snapshot.get("latest_close")
            if latest_price:
                self.execution.update_price(latest_price)
                redis_client.client.set("latest_price", str(latest_price))
            agents = self._get_agents()
            ctx = agents.market_context(snapshot)
            news = agents.news_sentiment(snapshot)
            dec = agents.trade_decision(snapshot, ctx, news)
            await self._record_agent_outputs(self._cycle_timestamp(snapshot), ctx, news, dec)
            prob = self.engine.evaluate_trade(dec.action, dec.stop_loss_pct, dec.take_profit_pct)
            snapshot["probability"] = prob
            redis_client.set_json("latest_statistical_snapshot", snapshot, ttl=3600)
            # Publish trade decision to Redis for Rust execution engine
            decision_payload = dec.model_dump()
            decision_payload["snapshot"] = snapshot
            redis_client.publish("trade_decision", decision_payload)
            # Check if we should open a new position
            if dec.action in ("LONG", "SHORT"):
                self.execution.evaluate_decision(snapshot, dec.model_dump())
            # Tick execution (check SL/TP/duration)
            await self.execution.tick()
            # Publish status
            status = self.execution.get_status()
            redis_client.set_json("trading_status", status, ttl=60)
            logger.info(f"Cycle complete | Equity: {status['equity']:.2f} | Open: {status['open_positions']} | Daily PnL: {status['daily_pnl']:.2f}")
        except Exception as e:
            logger.error(f"Orchestrator cycle error: {e}")

    async def run(self, cycle_interval_seconds: int = 60):
        await init_db()
        redis_client.connect()
        self._lock_ttl_seconds = max(
            MIN_ORCHESTRATOR_LOCK_TTL_SECONDS,
            cycle_interval_seconds * 5,
        )
        if not self._acquire_run_lock():
            self._running = False
            return
        self._running = True
        logger.info("Trading orchestrator started.")
        try:
            while self._running:
                if not self._refresh_run_lock():
                    break
                await self._cycle()
                if not self._refresh_run_lock():
                    break
                await asyncio.sleep(cycle_interval_seconds)
        finally:
            self._running = False
            self._release_run_lock()

    def stop(self):
        self._running = False
        self.execution.stop()
        logger.info("Trading orchestrator stopped.")

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="BTC Trading Orchestrator")
    parser.add_argument("--use-real-agents", action="store_true")
    parser.add_argument("--fetch-external", action="store_true")
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--interval", type=int, default=60, help="Cycle interval in seconds")
    args = parser.parse_args()

    orch = TradingOrchestrator(
        use_real_agents=args.use_real_agents,
        fetch_external=args.fetch_external,
        initial_equity=args.equity
    )
    try:
        await orch.run(cycle_interval_seconds=args.interval)
    except KeyboardInterrupt:
        orch.stop()

if __name__ == "__main__":
    asyncio.run(main())
