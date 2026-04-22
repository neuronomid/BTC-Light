from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Dict, Tuple

from config import settings
from statistical_engine.regime import STATE_LABELS


@dataclass(frozen=True)
class BacktestProfile:
    name: str = "baseline"
    min_conviction: int = 65
    min_ev: float = 0.002
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.05
    size_multiplier: float = 1.0
    max_risk_per_trade: float = 0.050
    max_daily_loss: float = settings.MAX_DAILY_LOSS
    max_weekly_loss: float = settings.MAX_WEEKLY_LOSS
    max_open_positions: int = settings.MAX_OPEN_POSITIONS
    max_position_duration_hours: int = 24
    min_time_between_trades_hours: int = 2
    max_leverage: float = settings.MAX_LEVERAGE
    hmm_training_window: int = settings.HMM_TRAINING_WINDOW
    regime_state_labels: Tuple[str, ...] = tuple(STATE_LABELS)
    monte_carlo_paths: int = settings.MONTE_CARLO_PATHS
    refit_interval_candles: int = 42
    kelly_fraction_override: float = 0.45
    seed: int = 42

    @classmethod
    def baseline(
        cls,
        *,
        monte_carlo_paths: int | None = None,
        refit_interval_candles: int = 42,
    ) -> "BacktestProfile":
        kwargs = {"refit_interval_candles": refit_interval_candles}
        if monte_carlo_paths is not None:
            kwargs["monte_carlo_paths"] = monte_carlo_paths
        return cls(**kwargs)

    def with_updates(self, **updates) -> "BacktestProfile":
        return replace(self, **updates)

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["regime_state_labels"] = list(self.regime_state_labels)
        return data
