"""
MT5 UNIVERSAL CONNECTOR
TIMEFRAME AGGREGATOR
VERSION 2.0.0

Canonical candle format:
    {
        "time": datetime,
        "timeframe": str,
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "tick_volume": int,
        "volume": float,
        "spread": int,
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .timeframe_registry import (
    is_native_timeframe,
    is_supported_timeframe,
    timeframe_to_minutes,
)


# ======================================================================
# TIMESTAMP
# ======================================================================

def _ensure_utc(value: Any) -> datetime:

    if isinstance(value, datetime):

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    if isinstance(value, (int, float)):

        return datetime.fromtimestamp(
            float(value),
            tz=timezone.utc,
        )

    if isinstance(value, str):

        text = value.strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        parsed = datetime.fromisoformat(
            text
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    if hasattr(value, "item"):

        try:

            scalar = value.item()

            if isinstance(
                scalar,
                (int, float),
            ):

                return datetime.fromtimestamp(
                    float(scalar),
                    tz=timezone.utc,
                )

        except Exception:
            pass

    raise TypeError(
        "Unsupported timestamp type: "
        f"{type(value).__name__}"
    )


# ======================================================================
# CANONICAL CANDLE CONVERSION
# ======================================================================

def _to_candle_dict(
    source: Any,
    timeframe: str,
) -> Dict[str, Any]:
    """
    Convert dictionary/object/MT5-style candle into the canonical
    dictionary representation used throughout the connector.
    """

    if isinstance(source, dict):

        timestamp = source.get(
            "time",
            source.get("timestamp"),
        )

        open_price = source.get(
            "open",
            source.get("o"),
        )

        high_price = source.get(
            "high",
            source.get("h"),
        )

        low_price = source.get(
            "low",
            source.get("l"),
        )

        close_price = source.get(
            "close",
            source.get("c"),
        )

        tick_volume = source.get(
            "tick_volume",
            source.get("volume", 0),
        )

        volume = source.get(
            "volume",
            source.get(
                "real_volume",
                source.get(
                    "volume_real",
                    0.0,
                ),
            ),
        )

        spread = source.get(
            "spread",
            0,
        )

    else:

        timestamp = getattr(
            source,
            "time",
            None,
        )

        open_price = getattr(
            source,
            "open",
            None,
        )

        high_price = getattr(
            source,
            "high",
            None,
        )

        low_price = getattr(
            source,
            "low",
            None,
        )

        close_price = getattr(
            source,
            "close",
            None,
        )

        tick_volume = getattr(
            source,
            "tick_volume",
            getattr(
                source,
                "volume",
                0,
            ),
        )

        volume = getattr(
            source,
            "volume",
            getattr(
                source,
                "real_volume",
                0.0,
            ),
        )

        spread = getattr(
            source,
            "spread",
            0,
        )

    if timestamp is None:
        raise ValueError(
            "Candle missing time"
        )

    if open_price is None:
        raise ValueError(
            "Candle missing open"
        )

    if high_price is None:
        raise ValueError(
            "Candle missing high"
        )

    if low_price is None:
        raise ValueError(
            "Candle missing low"
        )

    if close_price is None:
        raise ValueError(
            "Candle missing close"
        )

    return {
        "time": _ensure_utc(timestamp),
        "timeframe": timeframe,
        "open": float(open_price),
        "high": float(high_price),
        "low": float(low_price),
        "close": float(close_price),
        "tick_volume": int(
            tick_volume or 0
        ),
        "volume": float(
            volume or 0.0
        ),
        "spread": int(
            spread or 0
        ),
    }


# ======================================================================
# BUCKET
# ======================================================================

def _bucket_start(
    timestamp: datetime,
    minutes: int,
) -> datetime:

    timestamp = _ensure_utc(
        timestamp
    )

    total_minutes = (
        timestamp.hour * 60
        + timestamp.minute
    )

    bucket_minutes = (
        total_minutes // minutes
    ) * minutes

    hour = bucket_minutes // 60
    minute = bucket_minutes % 60

    return timestamp.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


# ======================================================================
# AGGREGATION
# ======================================================================

def aggregate_candles(
    candles: Iterable,
    target_timeframe: str,
) -> List[Dict[str, Any]]:
    """
    Aggregate lower timeframe candles into a custom timeframe.
    """

    target_timeframe = (
        str(target_timeframe)
        .strip()
        .upper()
    )

    if not is_supported_timeframe(
        target_timeframe
    ):

        raise ValueError(
            f"Unsupported timeframe: "
            f"{target_timeframe}"
        )

    if is_native_timeframe(
        target_timeframe
    ):

        raise ValueError(
            f"{target_timeframe} is native. "
            "Retrieve it directly from MT5."
        )

    target_minutes = timeframe_to_minutes(
        target_timeframe
    )

    if target_minutes is None:

        raise ValueError(
            "MN1 cannot be aggregated using "
            "fixed-minute buckets."
        )

    normalized = []

    for candle in candles:

        normalized.append(
            _to_candle_dict(
                candle,
                target_timeframe,
            )
        )

    if not normalized:
        return []

    normalized.sort(
        key=lambda candle: candle["time"]
    )

    output = []

    current_bucket: Optional[
        datetime
    ] = None

    bucket = []

    for candle in normalized:

        bucket_time = _bucket_start(
            candle["time"],
            target_minutes,
        )

        if (
            current_bucket is not None
            and bucket_time != current_bucket
        ):

            output.append(
                _build_aggregated_candle(
                    bucket,
                    target_timeframe,
                    current_bucket,
                )
            )

            bucket = []

        current_bucket = bucket_time
        bucket.append(candle)

    if bucket:

        output.append(
            _build_aggregated_candle(
                bucket,
                target_timeframe,
                current_bucket,
            )
        )

    return output


# ======================================================================
# BUILD CANDLE
# ======================================================================

def _build_aggregated_candle(
    candles: List[Dict[str, Any]],
    timeframe: str,
    bucket_time: datetime,
) -> Dict[str, Any]:

    if not candles:

        raise ValueError(
            "Cannot aggregate empty candle bucket."
        )

    return {
        "time": bucket_time,
        "timeframe": timeframe,

        "open": candles[0]["open"],

        "high": max(
            candle["high"]
            for candle in candles
        ),

        "low": min(
            candle["low"]
            for candle in candles
        ),

        "close": candles[-1]["close"],

        "tick_volume": sum(
            candle["tick_volume"]
            for candle in candles
        ),

        "volume": sum(
            candle["volume"]
            for candle in candles
        ),

        "spread": max(
            candle["spread"]
            for candle in candles
        ),
    }


# ======================================================================
# ALIAS
# ======================================================================

def aggregate(
    candles: Iterable,
    target_timeframe: str,
) -> List[Dict[str, Any]]:

    return aggregate_candles(
        candles,
        target_timeframe,
    )


__all__ = [
    "aggregate_candles",
    "aggregate",
]