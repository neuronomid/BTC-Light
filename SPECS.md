# Technical Specifications
## Statistical-LLM Hybrid Crypto Futures Trading System

**Version:** 1.0
**Date:** April 2026

---

## 1. System Architecture

### 1.1 Component Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA INGESTION LAYER                        │
│  Binance WS │ News APIs │ On-chain │ Macro feeds │ Social     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                ┌──────────▼──────────┐
                │  TimescaleDB        │  (time-series storage)
                └──────────┬──────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ STATISTICAL   │  │  AGENT LAYER  │  │ RULES ENGINE  │
│   ENGINE      │  │   (Python)    │  │    (Rust)     │
│   (Python)    │  │  4 LLM agents │  │  Execution    │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                ┌─────────────────────┐
                │   REDIS             │  (shared state)
                │   pub/sub + KV      │
                └─────────────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Binance Futures API │
                └─────────────────────┘
```

### 1.2 Language Choices

- **Rust** for the Rules Engine: memory safety matters when bugs cost money, tokio async runtime handles WebSocket + REST elegantly, predictable latency for stop-loss enforcement.
- **Python** for the Statistical Engine: the scientific Python ecosystem (statsmodels, arch, hmmlearn, ruptures, scipy) is unmatched. Rewriting these in Rust would take years and add bugs.
- **Python** for the Agent Layer: Anthropic SDK is Python-native, orchestration latency doesn't matter at 4H cadence.
- **Redis** for shared state: low-latency KV + pub/sub, battle-tested, simple to reason about.
- **TimescaleDB** for time-series: PostgreSQL compatibility, mature, handles both recent-hot and long-cold data well.

---

## 2. Statistical Analysis Engine

This is the most important addition to the system. It runs as a Python service with numerical heavy lifting. Every module outputs structured JSON to Redis that both the Rules Engine and LLM agents consume.

### 2.1 Regime Classification Module

**Concepts used:**

**Hidden Markov Model (HMM)** — a statistical model where the system is assumed to be in one of several hidden states, and only observable variables (returns, volume, volatility) are visible. The HMM estimates which hidden state the market is currently in and the probability of transitioning between states.

**Baum-Welch algorithm** — used to fit HMM parameters from historical data (transition probabilities, emission distributions).

**Viterbi algorithm** — used to decode the most likely current state given recent observations.

**Implementation:**
- 4 hidden states: `BULL_TREND`, `BEAR_TREND`, `HIGH_VOL_RANGE`, `LOW_VOL_RANGE`
- Observable features: log returns, realized volatility, volume z-score, price vs. 20-period moving average
- Training window: rolling 1000 candles (roughly 6 months of 4H data)
- Retraining: weekly, Sunday midnight UTC
- Library: `hmmlearn` with Gaussian emission distributions

**Outputs:**
```json
{
  "current_state": "BULL_TREND",
  "state_probabilities": {"BULL_TREND": 0.72, "BEAR_TREND": 0.05, "HIGH_VOL_RANGE": 0.18, "LOW_VOL_RANGE": 0.05},
  "expected_duration_candles": 8.2,
  "transition_probabilities": {"BULL_TREND_to_BEAR_TREND": 0.03, ...},
  "state_confidence": 0.72
}
```

**Why it matters:** Gives the system a mathematical basis for "what kind of market are we in right now" rather than relying on heuristics.

---

### 2.2 Trend Strength Module

**Concepts used:**

**Hurst Exponent (H)** — measures the degree of long-term memory in a time series.
- H > 0.55: trending (persistence, trends continue)
- H < 0.45: mean-reverting (anti-persistence)
- 0.45 ≤ H ≤ 0.55: random walk (no exploitable structure)

**Rescaled Range (R/S) Analysis** — the classical method for estimating Hurst. More robust: Detrended Fluctuation Analysis (DFA).

**Augmented Dickey-Fuller (ADF) Test** — tests for unit root (non-stationarity). A stationary series is mean-reverting; a non-stationary series is trending or random walk.

**Directional Movement Index (DMI) / ADX** — classical trend strength indicator, used alongside statistical measures for cross-validation.

**Implementation:**
- Hurst calculated on rolling 100-candle and 500-candle windows using DFA method
- ADF test with 5% significance threshold
- ADX with 14-period window
- Library: `nolds` for Hurst/DFA, `statsmodels` for ADF

**Outputs:**
```json
{
  "hurst_100": 0.62,
  "hurst_500": 0.58,
  "trend_classification": "TRENDING",
  "adf_statistic": -1.23,
  "adf_p_value": 0.65,
  "is_stationary": false,
  "adx": 32.4,
  "trend_strength_score": 0.71
}
```

**Why it matters:** Directly answers "should I trade trend-following or mean-reversion right now?" Trend-following strategies should only fire when H > 0.55 and ADX > 25. Mean-reversion only when H < 0.45 and ADF rejects unit root.

---

### 2.3 Volatility Forecasting Module

**Concepts used:**

**GARCH(1,1)** — Generalized Autoregressive Conditional Heteroskedasticity. Models volatility as a function of past squared returns and past volatility. Captures volatility clustering — the empirical fact that high-vol periods cluster together.

**EGARCH** — Exponential GARCH, captures leverage effect (volatility responds asymmetrically to positive vs. negative returns). Important for crypto where crashes are more volatile than rallies.

**Realized Volatility** — sum of squared high-frequency returns, used as "true" volatility benchmark.

**Implementation:**
- GARCH(1,1) for 4H forward volatility forecast
- EGARCH(1,1) as cross-check and for asymmetric risk
- Realized volatility over 1D, 7D, 30D windows
- Volatility percentile vs. 90-day distribution
- Library: `arch` (Kevin Sheppard's library)
- Retraining: daily

**Outputs:**
```json
{
  "garch_forecast_4h": 0.023,
  "egarch_forecast_4h": 0.025,
  "realized_vol_1d": 0.031,
  "realized_vol_7d": 0.028,
  "realized_vol_30d": 0.034,
  "vol_percentile_90d": 0.68,
  "vol_regime": "NORMAL",
  "leverage_effect_active": true
}
```

**Why it matters:** Stop-loss distances and position sizes must adapt to current volatility. A 2% stop in low-vol regime is appropriate; the same stop in high-vol regime is noise. GARCH gives you forward-looking vol, not just backward-looking ATR.

---

### 2.4 Change Point Detection Module

**Concepts used:**

**Bayesian Online Change Point Detection (BOCPD)** — computes the posterior probability at each time step that a change point just occurred. Uses hazard function and predictive likelihood to update beliefs online.

**CUSUM (Cumulative Sum Control Chart)** — classical statistical process control method for detecting shifts in the mean of a series.

**Pettitt Test** — non-parametric test for a single change point in location.

**Implementation:**
- BOCPD with hazard rate 1/200 (expected change point every 200 candles)
- CUSUM with threshold calibrated to 95th percentile of historical CUSUM values
- Monitored on returns, volatility, and correlation to SPX
- Library: `ruptures`, custom BOCPD implementation

**Outputs:**
```json
{
  "bocpd_change_probability": 0.18,
  "last_change_point_candles_ago": 47,
  "cusum_breached": false,
  "regime_stability_score": 0.82,
  "recommend_halt": false
}
```

**Why it matters:** When the market is transitioning between regimes, all historically-calibrated models are temporarily unreliable. The system should halt or drastically reduce size during high change-point probability periods.

---

### 2.5 Tail Risk Module

**Concepts used:**

**Extreme Value Theory (EVT) — Peaks Over Threshold (POT)** — models the distribution of extreme losses using Generalized Pareto Distribution. Gives reliable tail estimates even when you don't have many extreme observations.

**Conditional Value at Risk (CVaR / Expected Shortfall)** — the expected loss given that loss exceeds VaR. Much better than VaR because it captures the severity of tail losses, not just their frequency.

**Value at Risk (VaR)** — included for compatibility but always report CVaR alongside.

**Implementation:**
- POT method with 95th percentile threshold
- CVaR at 95% and 99% confidence levels
- Rolling 500-candle window for estimation
- Jump detection via Lee-Mykland test
- Library: `scipy.stats` for fitting Pareto, custom EVT code

**Outputs:**
```json
{
  "var_95_4h": 0.031,
  "cvar_95_4h": 0.047,
  "var_99_4h": 0.058,
  "cvar_99_4h": 0.089,
  "tail_index": 2.4,
  "tail_risk_level": "ELEVATED",
  "recent_jumps_detected": 2
}
```

**Why it matters:** Position sizing that ignores tail risk underestimates drawdown probability. Crypto has fat tails — normal distribution assumptions blow up accounts. CVaR-aware sizing is mathematically correct.

---

### 2.6 Probability Module

**Concepts used:**

**Monte Carlo Simulation** — simulate thousands of possible price paths using GARCH-forecasted volatility and HMM-regime-conditional drift. Count how many paths hit take-profit before stop-loss.

**Bayesian Inference** — combine multiple signals (statistical regime, trend strength, news sentiment) into a posterior probability of favorable outcome. Prior from historical base rates, likelihood from current signal strengths.

**Kelly Criterion (Fractional)** — optimal position size given edge and odds. Full Kelly is aggressive; fractional Kelly (0.25-0.5x) accounts for parameter uncertainty.

**Formula:** `f* = (p*b - q) / b` where `p` = win probability, `q` = 1-p, `b` = win/loss ratio. Fractional Kelly multiplies by 0.25-0.5.

**Implementation:**
- Monte Carlo: 10,000 paths per trade evaluation, using GARCH vol + HMM regime drift
- Bayesian update combining: HMM regime probability, Hurst exponent signal, news sentiment, change point probability
- Kelly sizing with 0.25 fractional multiplier
- Library: numpy for Monte Carlo, custom Bayesian code

**Outputs:**
```json
{
  "prob_hit_tp_before_sl": 0.56,
  "expected_value_per_trade": 0.011,
  "bayesian_posterior_long": 0.62,
  "bayesian_posterior_short": 0.28,
  "kelly_fraction": 0.18,
  "recommended_size_pct_equity": 0.012
}
```

**Why it matters:** This is where the system's edge is actually quantified. If `prob_hit_tp_before_sl < 0.5` after accounting for the risk-reward ratio, the expected value is negative and the trade should be skipped. Kelly gives theoretically optimal sizing.

---

### 2.7 Market Efficiency Module

**Concepts used:**

**Shannon Entropy** — information-theoretic measure of unpredictability. Higher entropy = more random = less exploitable.

**Approximate Entropy (ApEn)** and **Sample Entropy (SampEn)** — measure the regularity and complexity of time series. Low values indicate predictable patterns.

**Variance Ratio Test (Lo-MacKinlay)** — tests the random walk hypothesis. Rejection indicates exploitable autocorrelation.

**Implementation:**
- Shannon entropy on discretized returns (binned into deciles)
- SampEn with embedding dimension m=2, tolerance r=0.2*std
- Variance ratio test at 2, 4, 8, 16 lags
- Library: `EntropyHub` or custom

**Outputs:**
```json
{
  "shannon_entropy": 3.12,
  "sample_entropy": 1.45,
  "variance_ratio_2": 0.92,
  "variance_ratio_p_value": 0.04,
  "random_walk_rejected": true,
  "efficiency_score": 0.34,
  "predictability_level": "MODERATE"
}
```

**Why it matters:** When markets are highly efficient (high entropy, variance ratio near 1), no system has edge. During those periods the system should reduce activity or halt. When efficiency is low and tests reject random walk, there's something exploitable.

---

### 2.8 Correlation and Dependence Module

**Concepts used:**

**Rolling Pearson Correlation** — standard linear correlation over rolling windows.

**Copula-Based Tail Dependence** — measures whether extreme moves in one asset coincide with extreme moves in another, even when overall correlation is low. Gaussian copulas miss this; t-copulas and Clayton copulas capture it.

**Dynamic Conditional Correlation (DCC-GARCH)** — models time-varying correlations using GARCH framework.

**Implementation:**
- Rolling 30-day and 90-day correlation with SPX, DXY, Gold, ETH
- t-copula tail dependence coefficients
- DCC-GARCH for BTC-SPX pair (primary risk-on/risk-off indicator)
- Library: `copulas`, `statsmodels`

**Outputs:**
```json
{
  "corr_btc_spx_30d": 0.42,
  "corr_btc_dxy_30d": -0.28,
  "corr_btc_gold_30d": 0.15,
  "corr_btc_eth_30d": 0.88,
  "tail_dependence_btc_spx": 0.34,
  "dcc_garch_btc_spx": 0.51,
  "risk_on_off_regime": "RISK_ON"
}
```

**Why it matters:** BTC doesn't trade in isolation. When correlation to SPX spikes, BTC is driven by macro rather than crypto-specific factors — LLM should weight macro news more heavily. High tail dependence means a macro shock will hit BTC even if crypto fundamentals are unchanged.

---

## 3. LLM Agent Layer

Four agents, each with structured input schemas and structured output schemas.

### 3.1 Market Context Agent

- **Model:** Claude Opus 4.7
- **Cadence:** Every 4H at candle close
- **Inputs:** All Statistical Engine outputs, multi-timeframe price data (4H, 1D, 1W), key level analysis, order book snapshot, funding rate, open interest changes
- **Task:** Interpret statistical outputs in market context, identify narrative, flag inconsistencies between statistical signals

**Output schema:**
```json
{
  "regime_interpretation": "string",
  "narrative": "string",
  "key_levels": {"support": [...], "resistance": [...]},
  "statistical_coherence_score": 0.0-1.0,
  "notable_divergences": ["string"],
  "context_summary": "string"
}
```

### 3.2 News and Sentiment Agent

- **Model:** Claude Sonnet 4.6
- **Cadence:** Every 30 minutes + triggered on breaking news
- **Inputs:** Recent crypto news headlines/bodies, macro economic calendar, social sentiment metrics, regulatory developments
- **Task:** Assess directional implication of news flow, flag black swan risks, quantify sentiment

**Output schema:**
```json
{
  "news_sentiment_score": -1.0 to 1.0,
  "directional_bias": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0-1.0,
  "key_events": [{"headline": "...", "impact": "..."}],
  "black_swan_risk": "LOW|MEDIUM|HIGH",
  "macro_events_next_24h": [...]
}
```

### 3.3 Trade Decision Agent

- **Model:** Claude Opus 4.7
- **Cadence:** Every 4H at candle close, after Market Context and News agents have updated
- **Inputs:** All Statistical Engine outputs, Market Context Agent output, News Agent output, recent trade history and outcomes
- **Task:** Make final directional call with conviction score, justify decision, specify risk parameters

**Output schema:**
```json
{
  "action": "LONG|SHORT|NO_TRADE",
  "conviction": 0-100,
  "entry_zone": {"low": 0.0, "high": 0.0},
  "stop_loss_pct": 0.0,
  "take_profit_pct": 0.0,
  "invalidation_conditions": ["string"],
  "size_multiplier": 0.0-1.5,
  "reasoning": "string",
  "statistical_signals_weighted": {"hmm": 0.3, "hurst": 0.2, ...}
}
```

### 3.4 Risk Monitor Agent

- **Model:** Claude Sonnet 4.6
- **Cadence:** Every 15 minutes while position open
- **Inputs:** Current position status, live price action, updated Statistical Engine outputs, breaking news flags
- **Task:** Monitor for regime shifts or thesis invalidation, trigger early exit if conditions deteriorate

**Output schema:**
```json
{
  "thesis_still_valid": true/false,
  "regime_shift_detected": true/false,
  "recommend_action": "HOLD|EXIT_MARKET|TIGHTEN_STOP|TAKE_PARTIAL",
  "urgency": "LOW|MEDIUM|HIGH",
  "reasoning": "string"
}
```

---

## 4. Rules Engine (Rust)

### 4.1 Core Responsibilities
- WebSocket connection to Binance Futures (real-time price, depth, trades)
- REST API for order placement and account queries
- Position state management
- Hard safety rules enforcement
- OCO (One-Cancels-Other) stop-loss and take-profit order placement on exchange
- Logging to TimescaleDB

### 4.2 Hard Safety Rules (Non-Overridable)

```rust
// Executed regardless of agent decisions
const MAX_RISK_PER_TRADE: f64 = 0.02;        // 2% account equity max
const MAX_DAILY_LOSS: f64 = 0.05;            // Halt at 5% daily loss
const MAX_WEEKLY_LOSS: f64 = 0.10;           // Halt at 10% weekly loss
const MAX_OPEN_POSITIONS: u8 = 1;            // MVP: one at a time
const MAX_POSITION_DURATION_HOURS: u8 = 24;  // Force close after 24h
const MIN_TIME_BETWEEN_TRADES_HOURS: u8 = 4; // One trade per candle max
const MAX_LEVERAGE: f64 = 5.0;               // Conservative
const MIN_CONVICTION_TO_TRADE: u8 = 70;      // From Trade Decision Agent
const MIN_EV_TO_TRADE: f64 = 0.005;          // From Monte Carlo
```

### 4.3 Position Sizing Calculation

```
size = account_equity 
     × min(kelly_fraction * 0.25, MAX_RISK_PER_TRADE)
     × agent_size_multiplier
     × regime_stability_score
     / abs(entry_price - stop_loss_price)
     × leverage
