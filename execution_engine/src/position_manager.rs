use crate::config::*;
use crate::models::{AccountStatus, Action, ExitReason, Position, PositionStatus, TradeDecision};
use crate::safety::SafetyEngine;
use chrono::Utc;
use log::{info, warn};
use serde_json::Value;

pub struct PositionManager {
    pub equity: f64,
    pub starting_equity: f64,
    pub positions: Vec<Position>,
    pub closed_trades: Vec<Position>,
    pub daily_pnl: f64,
    pub weekly_pnl: f64,
    pub last_trade_time: Option<chrono::DateTime<chrono::Utc>>,
    pub safety: SafetyEngine,
    pub current_price: Option<f64>,
}

impl PositionManager {
    pub fn new(initial_equity: f64) -> Self {
        let mut safety = SafetyEngine::new();
        safety.update_risk(0.0, 0.0, 0);
        Self {
            equity: initial_equity,
            starting_equity: initial_equity,
            positions: vec![],
            closed_trades: vec![],
            daily_pnl: 0.0,
            weekly_pnl: 0.0,
            last_trade_time: None,
            safety,
            current_price: None,
        }
    }

    pub fn update_price(&mut self, price: f64) {
        self.current_price = Some(price);
        for pos in self.positions.iter_mut() {
            if pos.status == PositionStatus::OPEN {
                pos.update_pnl(price);
            }
        }
    }

    fn sync_safety(&mut self) {
        self.safety.update_risk(
            self.daily_pnl,
            self.weekly_pnl,
            self.positions.iter().filter(|p| p.status == PositionStatus::OPEN).count() as u32,
        );
    }

    /// Evaluate a trade decision and open a position if it passes safety.
    pub fn evaluate_decision(
        &mut self,
        snapshot: &Value,
        decision: &TradeDecision,
    ) -> Option<&Position> {
        if decision.action == Action::NO_TRADE {
            return None;
        }
        self.sync_safety();
        let check = self.safety.check_all(decision, snapshot, self.equity);
        if !check.passed {
            warn!("Safety check failed: {}", check.reason);
            return None;
        }
        let price = self.current_price?;
        let (sl, tp) = match decision.action {
            Action::LONG => {
                let sl_pct = decision.stop_loss_pct;
                let tp_pct = decision.take_profit_pct;
                (price * (1.0 - sl_pct), price * (1.0 + tp_pct))
            }
            Action::SHORT => {
                let sl_pct = decision.stop_loss_pct;
                let tp_pct = decision.take_profit_pct;
                (price * (1.0 + sl_pct), price * (1.0 - tp_pct))
            }
            _ => return None,
        };
        let size = self.safety.calculate_size(decision, snapshot, self.equity, price, sl);
        let pos = Position::new(
            snapshot.get("symbol").and_then(|v| v.as_str()).unwrap_or("BTC-USD"),
            decision.action.clone(),
            price,
            size,
            sl,
            tp,
            decision.conviction,
            decision.reasoning.clone(),
        );
        info!(
            "Opened {} | {:?} | Size: {:.6} | Entry: {:.2} | SL: {:.2} | TP: {:.2}",
            pos.trade_id, pos.action, pos.size, pos.entry_price, pos.stop_loss, pos.take_profit
        );
        self.positions.push(pos);
        self.last_trade_time = Some(Utc::now());
        self.sync_safety();
        self.positions.last()
    }

