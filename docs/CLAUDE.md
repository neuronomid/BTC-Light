# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a **Statistical-LLM Hybrid Crypto Futures Trading System** for BTC perpetual futures on the 4-hour timeframe. It combines a Python statistical analysis engine, an LLM agent layer, a Python rules/safety engine, and a Rust execution engine.

## Common Commands

### Environment Setup

The Python virtual environment lives at `venv/`. Activate it before running any Python code:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in secrets (e.g., `OPENROUTER_API_KEY`). All configuration is loaded from `.env` via `config/settings.py`.

### Python Entry Points

- **One-off runs:** `python run.py --mode <MODE>`
  - `ingest` — fetch and store Yahoo Finance BTC data
  - `stats` — run the statistical engine and print the JSON snapshot
  - `full` — run stats + mock/real agents + safety check and print results
  - `trade` — placeholder for live trading loop
  - Flags: `--use-real-agents` (requires `OPENROUTER_API_KEY`), `--fetch-external` (SPX, DXY, Gold, ETH), `--equity 10000`

- **Continuous paper-trading loop:** `python orchestrator.py`
  - Flags: `--use-real-agents`, `--fetch-external`, `--equity 10000`, `--interval 60` (cycle interval in seconds)

### Rust Execution Engine

Inside `execution_engine/`:

```bash
cd execution_engine
cargo build
cargo run
```

The Rust binary subscribes to Redis `trade_decision` messages published by the Python orchestrator and runs its own tick loop for stop-loss / take-profit / duration / circuit-breaker enforcement.

### Database

PostgreSQL (TimescaleDB-compatible schema) is used. Tables are auto-created on first run via `shared.db.init_db()`. The async URL is built by replacing `postgresql://` with `postgresql+asyncpg://` in `shared/db.py`.

## High-Level Architecture

### Layered Design

The system is split into four layers that communicate asynchronously through **Redis** (pub/sub + KV):

1. **Data Ingestion** (`data/`)
   - `ingest_yahoo.py` fetches BTC-USD from Yahoo Finance, resamples to 4H, stores candles in PostgreSQL, and publishes the latest candle to Redis.
   - `external_feeds.py` fetches SPX, DXY, Gold, and ETH for correlation analysis.

2. **Statistical Engine** (`statistical_engine/`)
   - `engine.py` (`StatisticalEngine`) orchestrates all modules. It refreshes data, runs every module, stores the snapshot to PostgreSQL, and publishes it to Redis.
   - Modules: `regime.py` (HMM), `trend.py` (Hurst/ADF/ADX), `volatility.py` (GARCH/EGARCH), `change_point.py` (BOCPD/CUSUM), `tail_risk.py` (EVT/CVaR), `probability.py` (Monte Carlo + Kelly), `efficiency.py` (entropy/variance ratio), `correlation.py` (DCC-GARCH/copulas).
   - `evaluate_trade()` in `engine.py` runs Monte Carlo simulation to estimate probability of hitting take-profit before stop-loss, using GARCH volatility and regime-conditional drift.

3. **Agent Layer** (`agent_layer/`)
   - `agents.py` defines `MockAgentLayer` and Pydantic output schemas for four agents:
     - **Market Context Agent** — interprets statistical outputs into market narrative and key levels.
     - **News/Sentiment Agent** — assesses directional bias from news flow.
     - **Trade Decision Agent** — makes final LONG/SHORT/NO_TRADE call with conviction, entry zone, SL/TP.
     - **Risk Monitor Agent** — monitors open positions for thesis invalidation or regime shifts.
   - `openrouter_agents.py` provides `OpenRouterAgentLayer`, which uses the OpenRouter API (Claude Opus 4.6 / Sonnet 4.6) for real agent reasoning.

4. **Rules & Execution Engines** (`rules_engine/` + `execution_engine/`)
   - `rules_engine/safety.py` (`SafetyEngine`) enforces hard safety rules (max risk per trade, daily/weekly loss limits, conviction threshold, EV threshold) and calculates position size using fractional Kelly.
   - `rules_engine/execution.py` (`PaperExecutionEngine`) simulates order execution: evaluates decisions against safety, opens positions, ticks SL/TP/duration/circuit breakers, and tracks PnL.
   - `execution_engine/` (Rust) is the production execution layer. It mirrors the Python paper engine but runs as a separate async binary. It listens to Redis `trade_decision` for new decisions and `latest_price` for price updates.

### Orchestration & Data Flow

- `orchestrator.py` (`TradingOrchestrator`) ties the Python side together in a continuous loop:
  1. Refresh data (`StatisticalEngine.refresh_data`).
  2. Run statistical snapshot (`StatisticalEngine.run_cycle`).
  3. Run agents (`market_context` → `news_sentiment` → `trade_decision`).
  4. Evaluate trade probability (`StatisticalEngine.evaluate_trade`).
  5. Publish trade decision to Redis (`trade_decision` channel).
  6. Evaluate opening a new position (`PaperExecutionEngine.evaluate_decision`).
  7. Tick execution (`PaperExecutionEngine.tick`) to check SL/TP/duration.
  8. Publish trading status to Redis.

- The Rust execution engine can run alongside the Python orchestrator. It receives the same `trade_decision` messages and manages its own position state. Both sides write to Redis and can read each other’s state.

### Shared Infrastructure

- **Redis** (`shared/redis_client.py`): used for pub/sub messaging and short-lived KV state (latest price, latest snapshot, trading status, position events).
- **PostgreSQL** (`shared/db.py`): persistent storage for candles, trade logs, and statistical snapshots. Uses SQLAlchemy async ORM with `asyncpg`.

## Key Design Decisions

- **Separation of concerns:** Statistics for measurement, LLMs for interpretation, rules for execution. Agents never block execution; the rules engine never waits for agents.
- **Two execution engines:** Python `PaperExecutionEngine` for rapid prototyping and backtesting; Rust `execution_engine` for production-grade latency and safety.
- **Hard safety rules are non-overridable** by agents. Position sizing uses fractional Kelly (default 0.25×) capped at 2% account risk per trade.
- **Regime detection drives strategy selection:** Trend-following only fires when HMM state is `BULL_TREND`/`BEAR_TREND` and Hurst exponent + ADX confirm trending. Mean-reversion only fires when Hurst < 0.45 and ADF rejects unit root.
- **Change-point detection triggers trading halts:** When `recommend_halt` is true, the system should not open new trades because historically-calibrated models are unreliable during regime transitions.

## Testing

The `tests/` directory exists but is currently empty. There is no test runner configured yet. If adding tests, `pytest` is the expected runner since the project is pure Python + Rust.

## Important Files

- `config/settings.py` — all tunable parameters (risk limits, model names, DB/Redis URLs).
- `PRD.md` — product requirements and development phases.
- `SPECS.md` — deep technical specifications for every statistical module and agent, including expected JSON output schemas.
