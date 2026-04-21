use crate::config::*;
use crate::models::*;
use redis::aio::MultiplexedConnection;
use redis::{AsyncCommands, Client, Cmd};
use serde_json::Value;
use anyhow::Result;

pub struct RedisBridge {
    conn: MultiplexedConnection,
}

impl RedisBridge {
    pub async fn connect(url: &str) -> Result<Self> {
        let client = Client::open(url)?;
        let conn = client.get_multiplexed_async_connection().await?;
        Ok(Self { conn })
    }

    /// Publish structured JSON to a channel.
    pub async fn publish(&mut self, channel: &str, payload: &Value) -> Result<()> {
        let json = serde_json::to_string(payload)?;
        let _: () = self.conn.publish(channel, json).await?;
        Ok(())
    }

    /// Set JSON value with optional TTL (seconds).
    pub async fn set_json(&mut self, key: &str, value: &Value, ttl_seconds: Option<u64>) -> Result<()> {
        let json = serde_json::to_string(value)?;
        if let Some(ttl) = ttl_seconds {
            let _: () = Cmd::new()
                .arg("SETEX")
                .arg(key)
                .arg(ttl)
                .arg(json)
                .query_async(&mut self.conn)
                .await?;
        } else {
            let _: () = self.conn.set(key, json).await?;
        }
        Ok(())
    }

    /// Get and deserialize JSON from a key.
    pub async fn get_json(&mut self, key: &str) -> Result<Option<Value>> {
        let val: Option<String> = self.conn.get(key).await?;
        match val {
            Some(s) => Ok(Some(serde_json::from_str(&s)?)),
            None => Ok(None),
        }
    }

    /// Publish position opened event.
    pub async fn publish_position_opened(&mut self, pos: &Position) -> Result<()> {
        let payload = serde_json::json!({
            "trade_id": pos.trade_id,
            "action": serde_json::to_string(&pos.action)?,
            "entry_price": pos.entry_price,
            "size": pos.size,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "conviction": pos.conviction,
        });
        self.publish(REDIS_CHANNEL_POSITION_OPENED, &payload).await
    }

    /// Publish position closed event.
    pub async fn publish_position_closed(
        &mut self,
        trade_id: &str,
        reason: &ExitReason,
        pnl: f64,
        pnl_pct: f64,
        equity: f64,
    ) -> Result<()> {
        let payload = serde_json::json!({
            "trade_id": trade_id,
            "reason": format!("{:?}", reason),
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "equity": equity,
        });
        self.publish(REDIS_CHANNEL_POSITION_CLOSED, &payload).await
    }

    /// Publish account status.
    pub async fn publish_status(&mut self, status: &AccountStatus) -> Result<()> {
        let value = serde_json::to_value(status)?;
        self.set_json(REDIS_KEY_TRADING_STATUS, &value, Some(60)).await
    }
}
