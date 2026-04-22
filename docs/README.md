# BTC Light Trading System

An automated Bitcoin perpetual futures trading system that combines statistical analysis with AI-driven decision making.

## What It Does

This system watches the Bitcoin market, analyzes it from multiple angles, and decides whether to enter or exit trades. It runs on the 4-hour timeframe and aims for 1-3 high-conviction trades per day that resolve within 24 hours.

## How It Works (The Big Picture)

Think of the system as a trading desk with three specialists who each do one thing well, plus a strict risk manager who has final say:

### 1. The Numbers Specialist (Statistical Engine)
- Watches price data and calculates hard metrics: trend strength, volatility, market regime
- Detects when market behavior changes significantly (regime shifts)
- Estimates the probability of a trade reaching profit before hitting a stop-loss
- Uses models like GARCH for volatility forecasting and Hidden Markov Models for regime detection

### 2. The Context Specialist (LLM Agent Layer)
- Reads market context, news sentiment, and macro factors
- Combines the statistical output with qualitative judgment
- Makes a directional call: go LONG, go SHORT, or stay flat
- Assigns a conviction score to each decision
- Can use real Anthropic Claude agents (with API key) or mock agents for testing

### 3. The Safety Officer (Rules Engine)
- Runs hard safety checks before any trade is executed
- Enforces position sizing limits (max 2% account risk per trade)
- Monitors drawdowns and can trigger circuit breakers
- Ensures stop-losses and take-profits are properly set

### 4. The Execution Desk (Rust Engine)
- Handles the actual order placement and position management
- Monitors open positions for stop-loss / take-profit triggers
- Tracks equity, PnL, and trade history
- Runs in Rust for speed and reliability

## Data Flow

```
1. Data Layer fetches BTC price + external data (SPX, DXY, Gold, ETH)
           |
           v
2. Statistical Engine computes metrics and probabilities
           |
           v
3. Agent Layer interprets data and makes trade decision
           |
           v
4. Rules Engine validates the decision against safety constraints
           |
           v
5. Execution Engine places the trade and manages the position
```

All components communicate through Redis, so the execution layer never waits for the AI agents.

## Key Features

- **Regime Detection**: Knows whether the market is trending up, trending down, or ranging
- **Probabilistic Evaluation**: Every trade gets a Monte Carlo simulation to estimate win probability
- **Kelly Sizing**: Position sizes are calculated using fractional Kelly criterion based on estimated edge
- **Adaptive Risk**: Stop-loss distances adjust dynamically based on GARCH-forecasted volatility
- **Paper Trading**: All execution is simulated until you explicitly switch to live trading
- **Closed-Loop Learning**: Every trade outcome is logged with full context for later analysis

## Running the System

### One-command backend
```bash
./backend
```

This starts Redis and PostgreSQL with Homebrew when they are installed but not
running, falls back to `pg_ctl` when macOS launch services fail, bootstraps the
configured PostgreSQL role/database when possible, then launches the continuous
paper-trading backend. Use `./backend api` for the FastAPI dashboard backend,
or `./backend --help` for the other modes.

The launcher uses exported `REDIS_*` and `DB_*` values for setup checks, falling
back to the same defaults shown in `.env.example`.

### One-shot analysis (no trading)
```bash
python run.py --mode stats
```

### Full pipeline with mock agents
```bash
python run.py --mode full
```

### Full pipeline with real Anthropic agents
```bash
python run.py --mode full --use-real-agents
```

### Continuous trading loop (orchestrator)
```bash
python orchestrator.py --interval 60
```

### With external correlation data
```bash
python run.py --mode full --fetch-external
```

## Project Structure

```
├── data/               # Data ingestion (Yahoo Finance, external feeds)
├── statistical_engine/ # Math and models (regime, volatility, probability)
├── agent_layer/        # LLM agents (market context, sentiment, decisions)
├── rules_engine/       # Safety checks and paper execution
├── execution_engine/   # Rust-based order execution
├── shared/             # Database and Redis utilities
├── config/             # Settings and configuration
├── notebooks/          # Analysis notebooks
└── tests/              # Test suite
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:
- Database connection
- Redis connection
- Anthropic API key (optional, for real agents)
- Trading symbol and timeframe

## Safety First

This system is designed with multiple layers of protection:
- Maximum 2% account risk per trade
- Hard circuit breakers on drawdown
- Paper trading by default
- All stop-losses are pre-placed as exchange orders

**Do not run with real money until you have completed at least 2-3 months of paper trading with positive metrics.**

## Tech Stack

- **Python**: Data ingestion, statistical engine, agent layer, rules engine
- **Rust**: High-performance execution engine
- **Redis**: Shared state and inter-process communication
- **SQLite/PostgreSQL**: Trade logging and historical data
- **Yahoo Finance**: Primary price data source
