"""
MT5 UNIVERSAL CONNECTOR
PHASE 0 - CONNECTOR -> TIMEFRAME ENGINE

Integration test harness.

Purpose:
    1. Connect to real MT5 terminal.
    2. Detect connected trading environment.
    3. Resolve XAUUSD broker symbol.
    4. Read live tick.
    5. Read all native MT5 timeframes.
    6. Normalize historical candles.
    7. Test custom timeframe aggregation.
    8. Display final engine diagnostics.

READ-ONLY:
    No orders are sent.
    No positions are modified.
    No trading execution is performed.
"""

from __future__ import annotations

from typing import Any


from connector.mt5_connector import MT5Connector

from engines.timeframe.timeframe_engine import (
    TimeframeEngine,
)

from engines.timeframe.timeframe_aggregator import (
    aggregate,
)


# ======================================================================
# DISPLAY HELPERS
# ======================================================================

def line() -> None:
    print("=" * 70)


def print_candle(candle: Any) -> None:
    """
    Print a normalized timeframe-engine candle.

    TimeframeEngine currently returns dictionaries.
    This function deliberately supports both dictionaries
    and Candle-like objects so the integration layer remains robust.
    """

    if isinstance(candle, dict):

        timestamp = candle.get("time")
        timeframe = candle.get("timeframe", "")
        open_price = candle.get("open")
        high_price = candle.get("high")
        low_price = candle.get("low")
        close_price = candle.get("close")
        tick_volume = candle.get("tick_volume", 0)

    else:

        timestamp = getattr(candle, "time", None)
        timeframe = getattr(candle, "timeframe", "")
        open_price = getattr(candle, "open", None)
        high_price = getattr(candle, "high", None)
        low_price = getattr(candle, "low", None)
        close_price = getattr(candle, "close", None)
        tick_volume = getattr(
            candle,
            "tick_volume",
            0,
        )

    if hasattr(timestamp, "isoformat"):
        timestamp_text = timestamp.isoformat()
    else:
        timestamp_text = str(timestamp)

    print(
        f"{timestamp_text} | "
        f"{str(timeframe):<5} | "
        f"O={open_price} | "
        f"H={high_price} | "
        f"L={low_price} | "
        f"C={close_price} | "
        f"TV={tick_volume}"
    )


