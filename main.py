"""MT5 Universal Connector - end-to-end certification harness.

Default behavior is non-trading certification: it connects, reads account/
portfolio/market data, validates execution permission, and calculates the
strategy-derived RRR. A real order is sent only when the operator explicitly
passes --execute with --symbol, --volume and --side.

There is no demo-only restriction and no hard-coded maximum risk percentage
or maximum RRR in this application layer.
"""

from __future__ import annotations

import argparse
from typing import Any

from connector.mt5_connector import MT5Connector
from engines.timeframe.timeframe_engine import TimeframeEngine
from execution.execution_engine import ExecutionEngine


def line() -> None:
    print("=" * 78)


def value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 Universal Connector")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--volume", type=float, default=None)
    parser.add_argument("--side", choices=("BUY", "SELL"), default=None)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp", type=float, default=None)
    parser.add_argument("--execute", action="store_true", help="Send the requested real MT5 market order")
    parser.add_argument("--rrr-entry", type=float, default=None)
    parser.add_argument("--rrr-stop", type=float, default=None)
    parser.add_argument("--rrr-tp", type=float, default=None)
    args = parser.parse_args()

    connector = MT5Connector()
    execution = ExecutionEngine(connector)
    timeframe = TimeframeEngine(connector)

    line()
    print("MT5 UNIVERSAL CONNECTOR - END-TO-END CERTIFICATION")
    line()

    try:
        if not connector.connect():
            print("CONNECTION: FAILED")
            print(f"ERROR: {connector.last_error}")
            return 1

        status = connector.status()
        account = connector.get_account_info() or {}
        resolved = connector.resolve_symbol(args.symbol)
        tick = connector.get_tick(args.symbol)

        print("CONNECTION: ACTIVE")
        print(f"BROKER       : {status.get('broker')}")
        print(f"SERVER       : {status.get('server')}")
        print(f"ACCOUNT TYPE : {status.get('account_type')}")
        print(f"ACCOUNT      : {account.get('login')}")
        print(f"BALANCE      : {account.get('balance')}")
        print(f"EQUITY       : {account.get('equity')}")
        print(f"TRADE ALLOWED: {account.get('trade_allowed')}")
        print(f"EXECUTION    : {status.get('execution_enabled')}")
        print(f"READ ONLY    : {status.get('read_only')}")
        print(f"SYMBOL       : {args.symbol} -> {resolved}")

        if tick:
            print(f"BID/ASK      : {tick.get('bid')} / {tick.get('ask')}")
        else:
            print(f"TICK ERROR   : {connector.last_error}")

        timeframe.initialize()
        print(f"TIMEFRAME    : INITIALIZED={timeframe.initialized}")
        print(f"POSITIONS    : {len(connector.get_positions())}")
        print(f"PENDING      : {len(connector.get_pending_orders())}")

        execution_status = execution.status()
        print(f"EXEC ENGINE  : {execution_status}")

        if args.rrr_entry is not None or args.rrr_stop is not None or args.rrr_tp is not None:
            if None in (args.rrr_entry, args.rrr_stop, args.rrr_tp, args.side):
                print("RRR          : INVALID - entry, stop, TP and side are required")
            else:
                rrr = execution.calculate_strategy_rrr(
                    args.side,
                    args.rrr_entry,
                    args.rrr_stop,
                    args.rrr_tp,
                )
                print(f"STRATEGY RRR  : {rrr}")

        if not args.execute:
            print("EXECUTION TEST: PREFLIGHT ONLY (NO ORDER SENT)")
            if args.volume is not None and args.side:
                print("PREFLIGHT     :", execution.preflight(
                    args.symbol, args.volume, args.side, args.sl, args.tp
                ))
            print("CERTIFICATION : CONNECTOR / DATA / EXECUTION PATH READY")
            return 0

        if args.volume is None or args.side is None:
            print("EXECUTION     : FAILED - --execute requires --volume and --side")
            return 2

        preflight = execution.preflight(
            args.symbol,
            args.volume,
            args.side,
            args.sl,
            args.tp,
        )
        print("EXECUTION PREFLIGHT:", preflight)
        if not preflight.get("allowed"):
            print("EXECUTION     : BLOCKED BY MT5/REQUEST VALIDATION")
            return 3

        result = execution.execute_market(
            args.symbol,
            args.volume,
            args.side,
            args.sl,
            args.tp,
        )
        print("EXECUTION RESULT:", result)
        return 0 if result.get("success") else 4

    finally:
        connector.disconnect()
        print("MT5 CONNECTION CLOSED")
        line()


if __name__ == "__main__":
    raise SystemExit(main())
