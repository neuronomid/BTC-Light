mod config;
mod models;
mod position_manager;
mod redis_bridge;
mod safety;

use crate::config::*;
use crate::models::*;
use crate::position_manager::PositionManager;
use crate::redis_bridge::RedisBridge;
use anyhow::Result;
use log::{error, info};
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::time::{interval, Duration};
use futures_util::StreamExt;

#[tokio::main]
async fn main() -> Result<()> {
    env_logger::init();
    info!("Execution Engine starting...");

    let redis_url =
        std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let redis_sub_url = redis_url.clone();

    let pm = Arc::new(Mutex::new(PositionManager::new(
        std::env::var("INITIAL_EQUITY")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(10000.0),
    )));

    // Task 1: Tick execution loop (SL/TP/duration/circuit breakers)
    let pm_tick = pm.clone();
    let mut redis_tick = RedisBridge::connect(&redis_url).await?;
    tokio::spawn(async move {
        let mut ticker = interval(Duration::from_secs(10));
        loop {
            ticker.tick().await;
            let mut manager = pm_tick.lock().await;
            let closed = manager.tick();
            for (trade_id, reason, pnl) in closed {
                info!(
                    "Closed {} | {:?} | PnL: {:.2}",
                    trade_id, reason, pnl
                );
                if let Err(e) = redis_tick
                    .publish_position_closed(
                        &trade_id,
                        &reason,
                        pnl,
                        pnl / manager.starting_equity,
                        manager.equity,
                    )
                    .await
                {
                    error!("Redis publish error: {}", e);
                }
            }
            let status = manager.get_status();
            if let Err(e) = redis_tick.publish_status(&status).await {
                error!("Redis status publish error: {}", e);
            }
        }
    });

    // Task 2: Subscribe to decisions from Python orchestrator
    let pm_sub = pm.clone();
    tokio::spawn(async move {
        let client = redis::Client::open(redis_sub_url).expect("Redis client");
        let mut pubsub = client.get_async_pubsub().await.expect("pubsub");
        pubsub.subscribe("trade_decision").await.expect("subscribe");
        let mut msg_stream = pubsub.on_message();
        info!("Subscribed to trade_decision channel");
        while let Some(msg) = msg_stream.next().await {
            let payload: String = match msg.get_payload() {
                Ok(p) => p,
                Err(e) => {
                    error!("Payload error: {}", e);
                    continue;
                }
            };
            let value: serde_json::Value = match serde_json::from_str(&payload) {
                Ok(v) => v,
                Err(e) => {
                    error!("JSON parse error: {}", e);
                    continue;
                }
            };
            let decision: TradeDecision = match serde_json::from_value(value.clone()) {
                Ok(d) => d,
                Err(e) => {
                    error!("Decision parse error: {}", e);
                    continue;
                }
            };
            let snapshot: serde_json::Value = value.get("snapshot").cloned().unwrap_or(serde_json::json!({}));
            let mut manager = pm_sub.lock().await;
            if let Some(pos) = manager.evaluate_decision(&snapshot, &decision) {
                info!(
                    "Opened position {} | {:?} | Conviction: {}",
                    pos.trade_id, pos.action, pos.conviction
                );
            }
        }
    });

    // Task 3: Poll latest price from Redis
    let pm_price = pm.clone();
    let redis_price_url = std::env::var("REDIS_URL")
        .unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    tokio::spawn(async move {
        use redis::AsyncCommands;
        let client = redis::Client::open(redis_price_url).expect("Redis client");
        let mut conn = client.get_multiplexed_async_connection().await.expect("Redis conn");
        let mut ticker = interval(Duration::from_secs(5));
        loop {
            ticker.tick().await;
            let price_str: Option<String> = conn.get("latest_price").await.ok().flatten();
            if let Some(s) = price_str {
                if let Ok(price) = s.parse::<f64>() {
                    let mut manager = pm_price.lock().await;
                    manager.update_price(price);
                }
            }
        }
    });

    info!("Execution Engine running. Press Ctrl+C to stop.");
    tokio::signal::ctrl_c().await?;
    info!("Shutting down...");
    Ok(())
}
