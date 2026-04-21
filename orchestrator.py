import asyncio
import json
from datetime import datetime
from typing import Optional
from shared.db import init_db
from shared.redis_client import redis_client
from data.ingest_yahoo import YahooFinanceIngestor
from data.external_feeds import ExternalFeedManager
from statistical_engine.engine import StatisticalEngine
from agent_layer.agents import MockAgentLayer
from rules_engine.safety import SafetyEngine
from rules_engine.execution import PaperExecutionEngine
from config.settings import SYMBOL, TIMEFRAME
from loguru import logger

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
            prob = self.engine.evaluate_trade(dec.action, dec.stop_loss_pct, dec.take_profit_pct)
            snapshot["probability"] = prob
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
        self._running = True
        logger.info("Trading orchestrator started.")
        while self._running:
            await self._cycle()
            await asyncio.sleep(cycle_interval_seconds)

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
