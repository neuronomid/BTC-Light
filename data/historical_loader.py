from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests


KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]

TIMEFRAME_DELTAS = {
    "15m": pd.Timedelta(minutes=15),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}


@dataclass
class TimeframeAudit:
    timeframe: str
    source_files: List[str] = field(default_factory=list)
    loaded_rows: int = 0
    fetched_rows: int = 0
    final_rows: int = 0
    duplicates_removed: int = 0
    first_timestamp: Optional[str] = None
    last_timestamp: Optional[str] = None
    missing_ranges: List[Dict[str, str]] = field(default_factory=list)
    gaps: List[Dict[str, str]] = field(default_factory=list)
    fetch_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HistoricalDataBundle:
    frames: Dict[str, pd.DataFrame]
    audit: Dict[str, Dict]
    requested_start: str
    requested_end: str
    effective_start: str
    effective_end: str
    caveats: List[str] = field(default_factory=list)


def ensure_utc_timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def parse_date_bound(value: str, *, is_end: bool = False) -> pd.Timestamp:
    ts = ensure_utc_timestamp(value)
    if is_end and len(value) <= 10:
        ts = ts + pd.Timedelta(days=1)
    return ts


def detect_timestamp_unit(value: float) -> str:
    value = abs(float(value))
    if value >= 1e17:
        return "ns"
    if value >= 1e14:
        return "us"
    if value >= 1e11:
        return "ms"
    return "s"


def normalize_kline_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = raw.copy()
    if len(df.columns) >= len(KLINE_COLUMNS):
        df = df.iloc[:, : len(KLINE_COLUMNS)]
        df.columns = KLINE_COLUMNS
    elif "open_time" not in df.columns:
        raise ValueError("Historical kline data must include Binance-style open_time values.")

    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    df = df.dropna(subset=["open_time"])
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    unit = detect_timestamp_unit(df["open_time"].iloc[0])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    return df.sort_values("timestamp").reset_index(drop=True)


def dedupe_sort(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    if df.empty:
        return df.copy(), 0
    before = len(df)
    out = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    out = out.reset_index(drop=True)
    return out, before - len(out)


def contiguous_missing_ranges(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timeframe: str,
) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    start = ensure_utc_timestamp(start)
    end = ensure_utc_timestamp(end)
    step = TIMEFRAME_DELTAS[timeframe]
    if end <= start:
        return []
    if df.empty:
        return [(start, end)]

    expected = pd.date_range(start=start, end=end - step, freq=step, tz="UTC")
    if expected.empty:
        return []
    existing = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True))
    missing = expected.difference(existing)
    if missing.empty:
        return []

    ranges: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    range_start = missing[0]
    previous = missing[0]
    for ts in missing[1:]:
        if ts - previous != step:
            ranges.append((range_start, previous + step))
            range_start = ts
        previous = ts
    ranges.append((range_start, previous + step))
    return ranges


def internal_gaps(df: pd.DataFrame, timeframe: str, limit: int = 100) -> List[Dict[str, str]]:
    if df.empty or len(df) < 2:
        return []
    step = TIMEFRAME_DELTAS[timeframe]
    timestamps = pd.to_datetime(df["timestamp"], utc=True).sort_values().reset_index(drop=True)
    gaps: List[Dict[str, str]] = []
    for prev, cur in zip(timestamps.iloc[:-1], timestamps.iloc[1:]):
        if cur - prev != step:
            gaps.append(
                {
                    "from": prev.isoformat(),
                    "to": cur.isoformat(),
                    "expected_next": (prev + step).isoformat(),
                }
            )
            if len(gaps) >= limit:
                break
    return gaps


def ranges_to_audit(ranges: Iterable[Tuple[pd.Timestamp, pd.Timestamp]]) -> List[Dict[str, str]]:
    return [{"start": start.isoformat(), "end": end.isoformat()} for start, end in ranges]


