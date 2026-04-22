/// Hard safety rules — non-overridable by agents.
pub const MAX_RISK_PER_TRADE: f64 = 0.02;
pub const MAX_DAILY_LOSS: f64 = 0.05;
pub const MAX_WEEKLY_LOSS: f64 = 0.10;
pub const MAX_OPEN_POSITIONS: u32 = 1;
pub const MAX_POSITION_DURATION_HOURS: u32 = 24;
pub const MIN_TIME_BETWEEN_TRADES_HOURS: u32 = 4;
pub const MAX_LEVERAGE: f64 = 5.0;
pub const MIN_CONVICTION_TO_TRADE: u8 = 70;
pub const MIN_EV_TO_TRADE: f64 = 0.005;

/// Redis keys used for shared state.
pub const REDIS_KEY_TRADING_STATUS: &str = "trading_status";
#[allow(dead_code)]
pub const REDIS_CHANNEL_POSITION_OPENED: &str = "position:opened";
pub const REDIS_CHANNEL_POSITION_CLOSED: &str = "position:closed";