    /// Tick: check SL/TP/duration for all open positions.
    pub fn tick(&mut self) -> Vec<(String, ExitReason, f64)> {
        let mut closed = vec![];
        let price = match self.current_price {
            Some(p) => p,
            None => return closed,
        };
        let now = Utc::now();
        for pos in self.positions.iter_mut() {
            if pos.status != PositionStatus::OPEN {
                continue;
            }
            pos.update_pnl(price);
            if let Some(reason) = pos.check_exit_trigger(price) {
                let pnl = pos.pnl;
                pos.close(reason.clone());
                self.equity += pnl;
                self.daily_pnl += pnl;
                self.weekly_pnl += pnl;
                closed.push((pos.trade_id.clone(), reason, pnl));
                continue;
            }
            if pos.duration_exceeded(now, MAX_POSITION_DURATION_HOURS) {
                let pnl = pos.pnl;
                pos.close(ExitReason::MAX_DURATION);
                self.equity += pnl;
                self.daily_pnl += pnl;
                self.weekly_pnl += pnl;
                closed.push((pos.trade_id.clone(), ExitReason::MAX_DURATION, pnl));
                continue;
            }
        }
        // Daily loss circuit breaker — close all open
        if self.daily_pnl < -MAX_DAILY_LOSS * self.starting_equity {
            for pos in self.positions.iter_mut() {
                if pos.status == PositionStatus::OPEN {
                    let pnl = pos.pnl;
                    pos.close(ExitReason::DAILY_LOSS_CIRCUIT_BREAKER);
                    self.equity += pnl;
                    self.daily_pnl += pnl;
                    self.weekly_pnl += pnl;
                    closed.push((pos.trade_id.clone(), ExitReason::DAILY_LOSS_CIRCUIT_BREAKER, pnl));
                }
            }
            warn!("Daily loss circuit breaker triggered. Halting.");
        }
        // Move closed from positions to closed_trades
        let mut open = vec![];
        for pos in self.positions.drain(..) {
            if pos.status == PositionStatus::OPEN {
                open.push(pos);
            } else {
                self.closed_trades.push(pos);
            }
        }
        self.positions = open;
        self.sync_safety();
        closed
    }