class HistoricalDataLoader:
    def __init__(self, history_dir: Path | str, data_symbol: str = "BTCUSDT"):
        self.history_dir = Path(history_dir)
        self.data_symbol = data_symbol

    def _files_for_timeframe(self, timeframe: str) -> List[Path]:
        if not self.history_dir.exists():
            return []
        return sorted(self.history_dir.rglob(f"*-{timeframe}-*.csv"))

    def load_local_timeframe(self, timeframe: str) -> Tuple[pd.DataFrame, TimeframeAudit]:
        audit = TimeframeAudit(timeframe=timeframe)
        frames = []
        for path in self._files_for_timeframe(timeframe):
            raw = pd.read_csv(path, header=None)
            frame = normalize_kline_frame(raw)
            if not frame.empty:
                frames.append(frame)
            audit.source_files.append(str(path))
            audit.loaded_rows += len(raw)

        if frames:
            df = pd.concat(frames, ignore_index=True)
        else:
            df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df, duplicates = dedupe_sort(df)
        audit.duplicates_removed = duplicates
        audit.final_rows = len(df)
        if not df.empty:
            audit.first_timestamp = pd.Timestamp(df["timestamp"].iloc[0]).isoformat()
            audit.last_timestamp = pd.Timestamp(df["timestamp"].iloc[-1]).isoformat()
        audit.gaps = internal_gaps(df, timeframe)
        return df, audit

    def fetch_binance_futures(
        self,
        timeframe: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        timeout: int = 20,
    ) -> pd.DataFrame:
        start = ensure_utc_timestamp(start)
        end = ensure_utc_timestamp(end)
        if end <= start:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        rows = []
        step_ms = int(TIMEFRAME_DELTAS[timeframe].total_seconds() * 1000)
        current_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        url = "https://fapi.binance.com/fapi/v1/klines"

        while current_ms < end_ms:
            response = requests.get(
                url,
                params={
                    "symbol": self.data_symbol,
                    "interval": timeframe,
                    "startTime": current_ms,
                    "endTime": end_ms - 1,
                    "limit": 1500,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            chunk = response.json()
            if not chunk:
                break
            rows.extend(chunk)
            last_open = int(chunk[-1][0])
            next_ms = last_open + step_ms
            if next_ms <= current_ms:
                break
            current_ms = next_ms
            if len(chunk) < 1500:
                break

        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = normalize_kline_frame(pd.DataFrame(rows))
        return df[(df["timestamp"] >= start) & (df["timestamp"] < end)].reset_index(drop=True)

    def _merge_fetched(
        self,
        local: pd.DataFrame,
        fetched: pd.DataFrame,
        audit: TimeframeAudit,
        timeframe: str,
    ) -> pd.DataFrame:
        if fetched.empty:
            return local
        merged = pd.concat([local, fetched], ignore_index=True)
        merged, duplicates = dedupe_sort(merged)
        audit.fetched_rows += len(fetched)
        audit.duplicates_removed += duplicates
        audit.final_rows = len(merged)
        audit.gaps = internal_gaps(merged, timeframe)
        if not merged.empty:
            audit.first_timestamp = pd.Timestamp(merged["timestamp"].iloc[0]).isoformat()
            audit.last_timestamp = pd.Timestamp(merged["timestamp"].iloc[-1]).isoformat()
        return merged

    def load(
        self,
        start: pd.Timestamp,
        end: Optional[pd.Timestamp] = None,
        *,
        fetch_missing: bool = False,
        warmup_candles: int = 1000,
        timeframes: Iterable[str] = ("15m", "4h", "1d"),
    ) -> HistoricalDataBundle:
        start = ensure_utc_timestamp(start)
        local_frames: Dict[str, pd.DataFrame] = {}
        audits: Dict[str, TimeframeAudit] = {}
        for timeframe in timeframes:
            df, audit = self.load_local_timeframe(timeframe)
            local_frames[timeframe] = df
            audits[timeframe] = audit

        if end is None:
            four_h = local_frames.get("4h", pd.DataFrame())
            if not four_h.empty:
                end = pd.Timestamp(four_h["timestamp"].max()) + TIMEFRAME_DELTAS["4h"]
            else:
                end = pd.Timestamp.utcnow().floor("D")
        end = ensure_utc_timestamp(end)

        frames: Dict[str, pd.DataFrame] = {}
        caveats: List[str] = []
        warmup_start = start - warmup_candles * TIMEFRAME_DELTAS["4h"]
        required_starts = {
            "4h": warmup_start,
            "15m": start,
            "1d": start.floor("D"),
        }

        for timeframe, df in local_frames.items():
            required_start = required_starts.get(timeframe, start)
            missing = contiguous_missing_ranges(df, required_start, end, timeframe)
            audits[timeframe].missing_ranges = ranges_to_audit(missing)
            if fetch_missing and missing:
                fetched_frames = []
                for missing_start, missing_end in missing:
                    try:
                        fetched_frames.append(
                            self.fetch_binance_futures(timeframe, missing_start, missing_end)
                        )
                    except requests.RequestException as exc:
                        message = f"{timeframe} fetch failed for {missing_start.isoformat()} to {missing_end.isoformat()}: {exc}"
                        audits[timeframe].fetch_errors.append(message)
                        caveats.append(message)
                if fetched_frames:
                    fetched = pd.concat(fetched_frames, ignore_index=True)
                    df = self._merge_fetched(df, fetched, audits[timeframe], timeframe)
                    remaining = contiguous_missing_ranges(df, required_start, end, timeframe)
                    audits[timeframe].missing_ranges = ranges_to_audit(remaining)

            mask = (df["timestamp"] >= required_start) & (df["timestamp"] < end)
            clipped = df.loc[mask].sort_values("timestamp").reset_index(drop=True)
            frames[timeframe] = clipped
            audits[timeframe].final_rows = len(clipped)
            if not clipped.empty:
                audits[timeframe].first_timestamp = pd.Timestamp(clipped["timestamp"].iloc[0]).isoformat()
                audits[timeframe].last_timestamp = pd.Timestamp(clipped["timestamp"].iloc[-1]).isoformat()
            else:
                audits[timeframe].first_timestamp = None
                audits[timeframe].last_timestamp = None

        four_h = frames.get("4h", pd.DataFrame())
        if four_h.empty:
            effective_start = start
            caveats.append("No 4H candles are available after loading historical data.")
        else:
            first_decision = pd.Timestamp(four_h["timestamp"].iloc[0]) + TIMEFRAME_DELTAS["4h"]
            effective_start = max(start, first_decision)

        audit_dict = {tf: audit.to_dict() for tf, audit in audits.items()}
        return HistoricalDataBundle(
            frames=frames,
            audit=audit_dict,
            requested_start=start.isoformat(),
            requested_end=end.isoformat(),
            effective_start=effective_start.isoformat(),
            effective_end=end.isoformat(),
            caveats=caveats,
        )
