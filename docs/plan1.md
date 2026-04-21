# Plan 1: Multi-Symbol And Cross-Asset Expansion

Date: 2026-04-21
Status: Brainstorming only. Do not execute or implement without explicit direction.

## Purpose

The current system is built around BTC perpetual futures on the 4H timeframe. A 4H cadence can produce long waiting periods between high-conviction entries. The goal of this plan is to increase the number of qualified opportunities by scanning more instruments while preserving the project's philosophy:

- Statistics measure market state.
- LLM agents interpret context.
- Rules enforce non-overridable safety.
- More symbols should create more qualified setups, not lower the quality bar.

## Architectural Direction

The current system should remain a crypto futures trading system. It is tuned around crypto market structure, crypto perpetual contracts, 24/7 trading, funding, open interest, liquidations, and BTC-led crypto beta.

Future EURUSD, XAU, and SPY systems should be separate systems inspired by this architecture, not extra symbols bolted onto the current crypto stack. They can reuse the same high-level philosophy, but each should have its own tuned data layer, statistical assumptions, agent prompts, risk controls, execution adapter, validation process, and performance tracking.

This separation keeps the current crypto system coherent while allowing non-crypto systems to be designed correctly for their own market structure.

## Core Constraint

The current MVP assumes one open position at a time. After implementing this plan, max open positions would no longer remain 1, but that change must only happen together with portfolio-level risk management.

The system should not simply open every symbol that triggers. It should rank candidates, account for correlation clusters, and enforce aggregate risk limits.

## Recommended Crypto Expansion

### First Expansion

Add:

- `ETHUSDT`
- `SOLUSDT`

Yahoo-style historical equivalents:

- `ETH-USD`
- `SOL-USD`

Rationale:

- Best fit with the existing BTC architecture.
- High liquidity and deep historical data.
- Strong enough volatility to create 4H opportunities.
- Enough narrative/context coverage for the LLM layer.
- Already aligned with the SPECS note that future expansion should add ETH and SOL with portfolio-level risk management.

### Second Expansion

Add after validation:

- `XRPUSDT`
- `BNBUSDT`
- `DOGEUSDT`

Yahoo-style historical equivalents:

- `XRP-USD`
- `BNB-USD`
- `DOGE-USD`

Rationale:

- More opportunity frequency.
- Still liquid enough for paper trading and small-size futures testing.
- More idiosyncratic behavior than BTC/ETH, but still heavily tied to broad crypto beta.

### Later Watchlist

Consider only after the first two phases are validated:

