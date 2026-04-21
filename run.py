import asyncio
import json
import argparse
from shared.db import init_db
from data.ingest_yahoo import YahooFinanceIngestor
from data.external_feeds import ExternalFeedManager
from statistical_engine.engine import StatisticalEngine
from agent_layer.agents import MockAgentLayer
from rules_engine.safety import SafetyEngine
from shared.redis_client import redis_client
from loguru import logger

def get_agent_layer(use_real: bool):
    if use_real:
        try:
            from agent_layer.openrouter_agents import OpenRouterAgentLayer
            logger.info("Using OpenRouterAgentLayer")
            return OpenRouterAgentLayer()
        except Exception as e:
            logger.warning(f"Failed to load OpenRouterAgentLayer: {e}. Falling back to MockAgentLayer.")
            return MockAgentLayer()
    return MockAgentLayer()

async def main():
    parser = argparse.ArgumentParser(description="BTC Trading System")
    parser.add_argument("--mode", choices=["ingest", "stats", "full", "trade"], default="full")
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--use-real-agents", action="store_true", help="Use OpenRouter API agents (requires OPENROUTER_API_KEY)")
    parser.add_argument("--fetch-external", action="store_true", help="Fetch external correlation data (SPX, DXY, Gold, ETH)")
    args = parser.parse_args()

    await init_db()
    redis_client.connect()

    if args.mode == "ingest":
        ingestor = YahooFinanceIngestor()
        await ingestor.run_once()
    elif args.mode == "stats":
        engine = StatisticalEngine()
        snapshot = await engine.run_cycle(fetch_external=args.fetch_external)
        print(json.dumps(snapshot, indent=2, default=str))
    elif args.mode == "full":
        engine = StatisticalEngine()
        agents = get_agent_layer(args.use_real_agents)
        safety = SafetyEngine()
        snapshot = await engine.run_cycle(fetch_external=args.fetch_external)
        ctx = agents.market_context(snapshot)
        news = agents.news_sentiment(snapshot)
        dec = agents.trade_decision(snapshot, ctx, news)
        prob = engine.evaluate_trade(dec.action, dec.stop_loss_pct, dec.take_profit_pct)
        snapshot["probability"] = prob
        check = safety.check_all(dec.model_dump(), snapshot, equity=args.equity)
        print("=== Statistical Snapshot ===")
        print(json.dumps(snapshot, indent=2, default=str))
        print("\n=== Agent Decision ===")
        print(json.dumps(dec.model_dump(), indent=2, default=str))
        print(f"\n=== Safety Check ===")
        print(f"Passed: {check.passed} | Reason: {check.reason}")
    elif args.mode == "trade":
        logger.info("Trade mode: continuous loop not yet implemented.")

if __name__ == "__main__":
    asyncio.run(main())