```

### 4.4 Order Flow

1. Trade Decision Agent outputs conviction ≥ 70 and action ≠ NO_TRADE
2. Rules Engine validates: hard rules pass, statistical filters pass (EV > threshold, regime stable, volatility in acceptable range, market efficiency below threshold)
3. Calculate position size using formula above
4. Place limit entry order at agent's specified entry zone
5. Once filled, immediately place OCO stop-loss + take-profit
6. Log all decisions and parameters to TimescaleDB
7. Publish position update to Redis for Risk Monitor Agent

### 4.5 Exit Triggers (Any One Fires → Exit)

- Stop-loss hit (exchange-enforced OCO)
- Take-profit hit (exchange-enforced OCO)
- Risk Monitor Agent signals EXIT_MARKET with HIGH urgency
- Max position duration reached
- Daily or weekly loss circuit breaker triggered

---

## 5. Data Infrastructure

### 5.1 Real-Time Feeds
- **Binance Futures WebSocket:** `bookTicker`, `markPrice`, `aggTrade`, `depth20`, `kline_4h`
- **Funding rate:** polled every 5 minutes via REST
- **Open interest:** polled every 5 minutes
- **Liquidations:** `!forceOrder@arr` stream

### 5.2 External Data
- **News:** CryptoPanic API (headlines + sentiment), NewsAPI for macro
- **Social:** Twitter API filtered to curated list of crypto analysts, Reddit r/CryptoCurrency sentiment via Pushshift-equivalent
- **On-chain:** Glassnode API (if budget allows) for exchange flows, active addresses, funding flows
- **Macro:** FRED API for DXY, SPX futures, treasury yields

### 5.3 Storage
- **TimescaleDB:** all time-series data, hypertables by time
- **Redis:** shared state (current agent outputs, statistical engine outputs, position state)
- **PostgreSQL:** trade logs, agent reasoning logs, performance metrics

---

## 6. Validation and Testing Plan

### 6.1 Statistical Engine Validation
- Backtest each statistical module on 3 years of BTC 4H data
- Measure information coefficient (IC) between each signal and forward returns
- Walk-forward analysis to check for overfitting
- Out-of-sample performance must match in-sample within 20%

### 6.2 Agent Calibration
- Run Trade Decision Agent on 200 historical setups with known outcomes
- Measure calibration: trades at 70% conviction should win ~70% of the time
- Identify systematic biases (always bullish, always bearish, bad in certain regimes)
- Iterate prompts based on failures

### 6.3 End-to-End Backtest
- Event-driven backtest replaying 2 years of data chronologically
- Realistic slippage (0.05%) and fees (0.04% per side on Binance)
- No look-ahead bias (strict temporal ordering)
- Target metrics: Sharpe > 1.0, max drawdown < 20%, profit factor > 1.5

### 6.4 Paper Trading
- Minimum 8 weeks live paper trading
- All systems running production mode, but orders simulated
- Track divergence between backtest predictions and paper results
- Must meet primary metrics in paper before going live

### 6.5 Live Trading Gradual Rollout
- Weeks 1-4: 0.1% risk per trade (10x smaller than target)
- Weeks 5-8: 0.5% risk per trade
- Week 9+: up to 2% risk per trade only if all metrics holding

---

## 7. Statistical Concepts Summary Table

| Concept | Module | What It Does | Why It's Used |
|---------|--------|--------------|---------------|
| Hidden Markov Model | Regime | Identifies hidden market state from observables | Mathematical regime classification |
| Hurst Exponent (DFA) | Trend | Measures trend persistence vs. mean-reversion | Answers "trend-follow or mean-revert?" |
| ADF Test | Trend | Tests for stationarity | Validates mean-reversion assumptions |
| GARCH / EGARCH | Volatility | Forecasts forward volatility | Dynamic stop-loss sizing |
| Bayesian Online Change Point | Change Detection | Real-time regime transition detection | Halts trading during transitions |
| CUSUM | Change Detection | Detects mean shifts | Cross-check for BOCPD |
| Extreme Value Theory (POT) | Tail Risk | Models tail loss distribution | Accurate fat-tail risk estimation |
| CVaR / Expected Shortfall | Tail Risk | Expected loss beyond VaR | Correct risk quantification |
| Monte Carlo Simulation | Probability | Estimates P(TP before SL) | Trade expected value calculation |
| Bayesian Inference | Probability | Combines signals into posterior | Multi-signal integration |
| Kelly Criterion (fractional) | Probability | Optimal position sizing | Mathematically correct sizing |
| Shannon Entropy | Efficiency | Measures randomness | Detects unexploitable periods |
| Sample Entropy | Efficiency | Measures complexity/regularity | Cross-check for predictability |
| Variance Ratio Test | Efficiency | Tests random walk hypothesis | Validates exploitable structure exists |
| t-Copula Tail Dependence | Correlation | Tail co-movement with other assets | Macro contagion risk |
| DCC-GARCH | Correlation | Time-varying correlation | Dynamic risk-on/risk-off detection |

---

## 8. Known Limitations and Honest Caveats

1. **Non-stationarity**: Crypto markets change structurally. Models calibrated on 2022-2024 data may fail in 2026+ regimes. Mitigation: rolling recalibration, change point halts, parameter stability monitoring. But cannot be fully solved.

2. **Overfitting risk**: With this many statistical modules, there's real risk of fitting noise. Mitigation: strict out-of-sample validation, walk-forward testing, preferring simpler models when they perform comparably.

3. **LLM evaluation difficulty**: Hard to know if LLM reasoning is adding value or just adding plausible-sounding noise. Mitigation: A/B test with and without LLM layer, measure IC of agent conviction vs. outcomes.

4. **Tail events**: EVT provides better tail estimates than normal distribution but still underestimates true black swan magnitude. Mitigation: position sizing accounts for 3-sigma gap risk, hard drawdown circuit breakers.

5. **Execution assumptions**: Backtest assumes fills at modeled prices. Live slippage in high-vol periods can be 5-10x modeled. Mitigation: use limit orders, avoid trading during news events, realistic slippage in backtests.

6. **Competitive landscape**: Institutional quants use similar or better methods with faster infrastructure. This system targets edges they ignore (too small for them, too slow to scale for their operations), not direct competition.

7. **Single asset concentration**: BTC-only means correlation risk. Mitigation: future version adds ETH, SOL with portfolio-level risk management.

8. **Cost of running**: LLM API calls, market data subscriptions, compute — realistic monthly operating cost $200-500. Profitability must clear this hurdle plus fees.
