# Product Requirements Document
## Statistical-LLM Hybrid Crypto Futures Trading System

**Version:** 1.0
**Date:** April 2026
**Status:** Draft

---

## 1. Executive Summary

An automated trading system for Bitcoin perpetual futures operating on the 4-hour timeframe. The system combines three layers of intelligence: a **Statistical Analysis Engine** that computes rigorous quantitative measures of market state, an **LLM Agent Layer** that interprets statistical outputs alongside qualitative data (news, sentiment, macro context) to make trading decisions, and a **Rules Engine** that handles execution, risk management, and hard safety constraints.

The core thesis: LLMs alone cannot reliably estimate probabilities or identify regime shifts mathematically. Statistical models alone lack contextual judgment about why market conditions have changed. Combining both produces better decisions than either in isolation.

---

## 2. Problem Statement

Pure rule-based systems fail when market regimes shift because they're calibrated to past conditions. Pure LLM systems fail because language models hallucinate probabilities, miss subtle statistical signals, and are too slow for execution-sensitive decisions. Most retail automated trading systems fail because they lack rigorous statistical grounding and treat complex markets as simple pattern-matching problems.

This system addresses these failures by enforcing a separation of concerns: statistics for measurement, LLMs for interpretation, rules for execution.

---

## 3. Goals and Non-Goals

### Goals
- Place 1-3 high-conviction trades per day on BTC perpetual futures
- Achieve positive risk-adjusted returns (Sharpe > 1.0) over 6-month rolling windows
- Each trade resolves within 24 hours (4H timeframe, hold 1-6 candles max)
- Automatic regime detection and strategy adjustment without manual intervention
- Transparent, auditable decision logs for every trade

### Non-Goals
- High-frequency trading or sub-minute execution
- Arbitrage between exchanges (competitive landscape too crowded)
- Prediction market trading (Polymarket) — replaced by direct futures
- Portfolio of multiple assets (BTC-only for MVP)
- Beating institutional quant funds (realistic benchmark is retail algo traders)

---

## 4. Success Metrics

### Primary
- **Sharpe Ratio** > 1.0 over rolling 6-month window
- **Profit Factor** > 1.5 (gross profit / gross loss)
- **Win Rate** > 45% with average win > average loss
- **Max Drawdown** < 20% of account equity

### Secondary
- **LLM Prediction Accuracy** — track agreement between Trade Decision Agent conviction and realized outcome
- **Regime Classification Accuracy** — measured against forward-realized volatility and trend characteristics
- **Statistical Signal Quality** — information coefficient (IC) between statistical features and forward returns
- **System Uptime** > 99.5%
- **Execution Slippage** < 0.05% per trade

---

## 5. User Profile

Single user (developer/trader). Technical background in neuroscience with strong interest in AI systems and quantitative methods. Direct communication style, low tolerance for fluff. Needs:
- Daily trade resolution (no weeks-long uncertainty)
- Full transparency into why each trade was taken
- Manual override capability for all positions
- Clear validation results before committing real capital

---

## 6. System Overview

Four major components operating asynchronously:

1. **Data Layer** — real-time price, order book, funding, news, on-chain metrics
2. **Statistical Engine** — continuous computation of regime, volatility, trend strength, tail risk, probability estimates
3. **Agent Layer** — four specialized LLM agents (Market Context, News/Sentiment, Trade Decision, Risk Monitor)
4. **Execution Layer** — Rust-based rules engine handling orders, stops, position management, circuit breakers

All components communicate through a Redis shared-state layer. Agents never block execution; rules engine never waits for agents.

---

## 7. Core Features

### 7.1 Statistical Regime Detection
Continuously classify the market into one of several regimes (trending bull, trending bear, high-volatility range, low-volatility range) using Hidden Markov Models and Hurst exponent. Feeds both the agent layer and rules engine.

### 7.2 Probabilistic Trade Evaluation
Every potential trade is evaluated through Monte Carlo simulation using GARCH-forecasted volatility to estimate the probability of hitting take-profit before stop-loss. Combined with Bayesian posterior updates from multiple signals.

### 7.3 Kelly-Optimized Position Sizing
Position sizes computed using fractional Kelly criterion based on estimated edge, regime-conditional win rate, and risk-reward ratio. Never exceeds 2% account risk per trade.

### 7.4 Multi-Agent Decision Pipeline
Four specialized LLM agents handle distinct reasoning tasks. Trade Decision Agent synthesizes statistical engine output plus other agents' assessments to produce final directional call with conviction score.

### 7.5 Adaptive Risk Management
GARCH-forecasted volatility determines dynamic stop-loss distances. Extreme Value Theory monitors tail risk. Bayesian change point detection triggers trading halts during regime transitions.

### 7.6 Closed-Loop Learning
Every trade outcome logged with full statistical and qualitative context. Weekly analysis identifies which regimes, statistical signals, and LLM reasoning patterns produced best outcomes. Agent prompts refined based on observed failure modes.

---

## 8. Assumptions and Risks

### Assumptions
- BTC futures markets remain liquid enough for 1-2% account positions without material slippage
- Statistical relationships have some persistence (non-stationarity is bounded, not extreme)
- LLM capabilities remain at least at current level
- Exchange APIs remain functional and rate limits don't break the system

### Critical Risks
| Risk | Severity | Mitigation |
|------|----------|------------|
| Overfit statistical models to historical noise | High | Out-of-sample validation, rolling recalibration, parameter stability monitoring |
| Regime shift invalidates all models simultaneously | High | Change point detection, trading halt on regime uncertainty, hard drawdown circuit breaker |
| LLM confident but wrong | Medium | Calibration tracking, conviction-outcome correlation monitoring, capped position sizes |
| Exchange outage during open position | Medium | Stop-losses placed as OCO orders on exchange, not locally enforced |
| Flash crash exceeds stop-loss | High | Position sizing accounts for 3-sigma gap risk, not just normal stop distance |
| Funding rate drain on held positions | Low | Funding rate filter, max hold duration enforcement |
| Correlated losses across trades | Medium | One position at a time for MVP, daily loss circuit breaker |

### Honest Assessment
This system is more rigorous than typical retail approaches but is not guaranteed to be profitable. The edge depends on:
1. Whether statistical regime detection actually has predictive power for BTC (partially validated in academic literature, unclear in current crypto markets)
2. Whether the LLM layer adds signal beyond the statistical engine alone (must be measured, not assumed)
3. Whether execution is clean enough that modeled edge survives real-world slippage and fees

Paper trading for 2-3 months minimum before real capital. Start with position sizes small enough that total account loss is tolerable.

---

## 9. Development Phases

### Phase 1: Foundation (Weeks 1-4)
Data infrastructure, exchange connectivity, time-series database, backtesting framework.

### Phase 2: Statistical Engine (Weeks 5-8)
Implement all statistical modules with offline validation against historical BTC data.

### Phase 3: Agent Layer (Weeks 9-11)
Build four agents with prompt engineering, integrate statistical engine outputs into agent context.

### Phase 4: Rules Engine (Weeks 12-14)
Rust execution layer, order management, hard safety rules, Redis integration.

### Phase 5: Paper Trading (Weeks 15-22)
Minimum 8 weeks live paper trading with full logging. Metrics review gates entry to Phase 6.

### Phase 6: Live Trading, Small Capital (Weeks 23+)
Start with position sizes 10x smaller than target. Scale up only after 30+ successful live trades and metrics meet primary success criteria.
