# AGENTS.md

Guidance for coding agents working in this repository.

## Project Purpose

This is a Statistical-LLM Hybrid Crypto Futures Trading System for BTC perpetual futures on the 4-hour timeframe. Treat it as safety-critical trading infrastructure even when running in paper mode. Preserve the separation of concerns:

- `data/`: fetch and normalize market data.
- `statistical_engine/`: quantitative regime, trend, volatility, change-point, tail-risk, probability, efficiency, and correlation analysis.
- `agent_layer/`: mock and Anthropic-backed LLM agents that interpret statistical output and produce structured decisions.
- `rules_engine/`: Python safety and paper execution.
- `execution_engine/`: Rust execution service that consumes Redis decisions and mirrors safety checks.
- `shared/`: PostgreSQL and Redis infrastructure.
- `dashboard/`: Next.js dashboard. Also read `dashboard/AGENTS.md` before editing there.

Do not loosen risk controls, bypass safety checks, or imply the system is safe for live capital without explicit paper-trading validation.

## Repository Shape

The root checkout currently is not a Git repository, while `dashboard/` and `execution_engine/` each contain their own `.git` directories. Check status in the relevant working tree before making changes there.

Ignore generated and dependency directories unless the user explicitly asks about them:

- `venv/`
- `__pycache__/`
- `dashboard/node_modules/`
- `dashboard/.next/`
- `execution_engine/target/`
- `.DS_Store`

Do not read, print, or copy `.env`. Use `.env.example` for configuration shape.

## Environment

Python uses the checked-in virtual environment path:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Full backend runs require local Redis and PostgreSQL/Timescale-compatible PostgreSQL. Tables are created by `shared.db.init_db()`. Data fetches use Yahoo Finance and need network access.

Configuration is loaded by `config/settings.py` from `.env`. Important defaults:

- Symbol/timeframe: `BTC-USD`, `4h`
- Max risk per trade: `0.02`
- Min conviction to trade: `70`
- Min EV to trade: `0.005`
- Real agents require `ANTHROPIC_API_KEY`

## Common Commands

From the repo root:

```bash
python run.py --mode ingest
python run.py --mode stats
python run.py --mode full
python run.py --mode full --fetch-external
python run.py --mode full --use-real-agents
python orchestrator.py --interval 60
```

Rust execution engine:

```bash
cd execution_engine
cargo build
cargo run
cargo test
```

Dashboard:

```bash
cd dashboard
npm run dev
npm run build
npm run lint
```

The dashboard uses Next.js `16.2.4`; the local `dashboard/AGENTS.md` says to read relevant guides in `node_modules/next/dist/docs/` before changing Next.js APIs or conventions.

## Data And Runtime Contracts

Keep these Redis keys/channels stable unless updating all producers and consumers together:

- `candles:new`
- `latest_candle`
- `statistical:snapshot`
- `latest_statistical_snapshot`
- `latest_price`
- `trade_decision`
- `trading_status`
- `position:opened`
- `position:closed`

`StatisticalEngine.run_cycle()` refreshes data, runs all statistical modules, stores a `StatisticalSnapshot`, and publishes the snapshot. The snapshot shape is consumed by agents, safety, and execution. Preserve these top-level keys when extending it:

- `symbol`
- `timeframe`
- `timestamp`
- `latest_close`
- `regime`
- `trend`
- `volatility`
- `change_point`
- `tail_risk`
- `efficiency`
- `correlation`
- `probability` when a trade has been evaluated

Trade decisions published on `trade_decision` are the agent decision payload plus `snapshot`. The Rust `TradeDecision` expects:

- `action`: `LONG`, `SHORT`, or `NO_TRADE`
- `conviction`
- `stop_loss_pct`
- `take_profit_pct`
- `size_multiplier`
- `reasoning`
- optional `entry_zone`

Agent outputs are Pydantic models in `agent_layer/agents.py`. Anthropic-backed agents must return strict JSON matching those schemas. Keep mock agents deterministic and usable without external APIs.

## Safety Rules

Safety checks are non-overridable. Before opening positions, both Python and Rust enforce conviction, EV, change-point halts, max positions, and drawdown limits. If changing a risk constant or rule, update both sides when applicable:

- Python: `config/settings.py`, `rules_engine/safety.py`, `rules_engine/execution.py`
- Rust: `execution_engine/src/config.rs`, `execution_engine/src/safety.rs`, `execution_engine/src/position_manager.rs`

Paper execution and Rust execution are intended to remain behaviorally aligned. Do not change one path without checking the other for matching semantics.

## Coding Guidelines

- Prefer small, local changes that match the existing simple module style.
- Keep structured outputs JSON-serializable; Redis helpers call `json.dumps`.
- Use typed Pydantic/dataclass/Rust structs for cross-layer contracts instead of ad hoc strings.
- Avoid expensive model fitting in tight loops unless necessary; the statistical engine already fits HMM and GARCH during `run_all()`.
- Handle insufficient data gracefully by returning `{}` or clear warnings, matching the existing statistical modules.
- Keep comments sparse and useful. Existing code favors direct, readable implementations.
- Do not add live exchange trading or order placement without explicit user direction.

## Verification

There is no populated Python test suite yet. Use the smallest verification that matches the change:

- Python syntax/import checks for touched modules:

```bash
python -m compileall data statistical_engine agent_layer rules_engine shared config run.py orchestrator.py
```

- One-shot backend smoke tests when Redis/PostgreSQL and network are available:

```bash
python run.py --mode stats
python run.py --mode full
```

- Rust:

```bash
cd execution_engine
cargo test
cargo build
```

- Dashboard:

```bash
cd dashboard
npm run lint
npm run build
```

If a command cannot run because infrastructure, network, or secrets are missing, report that explicitly instead of hiding the gap.
