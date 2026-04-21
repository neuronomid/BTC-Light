use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum Action {
    LONG,
    SHORT,
    NO_TRADE,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum PositionStatus {
    OPEN,
    CLOSED,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExitReason {
    STOP_LOSS,
    TAKE_PROFIT,
    MAX_DURATION,
    DAILY_LOSS_CIRCUIT_BREAKER,
    WEEKLY_LOSS_CIRCUIT_BREAKER,
    AGENT_EXIT,
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    #[test]
    fn position_new_defaults_to_open_with_generated_trade_id() {
        let pos = Position::new(
            "BTC-USD",
            Action::LONG,
            100.0,
            2.0,
            95.0,
            110.0,
            80,
            "test",
        );

        assert_eq!(pos.symbol, "BTC-USD");
        assert_eq!(pos.action, Action::LONG);
        assert_eq!(pos.status, PositionStatus::OPEN);
        assert!(uuid::Uuid::parse_str(&pos.trade_id).is_ok());
        assert_eq!(pos.pnl, 0.0);
        assert_eq!(pos.closed_at, None);
        assert_eq!(pos.exit_reason, None);
    }

    #[test]
    fn update_pnl_handles_long_and_short_positions() {
        let mut long = Position::new("BTC-USD", Action::LONG, 100.0, 2.0, 95.0, 110.0, 80, "long");
        let mut short = Position::new("BTC-USD", Action::SHORT, 100.0, 3.0, 105.0, 90.0, 80, "short");

        long.update_pnl(110.0);
        short.update_pnl(110.0);

        assert_eq!(long.pnl, 20.0);
        assert_eq!(long.pnl_pct, 0.1);
        assert_eq!(short.pnl, -30.0);
        assert_eq!(short.pnl_pct, -0.1);
    }

    #[test]
    fn check_exit_trigger_handles_long_stop_loss_and_take_profit() {
        let pos = Position::new("BTC-USD", Action::LONG, 100.0, 1.0, 95.0, 110.0, 80, "long");

        assert_eq!(pos.check_exit_trigger(94.99), Some(ExitReason::STOP_LOSS));
        assert_eq!(pos.check_exit_trigger(110.0), Some(ExitReason::TAKE_PROFIT));
        assert_eq!(pos.check_exit_trigger(100.0), None);
    }

    #[test]
    fn check_exit_trigger_handles_short_stop_loss_and_take_profit() {
        let pos = Position::new("BTC-USD", Action::SHORT, 100.0, 1.0, 105.0, 90.0, 80, "short");

        assert_eq!(pos.check_exit_trigger(105.0), Some(ExitReason::STOP_LOSS));
        assert_eq!(pos.check_exit_trigger(89.99), Some(ExitReason::TAKE_PROFIT));
        assert_eq!(pos.check_exit_trigger(100.0), None);
    }

    #[test]
    fn closed_position_does_not_emit_exit_trigger() {
        let mut pos = Position::new("BTC-USD", Action::LONG, 100.0, 1.0, 95.0, 110.0, 80, "long");
        pos.close(ExitReason::AGENT_EXIT);

        assert_eq!(pos.check_exit_trigger(90.0), None);
        assert_eq!(pos.status, PositionStatus::CLOSED);
        assert!(pos.closed_at.is_some());
        assert_eq!(pos.exit_reason, Some(ExitReason::AGENT_EXIT));
    }

    #[test]
    fn duration_exceeded_uses_strict_hour_threshold() {
        let now = Utc::now();
        let mut pos = Position::new("BTC-USD", Action::LONG, 100.0, 1.0, 95.0, 110.0, 80, "long");

        pos.opened_at = now - Duration::hours(24);
        assert!(!pos.duration_exceeded(now, 24));

        pos.opened_at = now - Duration::hours(25);
        assert!(pos.duration_exceeded(now, 24));
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeDecision {
    pub action: Action,
    pub conviction: u8,
    pub stop_loss_pct: f64,
    pub take_profit_pct: f64,
    pub size_multiplier: f64,
    pub reasoning: String,
    pub entry_zone: Option<EntryZone>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EntryZone {
    pub low: f64,
    pub high: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub trade_id: String,
    pub symbol: String,
    pub action: Action,
    pub entry_price: f64,
    pub size: f64,
    pub stop_loss: f64,
    pub take_profit: f64,
    pub opened_at: DateTime<Utc>,
    pub conviction: u8,
    pub reasoning: String,
    pub pnl: f64,
    pub pnl_pct: f64,
    pub status: PositionStatus,
    pub closed_at: Option<DateTime<Utc>>,
    pub exit_reason: Option<ExitReason>,
}

impl Position {
    pub fn new(
        symbol: impl Into<String>,
        action: Action,
        entry_price: f64,
        size: f64,
        stop_loss: f64,
        take_profit: f64,
        conviction: u8,
        reasoning: impl Into<String>,
    ) -> Self {
        Self {
            trade_id: Uuid::new_v4().to_string(),
            symbol: symbol.into(),
            action,
            entry_price,
            size,
            stop_loss,
            take_profit,
            opened_at: Utc::now(),
            conviction,
            reasoning: reasoning.into(),
            pnl: 0.0,
            pnl_pct: 0.0,
            status: PositionStatus::OPEN,
            closed_at: None,
            exit_reason: None,
        }
    }

    /// Update unrealized PnL given current mark price.
    pub fn update_pnl(&mut self, price: f64) {
        let diff = if self.action == Action::LONG {
            price - self.entry_price
        } else {
            self.entry_price - price
        };
        self.pnl = diff * self.size;
        self.pnl_pct = if self.entry_price > 0.0 {
            diff / self.entry_price
        } else {
            0.0
        };
    }

    /// Check if price has hit SL or TP.
    pub fn check_exit_trigger(&self, price: f64) -> Option<ExitReason> {
        if self.status != PositionStatus::OPEN {
            return None;
        }
        match self.action {
            Action::LONG => {
                if price <= self.stop_loss {
                    Some(ExitReason::STOP_LOSS)
                } else if price >= self.take_profit {
                    Some(ExitReason::TAKE_PROFIT)
                } else {
                    None
                }
            }
            Action::SHORT => {
                if price >= self.stop_loss {
                    Some(ExitReason::STOP_LOSS)
                } else if price <= self.take_profit {
                    Some(ExitReason::TAKE_PROFIT)
                } else {
                    None
                }
            }
            _ => None,
        }
    }

    /// Check if max duration exceeded.
    pub fn duration_exceeded(&self, now: DateTime<Utc>, max_hours: u32) -> bool {
        let elapsed = now.signed_duration_since(self.opened_at);
        elapsed.num_hours() > max_hours as i64
    }

    pub fn close(&mut self, reason: ExitReason) {
        self.status = PositionStatus::CLOSED;
        self.closed_at = Some(Utc::now());
        self.exit_reason = Some(reason);
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountStatus {
    pub equity: f64,
    pub starting_equity: f64,
    pub open_positions: usize,
    pub closed_trades: usize,
    pub daily_pnl: f64,
    pub weekly_pnl: f64,
    pub current_price: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskUpdate {
    pub daily_pnl: f64,
    pub weekly_pnl: f64,
    pub open_positions: usize,
    pub last_trade_time: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyCheck {
    pub passed: bool,
    pub reason: String,
}

impl SafetyCheck {
    pub fn pass(reason: impl Into<String>) -> Self {
        Self {
            passed: true,
            reason: reason.into(),
        }
    }
    pub fn fail(reason: impl Into<String>) -> Self {
        Self {
            passed: false,
            reason: reason.into(),
        }
    }
}