def get_value(
    obj: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Read a value from either a dictionary or object.
    """

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(
        obj,
        key,
        default,
    )


# ======================================================================
# MAIN
# ======================================================================

def main() -> None:

    line()
    print("MT5 UNIVERSAL CONNECTOR")
    print("PHASE 0 - CONNECTOR -> TIMEFRAME ENGINE")
    line()

    connector = MT5Connector()

    try:

        # ==============================================================
        # CONNECT
        # ==============================================================

        print()
        print("Connecting to MT5 terminal...")

        connector.connect()

        print("CONNECTION: ACTIVE")

        # ==============================================================
        # CONNECTED ENVIRONMENT
        # ==============================================================

        print()
        line()
        print("CONNECTED MT5 ENVIRONMENT")
        line()

        # Use connector's environment/status interfaces when available.
        status = None

        status_method = getattr(
            connector,
            "get_account_info",
            None,
        )

        if callable(status_method):

            try:
                status = status_method()
            except Exception:
                status = None

        if status is None:

            status_method = getattr(
                connector,
                "status",
                None,
            )

            if callable(status_method):

                try:
                    status = status_method()
                except Exception:
                    status = None

        if isinstance(status, dict):

            print(
                f"Broker       : "
                f"{status.get('broker', status.get('company', 'UNKNOWN'))}"
            )

            print(
                f"Server       : "
                f"{status.get('server', 'UNKNOWN')}"
            )

            print(
                f"Account Type : "
                f"{status.get('account_type', 'UNKNOWN')}"
            )

            print(
                f"Trade Allowed: "
                f"{status.get('trade_allowed', 'UNKNOWN')}"
            )

            print(
                f"Read Only    : "
                f"{status.get('read_only', 'UNKNOWN')}"
            )

            print(
                f"Execution    : "
                f"{status.get('execution_enabled', False)}"
            )

            print(
                f"Simulation   : "
                f"{status.get('simulation_enabled', False)}"
            )

        else:

            print(
                "Account/environment details "
                "are available through the connector."
            )

        # ==============================================================
        # TIMEFRAME ENGINE
        # ==============================================================

        engine = TimeframeEngine(
            connector=connector,
        )

        symbol = "XAUUSD"

        print()
        line()
        print("TIMEFRAME ENGINE")
        line()

        print(
            f"Engine Status : "
            f"{getattr(engine, 'initialized', 'UNKNOWN')}"
        )

        print(
            f"Mode          : "
            f"{getattr(engine, 'MODE', 'UNKNOWN')}"
        )

        print(
            f"Execution     : "
            f"{getattr(engine, 'EXECUTION_ENABLED', False)}"
        )

        print(
            f"Simulation    : "
            f"{getattr(engine, 'SIMULATION_ENABLED', False)}"
        )

        print(
            f"Requested     : "
            f"{symbol}"
        )

        resolved_symbol = getattr(
            engine,
            "resolve_symbol",
            None,
        )

        if callable(resolved_symbol):

            try:
                actual_symbol = resolved_symbol(symbol)
            except Exception:
                actual_symbol = symbol

        else:
            actual_symbol = symbol

        print(
            f"MT5 Symbol    : "
            f"{actual_symbol}"
        )

        # ==============================================================
        # CURRENT REAL MT5 TICK
        # ==============================================================

        print()
        line()
        print("CURRENT REAL MT5 TICK")
        line()

        tick = None

        tick_method = getattr(
            engine,
            "get_tick",
            None,
        )

        if callable(tick_method):

            try:
                tick = tick_method(symbol)
            except Exception:
                tick = None

        if tick is None:

            tick_method = getattr(
                connector,
                "get_tick",
                None,
            )

            if callable(tick_method):

                try:
                    tick = tick_method(actual_symbol)
                except Exception:
                    tick = None

        if tick is not None:

            timestamp = get_value(
                tick,
                "time",
                get_value(
                    tick,
                    "timestamp",
                    None,
                ),
            )

            if hasattr(timestamp, "isoformat"):
                timestamp = timestamp.isoformat()

            bid = get_value(
                tick,
                "bid",
                0.0,
            )

            ask = get_value(
                tick,
                "ask",
                0.0,
            )

            last = get_value(
                tick,
                "last",
                0.0,
            )

            spread = (
                float(ask) - float(bid)
            )

            mid = (
                float(bid) + float(ask)
            ) / 2.0

            print(
                f"Symbol        : "
                f"{actual_symbol}"
            )

            print(
                f"UTC Time      : "
                f"{timestamp}"
            )

            print(
                f"BID           : "
                f"{bid}"
            )

            print(
                f"ASK           : "
                f"{ask}"
            )

            print(
                f"LAST          : "
                f"{last}"
            )

            print(
                f"SPREAD        : "
                f"{spread}"
            )

            print(
                f"MID           : "
                f"{mid}"
            )

        else:

            print(
                "TICK DATA UNAVAILABLE"
            )

        # ==============================================================
        # NATIVE TIMEFRAMES
        # ==============================================================

        print()
        line()
        print("NATIVE MT5 TIMEFRAMES")
        line()

        native_timeframes = [
            "M1",
            "M5",
            "M15",
            "M30",
            "H1",
            "H4",
            "D1",
            "W1",
            "MN1",
        ]

        native_results = {}

        for timeframe in native_timeframes:

            try:

                candles = engine.get_candles(
                    symbol,
                    timeframe,
                    count=1,
                )

                native_results[timeframe] = candles

                if candles:

                    candle = candles[-1]

                    timestamp = get_value(
                        candle,
                        "time",
                    )

                    if hasattr(
                        timestamp,
                        "isoformat",
                    ):
                        timestamp = (
                            timestamp.isoformat()
                        )

                    print(
                        f"{timeframe:<5} PASS | "
                        f"O={get_value(candle, 'open')} "
                        f"H={get_value(candle, 'high')} "
                        f"L={get_value(candle, 'low')} "
                        f"C={get_value(candle, 'close')} "
                        f"TIME={timestamp}"
                    )

                else:

                    print(
                        f"{timeframe:<5} FAIL | "
                        f"No candle returned"
                    )

            except Exception as exc:

                print(
                    f"{timeframe:<5} FAIL | "
                    f"{type(exc).__name__}: {exc}"
                )

        # ==============================================================
        # HISTORICAL MULTI-TIMEFRAME DATA
        # ==============================================================

        print()
        line()
        print("MULTI-TIMEFRAME HISTORICAL DATA")
        line()

        test_timeframes = [
            "M1",
            "M5",
            "M15",
            "M30",
            "H1",
            "H4",
            "D1",
            "W1",
            "MN1",
        ]

        for timeframe in test_timeframes:

            print()
            print(f"--- {timeframe} ---")

            try:

                candles = engine.get_candles(
                    symbol,
                    timeframe,
                    count=3,
                )

                if not candles:

                    print("NO DATA")
                    continue

                for candle in candles:
                    print_candle(candle)

            except Exception as exc:

                print(
                    f"ERROR {symbol} "
                    f"{timeframe}: "
                    f"{type(exc).__name__}: {exc}"
                )

        # ==============================================================
        # CUSTOM M20
        # ==============================================================

        print()
        line()
        print("CUSTOM TIMEFRAME AGGREGATION")
        line()

        print()
        print("Testing M20 from M1 data...")

        try:

            m1 = engine.get_native_candles(
                symbol,
                "M1",
                count=120,
            )

            m20 = aggregate(
                m1,
                "M20",
            )

            print(
                f"M1 candles received : "
                f"{len(m1)}"
            )

            print(
                f"M20 candles created  : "
                f"{len(m20)}"
            )

            for candle in m20[-3:]:

                print_candle(candle)

        except Exception as exc:

            print("M20 TEST FAILED")
            print(
                f"{type(exc).__name__}: {exc}"
            )

        # ==============================================================
        # CUSTOM H2
        # ==============================================================

        print()
        print("Testing H2 from H1 data...")

        try:

            h1 = engine.get_native_candles(
                symbol,
                "H1",
                count=48,
            )

            h2 = aggregate(
                h1,
                "H2",
            )

            print(
                f"H1 candles received : "
                f"{len(h1)}"
            )

            print(
                f"H2 candles created  : "
                f"{len(h2)}"
            )

            for candle in h2[-3:]:

                print_candle(candle)

        except Exception as exc:

            print("H2 TEST FAILED")
            print(
                f"{type(exc).__name__}: {exc}"
            )

        # ==============================================================
        # ENGINE STATUS
        # ==============================================================

        print()
        line()
        print("TIMEFRAME ENGINE STATUS")
        line()

        engine.print_status()

        # ==============================================================
        # REGISTRY
        # ==============================================================

        engine.print_registry()

        # ==============================================================
        # FINAL
        # ==============================================================

        print()
        line()
        print("PHASE 0 TIMEFRAME ENGINE")
        print("CONNECTOR INTEGRATION TEST COMPLETE")
        line()

        print()
        print("SOURCE        : REAL MT5 MARKET DATA")
        print("CONNECTION    : MT5Connector")
        print("TIMEFRAME     : TimeframeEngine")
        print("MODE          : READ-ONLY")
        print("EXECUTION     : DISABLED")
        print("SIMULATION    : DISABLED")

    except KeyboardInterrupt:

        print()
        print("TEST INTERRUPTED BY USER")

    except Exception as exc:

        print()
        print("TIMEFRAME ENGINE TEST FAILED")
        print(
            f"{type(exc).__name__}: {exc}"
        )

    finally:

        try:
            connector.disconnect()
        except Exception:
            pass

        print()
        print("MT5 CONNECTION CLOSED.")
        line()


# ======================================================================
# ENTRY POINT
# ======================================================================

if __name__ == "__main__":
    main()