    pub fn get_status(&self) -> AccountStatus {
        AccountStatus {
            equity: (self.equity * 100.0).round() / 100.0,
            starting_equity: self.starting_equity,
            open_positions: self.positions.iter().filter(|p| p.status == PositionStatus::OPEN).count(),
            closed_trades: self.closed_trades.len(),
            daily_pnl: (self.daily_pnl * 100.0).round() / 100.0,
            weekly_pnl: (self.weekly_pnl * 100.0).round() / 100.0,
            current_price: self.current_price,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{EntryZone, PositionStatus};
    use chrono::{Duration, Utc};
    use serde_json::json;

    fn decision(action: Action) -> TradeDecision {
        TradeDecision {
            action,
            conviction: 80,
            stop_loss_pct: 0.02,
            take_profit_pct: 0.04,
            size_multiplier: 1.0,
            reasoning: "test".to_string(),
            entry_zone: Some(EntryZone { low: 99.0, high: 101.0 }),
        }
    }

    fn snapshot() -> serde_json::Value {
        json!({
            "symbol": "BTC-USD",
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
    fn update_price_marks_open_positions_and_ignores_closed_positions() {
        let mut manager = PositionManager::new(10_000.0);
        manager.positions.push(Position::new("BTC-USD", Action::LONG, 100.0, 2.0, 95.0, 110.0, 80, "open"));
        let mut closed = Position::new("BTC-USD", Action::LONG, 100.0, 2.0, 95.0, 110.0, 80, "closed");
        closed.close(ExitReason::AGENT_EXIT);
        manager.positions.push(closed);

        manager.update_price(110.0);

        assert_eq!(manager.current_price, Some(110.0));
        assert_eq!(manager.positions[0].pnl, 20.0);
        assert_eq!(manager.positions[1].pnl, 0.0);
    }

    #[test]
    fn evaluate_decision_requires_action_and_current_price() {
        let mut manager = PositionManager::new(10_000.0);

        assert!(manager.evaluate_decision(&snapshot(), &decision(Action::NO_TRADE)).is_none());
        assert!(manager.evaluate_decision(&snapshot(), &decision(Action::LONG)).is_none());
    }

    #[test]
    fn evaluate_decision_opens_long_position_with_safety_sized_units() {
        let mut manager = PositionManager::new(10_000.0);
        manager.update_price(100.0);

        let pos = manager.evaluate_decision(&snapshot(), &decision(Action::LONG)).unwrap();

        assert_eq!(pos.symbol, "BTC-USD");
        assert_eq!(pos.action, Action::LONG);
        assert_eq!(pos.entry_price, 100.0);
        assert_eq!(pos.stop_loss, 98.0);
        assert_eq!(pos.take_profit, 104.0);
        assert_eq!(pos.size, 100.0);
        assert_eq!(manager.get_status().open_positions, 1);
    }

    #[test]
    fn evaluate_decision_opens_short_position_with_inverse_stop_and_target() {
        let mut manager = PositionManager::new(10_000.0);
        manager.update_price(100.0);

        let pos = manager.evaluate_decision(&snapshot(), &decision(Action::SHORT)).unwrap();

        assert_eq!(pos.action, Action::SHORT);
        assert_eq!(pos.stop_loss, 102.0);
        assert_eq!(pos.take_profit, 96.0);
        assert_eq!(pos.size, 100.0);
    }

    #[test]
    fn evaluate_decision_respects_failed_safety_check() {
        let mut manager = PositionManager::new(10_000.0);
        manager.update_price(100.0);
        let mut low_conviction = decision(Action::LONG);
        low_conviction.conviction = 20;

        assert!(manager.evaluate_decision(&snapshot(), &low_conviction).is_none());
        assert!(manager.positions.is_empty());
    }

    #[test]
    fn tick_closes_take_profit_and_moves_position_to_closed_trades() {
        let mut manager = PositionManager::new(10_000.0);
        manager.update_price(100.0);
        manager.evaluate_decision(&snapshot(), &decision(Action::LONG)).unwrap();

        manager.update_price(104.0);
        let closed = manager.tick();

        assert_eq!(closed.len(), 1);
        assert_eq!(closed[0].1, ExitReason::TAKE_PROFIT);
        assert_eq!(closed[0].2, 400.0);
        assert_eq!(manager.equity, 10_400.0);
        assert!(manager.positions.is_empty());
        assert_eq!(manager.closed_trades.len(), 1);
        assert_eq!(manager.closed_trades[0].status, PositionStatus::CLOSED);
    }

    #[test]
    fn tick_closes_stop_loss_for_short_position() {
        let mut manager = PositionManager::new(10_000.0);
        manager.update_price(100.0);
        manager.evaluate_decision(&snapshot(), &decision(Action::SHORT)).unwrap();

        manager.update_price(102.0);
        let closed = manager.tick();

        assert_eq!(closed.len(), 1);
        assert_eq!(closed[0].1, ExitReason::STOP_LOSS);
        assert_eq!(closed[0].2, -200.0);
        assert_eq!(manager.equity, 9_800.0);
        assert_eq!(manager.closed_trades.len(), 1);
    }

    #[test]
    fn tick_closes_positions_past_max_duration() {
        let mut manager = PositionManager::new(10_000.0);
        let mut pos = Position::new("BTC-USD", Action::LONG, 100.0, 1.0, 1.0, 1_000.0, 80, "old");
        pos.opened_at = Utc::now() - Duration::hours((MAX_POSITION_DURATION_HOURS + 1) as i64);
        manager.positions.push(pos);
        manager.update_price(101.0);

        let closed = manager.tick();

        assert_eq!(closed.len(), 1);
        assert_eq!(closed[0].1, ExitReason::MAX_DURATION);
        assert_eq!(manager.closed_trades.len(), 1);
    }

    #[test]
    fn tick_applies_daily_loss_circuit_breaker_to_remaining_open_positions() {
        let mut manager = PositionManager::new(10_000.0);
        manager.daily_pnl = -600.0;
        manager.positions.push(Position::new(
            "BTC-USD",
            Action::LONG,
            100.0,
            1.0,
            1.0,
            1_000.0,
            80,
            "breaker",
        ));
        manager.update_price(100.0);

        let closed = manager.tick();

        assert_eq!(closed.len(), 1);
        assert_eq!(closed[0].1, ExitReason::DAILY_LOSS_CIRCUIT_BREAKER);
        assert!(manager.positions.is_empty());
        assert_eq!(manager.closed_trades.len(), 1);
    }

    #[test]
    fn get_status_rounds_money_and_counts_positions() {
        let mut manager = PositionManager::new(10_000.0);
        manager.equity = 10_123.456;
        manager.daily_pnl = 12.345;
        manager.weekly_pnl = -6.789;
        manager.current_price = Some(101.5);
        manager.positions.push(Position::new("BTC-USD", Action::LONG, 100.0, 1.0, 95.0, 110.0, 80, "open"));
        let mut closed = Position::new("BTC-USD", Action::LONG, 100.0, 1.0, 95.0, 110.0, 80, "closed");
        closed.close(ExitReason::AGENT_EXIT);
        manager.closed_trades.push(closed);

        let status = manager.get_status();

        assert_eq!(status.equity, 10_123.46);
        assert_eq!(status.daily_pnl, 12.35);
        assert_eq!(status.weekly_pnl, -6.79);
        assert_eq!(status.open_positions, 1);
        assert_eq!(status.closed_trades, 1);
        assert_eq!(status.current_price, Some(101.5));
    }
}
