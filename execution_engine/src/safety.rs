use crate::config::*;
use crate::models::{SafetyCheck, TradeDecision};
use serde_json::Value;

/// Immutable safety engine evaluating hard rules.
pub struct SafetyEngine {
    pub daily_pnl: f64,
    pub weekly_pnl: f64,
    pub open_positions: u32,
    pub last_trade_time: Option<chrono::DateTime<chrono::Utc>>,
}

impl SafetyEngine {
    pub fn new() -> Self {
        Self {
            daily_pnl: 0.0,
            weekly_pnl: 0.0,
            open_positions: 0,
            last_trade_time: None,
        }
    }

    pub fn update_risk(&mut self, daily: f64, weekly: f64, positions: u32) {
        self.daily_pnl = daily;
        self.weekly_pnl = weekly;
        self.open_positions = positions;
    }

    /// Run all safety checks before opening a new position.
    pub fn check_all(
        &self,
        decision: &TradeDecision,
        stats: &Value,
        equity: f64,
    ) -> SafetyCheck {
        if decision.action == crate::models::Action::NO_TRADE {
            return SafetyCheck::pass("No trade requested.");
        }
        if decision.conviction < MIN_CONVICTION_TO_TRADE {
            return SafetyCheck::fail(format!(
                "Conviction {} < {}",
                decision.conviction, MIN_CONVICTION_TO_TRADE
            ));
        }
        // Check statistical EV from snapshot
        if let Some(prob) = stats.get("probability") {
            let ev = prob.get("expected_value_per_trade").and_then(|v| v.as_f64()).unwrap_or(0.0);
            if ev < MIN_EV_TO_TRADE {
                return SafetyCheck::fail(format!(
                    "EV {:.6} < {}",
                    ev, MIN_EV_TO_TRADE
                ));
            }
        }
        // Change point halt
        if let Some(cp) = stats.get("change_point") {
            if cp.get("recommend_halt").and_then(|v| v.as_bool()).unwrap_or(false) {
                return SafetyCheck::fail("Change point detection recommends halt.");
            }
        }
        if self.open_positions >= MAX_OPEN_POSITIONS {
            return SafetyCheck::fail(format!(
                "Max open positions {} reached.",
                MAX_OPEN_POSITIONS
            ));
        }
        if self.daily_pnl < -MAX_DAILY_LOSS * equity {
            return SafetyCheck::fail(format!(
                "Daily loss circuit breaker triggered: {:.2}",
                self.daily_pnl
            ));
        }
        if self.weekly_pnl < -MAX_WEEKLY_LOSS * equity {
            return SafetyCheck::fail(format!(
                "Weekly loss circuit breaker triggered: {:.2}",
                self.weekly_pnl
            ));
        }
        // Min time between trades check
        if let Some(last) = self.last_trade_time {
            let elapsed = chrono::Utc::now().signed_duration_since(last).num_hours();
            if elapsed < MIN_TIME_BETWEEN_TRADES_HOURS as i64 {
                return SafetyCheck::fail(format!(
                    "Min time between trades: {}h, elapsed: {}h",
                    MIN_TIME_BETWEEN_TRADES_HOURS, elapsed
                ));
            }
        }
        SafetyCheck::pass("All safety checks passed.")
    }

