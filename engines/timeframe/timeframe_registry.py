"""
MT5 UNIVERSAL CONNECTOR
TIMEFRAME REGISTRY
======================================================================

Single authoritative registry for all supported timeframes.

Responsibilities:
    - Define every supported timeframe
    - Identify native MT5 timeframes
    - Identify custom/aggregated timeframes
    - Convert timeframe -> minutes
    - Validate timeframe names
    - Provide ordered timeframe lists

NO market data.
NO trading execution.
NO simulation.
"""

from __future__ import annotations


# ======================================================================
# NATIVE MT5 TIMEFRAMES
# ======================================================================

NATIVE_TIMEFRAMES = (
    "M1",
    "M5",
    "M15",
    "M30",
    "H1",
    "H4",
    "D1",
    "W1",
    "MN1",
)


# ======================================================================
# CUSTOM / AGGREGATED TIMEFRAMES
# ======================================================================

CUSTOM_TIMEFRAMES = (
    "M2",
    "M3",
    "M4",
    "M6",
    "M10",
    "M12",
    "M20",
    "H2",
    "H3",
    "H6",
    "H8",
    "H12",
)


# ======================================================================
# COMPLETE TIMEFRAME REGISTRY
# ======================================================================
#
# None = calendar-month timeframe.
#
# These values represent the duration of the timeframe in minutes.
#

TIMEFRAME_MINUTES = {

    # Minute
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
    "M6": 6,
    "M10": 10,
    "M12": 12,
    "M15": 15,
    "M20": 20,
    "M30": 30,

    # Hour
    "H1": 60,
    "H2": 120,
    "H3": 180,
    "H4": 240,
    "H6": 360,
    "H8": 480,
    "H12": 720,

    # Day
    "D1": 1440,

    # Week
    "W1": 10080,

    # Month
    "MN1": None,
}


# ======================================================================
# ORDERED TIMEFRAME LIST
# ======================================================================

ALL_TIMEFRAMES = tuple(TIMEFRAME_MINUTES.keys())


# ======================================================================
# TIMEFRAME GROUPS
# ======================================================================

MINUTE_TIMEFRAMES = (
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M10",
    "M12",
    "M15",
    "M20",
    "M30",
)

HOURLY_TIMEFRAMES = (
    "H1",
    "H2",
    "H3",
    "H4",
    "H6",
    "H8",
    "H12",
)

DAILY_TIMEFRAMES = (
    "D1",
)

WEEKLY_TIMEFRAMES = (
    "W1",
)

MONTHLY_TIMEFRAMES = (
    "MN1",
)


# ======================================================================
# LOOKUP FUNCTIONS
# ======================================================================

def normalize_timeframe(timeframe: str) -> str:
    """
    Normalize a timeframe string.

    Example:
        "m20" -> "M20"
        " h2 " -> "H2"
    """

    if not isinstance(timeframe, str):
        raise TypeError("timeframe must be a string")

    return timeframe.strip().upper()


def is_valid_timeframe(timeframe: str) -> bool:
    """Return True if timeframe is supported."""

    normalized = normalize_timeframe(timeframe)

    return normalized in TIMEFRAME_MINUTES


def timeframe_to_minutes(timeframe: str):
    """
    Convert timeframe to minutes.

    MN1 returns None because calendar months
    do not have a fixed number of minutes.
    """

    normalized = normalize_timeframe(timeframe)

    if normalized not in TIMEFRAME_MINUTES:
        raise ValueError(
            f"Unsupported timeframe: {timeframe}"
        )

    return TIMEFRAME_MINUTES[normalized]


def is_native_timeframe(timeframe: str) -> bool:
    """Return True if timeframe is natively supported by MT5."""

    normalized = normalize_timeframe(timeframe)

    return normalized in NATIVE_TIMEFRAMES


def is_custom_timeframe(timeframe: str) -> bool:
    """Return True if timeframe must be constructed/aggregated."""

    normalized = normalize_timeframe(timeframe)

    return normalized in CUSTOM_TIMEFRAMES


def timeframe_description(timeframe: str) -> str:
    """Return a human-readable timeframe description."""

    normalized = normalize_timeframe(timeframe)

    minutes = timeframe_to_minutes(normalized)

    if normalized == "MN1":
        return "calendar month"

    if minutes < 60:
        return f"{minutes} minute(s)"

    if minutes < 1440:
        hours = minutes // 60
        return f"{hours} hour(s)"

    if minutes == 1440:
        return "1 day"

    if minutes == 10080:
        return "1 week"

    return f"{minutes} minute(s)"


# ======================================================================
# REGISTRY INFORMATION
# ======================================================================

def registry_snapshot() -> dict:
    """
    Return a structured snapshot of the timeframe registry.
    """

    return {
        "all_timeframes": list(ALL_TIMEFRAMES),
        "native_timeframes": list(NATIVE_TIMEFRAMES),
        "custom_timeframes": list(CUSTOM_TIMEFRAMES),
        "minute_timeframes": list(MINUTE_TIMEFRAMES),
        "hourly_timeframes": list(HOURLY_TIMEFRAMES),
        "daily_timeframes": list(DAILY_TIMEFRAMES),
        "weekly_timeframes": list(WEEKLY_TIMEFRAMES),
        "monthly_timeframes": list(MONTHLY_TIMEFRAMES),
    }


# ======================================================================
# VALIDATION
# ======================================================================

def validate_registry() -> None:
    """
    Validate internal registry consistency.
    """

    # Every native timeframe must exist in registry.
    for timeframe in NATIVE_TIMEFRAMES:
        if timeframe not in TIMEFRAME_MINUTES:
            raise RuntimeError(
                f"Native timeframe missing from registry: {timeframe}"
            )

    # Every custom timeframe must exist in registry.
    for timeframe in CUSTOM_TIMEFRAMES:
        if timeframe not in TIMEFRAME_MINUTES:
            raise RuntimeError(
                f"Custom timeframe missing from registry: {timeframe}"
            )

    # No duplicate entries.
    if len(ALL_TIMEFRAMES) != len(set(ALL_TIMEFRAMES)):
        raise RuntimeError(
            "Duplicate timeframe detected."
        )


# Validate immediately when imported.
validate_registry()
def is_supported_timeframe(timeframe: str) -> bool:
    """
    Backward-compatible alias used by the Timeframe Engine.

    Returns True when the timeframe is registered.
    """
    return is_valid_timeframe(timeframe)