- `LINKUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `SUIUSDT`

Yahoo-style historical equivalents:

- `LINK-USD`
- `AVAX-USD`
- `ADA-USD`
- `SUI-USD`

These are candidates, not automatic additions. They should pass liquidity, spread, funding, history-depth, and signal-quality checks before becoming tradable symbols.

## Symbols To Avoid Early

Avoid starting with:

- Newly listed coins.
- Low open-interest altcoins.
- Pure hype/memecoin contracts outside the highly liquid majors.
- Symbols with unstable exchange support.
- Symbols where funding, spread, or slippage can dominate the modeled edge.

The statistical modules need enough stable history for HMM, GARCH, Hurst, EVT, Monte Carlo, and entropy tests. Adding many noisy symbols increases the chance of false positives.

## Portfolio-Level Risk Requirements

Before allowing multiple simultaneous positions, the system needs portfolio-level controls:

- Aggregate account risk cap across all open positions.
- Per-symbol risk cap.
- Per-cluster risk cap, for example crypto beta, gold, equity index, FX.
- Correlation-aware signal ranking.
- Tail-dependence checks between open positions.
- Daily and weekly drawdown circuit breakers across the whole portfolio.
- Rules for conflicting signals, for example BTC long and ETH short.
- Rules for duplicate exposure, for example BTC long, ETH long, and SOL long all firing at once.

The default behavior should be:

1. Scan all enabled symbols.
2. Score all candidates.
3. Reject candidates below conviction, EV, stability, efficiency, and tail-risk thresholds.
4. Rank remaining candidates by risk-adjusted expected value.
5. Open only the best candidates allowed by portfolio risk.

## Recommended Staging

### Phase 1: Crypto Core 3

Tradable symbols:

- `BTCUSDT`
- `ETHUSDT`
- `SOLUSDT`

Goal:

- Increase trigger frequency while staying close to the original system design.
- Keep max simultaneous exposure conservative.

### Phase 2: Crypto Core 6

Add:

- `XRPUSDT`
- `BNBUSDT`
- `DOGEUSDT`

Goal:

- Improve opportunity frequency.
- Test whether the statistical engine generalizes beyond BTC/ETH/SOL.

### Phase 3: Cross-Asset Observation Mode

Observe but do not trade inside the crypto execution stack:

- Gold proxy, such as `XAUUSDT` or external `XAUUSD`.
- Equity index proxy, preferably `SPY`/S&P 500 exposure before Dow-specific exposure.
- FX proxy, likely `EURUSD`. The user wrote `EUUSD`, but the standard pair is `EURUSD`.

Goal:

- Learn whether cross-asset data improves crypto regime context and risk filtering.
- Use these symbols as macro context only, not as tradable instruments in the crypto system.
- Avoid mixing asset classes before session, pricing, venue, and risk differences are modeled.

### Phase 4: Separate Non-Crypto Systems

Build later as separate systems, not as an extension of this crypto system:

- EURUSD system.
- XAU system.
- SPY or broader equity-index system.

Goal:

- Reuse the architecture pattern: statistical engine, LLM interpretation, hard rules, paper validation.
- Tune each stack to its own asset class.
- Keep performance, risk, and execution separate from the crypto futures system.

## Cross-Asset Diversification Notes

### Gold: XAUUSD / XAUUSDT

Gold is the best first non-crypto candidate for a future separate system.

Pros:

- Often behaves differently from crypto beta.
- Useful macro and risk-off signal.
- Good fit for regime and volatility analysis.
- Can improve overall trading diversification if execution venue is reliable.

Risks:

- If traded as a crypto-exchange TradFi perp, the symbol may be `XAUUSDT`, not `XAUUSD`.
- If traded through a broker or data vendor, execution and data plumbing may be different from Binance crypto perps.
- Off-hours pricing rules may differ from normal crypto markets.

Recommendation:

- Add gold first as an observation/context symbol for the crypto dashboard and research layer.
- Do not trade it through the current crypto system.
- Later, build a dedicated XAU system with its own contract specs, session model, spread/slippage assumptions, macro-event filters, and risk calibration.

### EURUSD

EURUSD can diversify the broader project, but it should be a separate future system.

Pros:

- Deep, liquid global market.
- Different drivers from BTC: central banks, rates, macro data, dollar regime.
- Useful as macro context even before being tradable.

Risks:

- Requires FX-specific data and likely a different execution venue.
- Session structure is different from crypto.
- Volatility is lower, so stop sizing and expected value thresholds may need different calibration.
- LLM context must understand macro calendars, central bank events, CPI, NFP, rate expectations, and DXY.

Recommendation:

- Use EURUSD first as a context feature for crypto macro interpretation.
- Do not trade it through the current crypto stack.
- Later, build a dedicated EURUSD system with FX-specific sessions, data, spreads, calendar filters, volatility thresholds, and execution/risk rules.

### SPY / Equity Index Exposure

Equity index exposure can help, but SPY/S&P 500 is a better default than Dow for this architecture.

Possible proxies:

- `SPY` ETF for S&P 500 exposure.
- `SPYUSDT` if using a crypto-exchange ETF-linked perpetual and if supported/liquid enough.
- `QQQ` or `QQQUSDT` if Nasdaq/high-beta technology exposure is more relevant.
- `DIA`, `YM`, or `US30` only if there is a specific reason to target Dow Jones exposure.

Pros:

- Helps detect risk-on/risk-off regimes.
- Can diversify the broader project beyond crypto.
- S&P/Nasdaq proxies may be more useful than Dow because BTC often behaves more like high-beta tech/liquidity risk than industrial Dow exposure.

Risks:

- Equity markets have exchange sessions, holidays, and overnight gaps.
- 24/7 synthetic perps can have special off-hours pricing behavior.
- Traditional index data and Binance-style perp data may not behave the same.
- A dedicated equity-index system needs session-aware gap handling before treating these like normal 4H signals.

Recommendation:

- Use SPY/S&P 500 first as a crypto context signal.
- Do not trade SPY through the current crypto stack.
- Later, build a dedicated SPY or equity-index system with market-hours awareness, gap logic, earnings/macro-event filters, and equity-specific risk calibration.
- Treat Dow as lower priority than SPY or QQQ unless the strategy specifically needs Dow exposure.

## Practical Recommendation

Near-term:

1. Keep this plan as brainstorming only.
2. Expand crypto first: BTC, ETH, SOL.
3. Add XRP, BNB, DOGE only after the first expansion is validated.
4. Add XAU, SPY, and EURUSD as context/observation signals only.
5. Keep the crypto execution system crypto-only.

Longer-term:

1. Build portfolio-level crypto risk before increasing max open positions inside the crypto system.
2. Design separate systems for XAU, EURUSD, and SPY rather than trading them through the crypto stack.
3. Give each future system its own paper validation, thresholds, risk model, and execution path.
4. Keep separate performance metrics by system and asset class.
5. Do not lower conviction or EV thresholds just to force more trades.

## Key Principle

More crypto symbols should increase the number of independent high-quality crypto opportunities. Non-crypto assets should inform context now and become separate fine-tuned systems later, rather than being mixed into a crypto stack that was not designed for their market structure.