    /// Calculate position size using fractional Kelly and hard caps.
    pub fn calculate_size(
        &self,
        decision: &TradeDecision,
        stats: &Value,
        equity: f64,
        entry_price: f64,
        stop_loss_price: f64,
    ) -> f64 {
        let kelly_frac = stats
            .get("probability")
            .and_then(|p| p.get("kelly_fraction"))
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
        let base = equity * (kelly_frac * 0.25).min(MAX_RISK_PER_TRADE) * decision.size_multiplier;

        let regime_stability = stats
            .get("change_point")
            .and_then(|cp| cp.get("regime_stability_score"))
            .and_then(|v| v.as_f64())
            .unwrap_or(1.0);

        let mut size = base * regime_stability;

        if entry_price > 0.0 && stop_loss_price > 0.0 {
            let sl_dist = (entry_price - stop_loss_price).abs();
            if sl_dist > 0.0 {
                size = size / sl_dist; // notional ~ risk / sl distance
            }
        }
        let cap = equity * MAX_RISK_PER_TRADE;
        size = size.min(cap);
        (size * 1e6).round() / 1e6
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{Action, TradeDecision};
    use chrono::{Duration, Utc};
    use serde_json::json;

    fn decision(action: Action, conviction: u8) -> TradeDecision {
        TradeDecision {
            action,
            conviction,
            stop_loss_pct: 0.02,
            take_profit_pct: 0.04,
            size_multiplier: 1.0,
            reasoning: "test".to_string(),
            entry_zone: None,
        }
    }

    fn passing_stats() -> serde_json::Value {
        json!({
            "probability": {
                "expected_value_per_trade": 0.02,
                "kelly_fraction": 0.4
            },
            "change_point": {
                "recommend_halt": false,
                "regime_stability_score": 1.0
            }
        })
    }

    #[test]
    fn no_trade_passes_without_other_checks() {
        let result = SafetyEngine::new().check_all(&decision(Action::NO_TRADE, 0), &json!({}), 10_000.0);

        assert!(result.passed);
        assert_eq!(result.reason, "No trade requested.");
    }

    #[test]
    fn low_conviction_fails() {
        let result = SafetyEngine::new().check_all(&decision(Action::LONG, 20), &passing_stats(), 10_000.0);

        assert!(!result.passed);
        assert!(result.reason.contains("Conviction"));
    }

    #[test]
    fn low_expected_value_fails() {
        let stats = json!({
            "probability": {"expected_value_per_trade": 0.0},
            "change_point": {"recommend_halt": false}
        });

        let result = SafetyEngine::new().check_all(&decision(Action::LONG, 80), &stats, 10_000.0);

        assert!(!result.passed);
        assert!(result.reason.contains("EV"));
    }

    #[test]
    fn change_point_halt_fails() {
        let stats = json!({
            "probability": {"expected_value_per_trade": 0.02},
            "change_point": {"recommend_halt": true}
        });

        let result = SafetyEngine::new().check_all(&decision(Action::LONG, 80), &stats, 10_000.0);

        assert!(!result.passed);
        assert!(result.reason.contains("Change point"));
    }

    #[test]
    fn open_position_limit_and_loss_breakers_fail() {
        let mut safety = SafetyEngine::new();
        safety.open_positions = MAX_OPEN_POSITIONS;
        let max_open = safety.check_all(&decision(Action::LONG, 80), &passing_stats(), 10_000.0);

        safety.open_positions = 0;
        safety.daily_pnl = -501.0;
        let daily = safety.check_all(&decision(Action::LONG, 80), &passing_stats(), 10_000.0);

        safety.daily_pnl = 0.0;
        safety.weekly_pnl = -1001.0;
        let weekly = safety.check_all(&decision(Action::LONG, 80), &passing_stats(), 10_000.0);

        assert!(!max_open.passed);
        assert!(max_open.reason.contains("Max open positions"));
        assert!(!daily.passed);
        assert!(daily.reason.contains("Daily loss"));
        assert!(!weekly.passed);
        assert!(weekly.reason.contains("Weekly loss"));
    }

    #[test]
    fn min_time_between_trades_fails_when_recent_trade_exists() {
        let mut safety = SafetyEngine::new();
        safety.last_trade_time = Some(Utc::now() - Duration::hours(1));

        let result = safety.check_all(&decision(Action::LONG, 80), &passing_stats(), 10_000.0);

        assert!(!result.passed);
        assert!(result.reason.contains("Min time between trades"));
    }

    #[test]
    fn all_checks_pass_for_valid_trade() {
        let result = SafetyEngine::new().check_all(&decision(Action::LONG, 80), &passing_stats(), 10_000.0);

        assert!(result.passed);
        assert_eq!(result.reason, "All safety checks passed.");
    }

    #[test]
    fn calculate_size_uses_fractional_kelly_multiplier_and_stability_without_prices() {
        let stats = json!({
            "probability": {"kelly_fraction": 0.04},
            "change_point": {"regime_stability_score": 0.5}
        });
        let mut dec = decision(Action::LONG, 80);
        dec.size_multiplier = 0.5;

        let size = SafetyEngine::new().calculate_size(&dec, &stats, 10_000.0, 0.0, 0.0);

        assert!((size - 25.0).abs() < 1e-9);
    }

    #[test]
    fn calculate_size_converts_risk_budget_to_units_with_stop_distance_and_cap() {
        let stats = json!({
            "probability": {"kelly_fraction": 0.4},
            "change_point": {"regime_stability_score": 1.0}
        });

        let size = SafetyEngine::new().calculate_size(
            &decision(Action::LONG, 80),
            &stats,
            10_000.0,
            100.0,
            98.0,
        );

        assert!((size - 100.0).abs() < 1e-9);
    }
}
