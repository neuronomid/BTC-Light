import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# TimescaleDB / PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "btc_trader")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Data
SYMBOL = os.getenv("SYMBOL", "BTC-USD")
TIMEFRAME = os.getenv("TIMEFRAME", "4h")
YF_INTERVAL = os.getenv("YF_INTERVAL", "1h")  # yfinance fetch interval
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "730"))

# Risk Limits
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.05"))
MAX_WEEKLY_LOSS = float(os.getenv("MAX_WEEKLY_LOSS", "0.10"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))
MAX_POSITION_DURATION_HOURS = int(os.getenv("MAX_POSITION_DURATION_HOURS", "24"))
MIN_TIME_BETWEEN_TRADES_HOURS = int(os.getenv("MIN_TIME_BETWEEN_TRADES_HOURS", "4"))
MAX_LEVERAGE = float(os.getenv("MAX_LEVERAGE", "5.0"))
MIN_CONVICTION_TO_TRADE = int(os.getenv("MIN_CONVICTION_TO_TRADE", "70"))
MIN_EV_TO_TRADE = float(os.getenv("MIN_EV_TO_TRADE", "0.005"))

# Statistical Engine
HMM_STATES = 4
HMM_TRAINING_WINDOW = 1000
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.25"))
MONTE_CARLO_PATHS = 10000

# OpenRouter / LLM API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
AGENT_MODEL_OPUS = os.getenv("AGENT_MODEL_OPUS", "anthropic/claude-opus-4-6")
AGENT_MODEL_SONNET = os.getenv("AGENT_MODEL_SONNET", "anthropic/claude-sonnet-4-6")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
