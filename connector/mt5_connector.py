"""
MT5 UNIVERSAL CONNECTOR
PHASE 0 - MT5 CONNECTION FOUNDATION

Responsibilities:
    - Connect to the local MetaTrader 5 terminal
    - Detect account/environment
    - Resolve broker-specific symbols
    - Read live tick data
    - Read historical OHLC candles
    - Provide connection status to higher-level engines
    - READ-ONLY foundation
    - NO trade execution
    - NO simulation
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import MetaTrader5 as mt5


class MT5Connector:
    """
    Central MT5 connection layer.

    Higher-level engines should communicate with MT5 through this
    connector rather than calling MetaTrader5 directly whenever possible.
    """

    ENGINE_NAME = "MT5 Universal Connector"
    VERSION = "1.1.0"

    READ_ONLY = True
    EXECUTION_ENABLED = False
    SIMULATION_ENABLED = False

    def __init__(self) -> None:
        self.connected: bool = False
        self.initialized: bool = False

        self.last_error: Optional[Any] = None

        self.broker: Optional[str] = None
        self.server: Optional[str] = None
        self.terminal: Optional[str] = None
        self.build: Optional[int] = None

        self.account_login: Optional[int] = None
        self.account_currency: Optional[str] = None
        self.account_balance: Optional[float] = None
        self.account_equity: Optional[float] = None
        self.account_leverage: Optional[int] = None
        self.account_trade_allowed: Optional[bool] = None
        self.account_type: Optional[str] = None

    # ==================================================================
    # CONNECTION
    # ==================================================================

    def connect(self) -> bool:
        """
        Initialize the MT5 Python connection.

        Returns:
            True if connected successfully.
            False otherwise.
        """

        if self.connected:
            return True

        try:
            result = mt5.initialize()

            if not result:
                self.last_error = mt5.last_error()
                self.connected = False
                self.initialized = False
                return False

            self.initialized = True

            terminal = mt5.terminal_info()
            account = mt5.account_info()

            if terminal is None or account is None:
                self.last_error = mt5.last_error()
                mt5.shutdown()

                self.connected = False
                self.initialized = False

                return False

            self.broker = terminal.company
            self.server = account.server
            self.terminal = terminal.name
            self.build = terminal.build

            self.account_login = account.login
            self.account_currency = account.currency
            self.account_balance = account.balance
            self.account_equity = account.equity
            self.account_leverage = account.leverage
            self.account_trade_allowed = account.trade_allowed

            self.account_type = self._detect_account_type(
                account.server
            )

            self.connected = True
            self.last_error = None

            return True

        except Exception as exc:

            self.last_error = str(exc)
            self.connected = False
            self.initialized = False

            return False

    # ==================================================================
    # DISCONNECT
    # ==================================================================

    def disconnect(self) -> None:
        """
        Close the MT5 connection.
        """

        if self.initialized:
            try:
                mt5.shutdown()
            except Exception:
                pass

        self.connected = False
        self.initialized = False

    # ==================================================================
    # STATUS
    # ==================================================================

    def status(self) -> Dict[str, Any]:
        """
        Return complete connector status.

        This method is consumed by higher-level engines such as the
        Timeframe Engine.
        """

        return {
            "connector": self.ENGINE_NAME,
            "version": self.VERSION,

            "connected": self.connected,
            "initialized": self.initialized,

            "broker": self.broker,
            "server": self.server,
            "terminal": self.terminal,
            "build": self.build,

            "account_login": self.account_login,
            "account_currency": self.account_currency,
            "account_type": self.account_type,

            "balance": self.account_balance,
            "equity": self.account_equity,
            "leverage": self.account_leverage,
            "trade_allowed": self.account_trade_allowed,

            "read_only": self.READ_ONLY,
            "execution_enabled": self.EXECUTION_ENABLED,
            "simulation_enabled": self.SIMULATION_ENABLED,

            "last_error": self.last_error,
        }

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def validate(self, symbol: str = "XAUUSD") -> Dict[str, Any]:
        """
        Validate MT5 connection and resolve a broker-specific symbol.
        """

        if not self.connected:
            if not self.connect():
                return {
                    "connector": self.ENGINE_NAME,
                    "version": self.VERSION,
                    "connected": False,
                    "symbol_available": False,
                    "requested_symbol": symbol,
                    "resolved_symbol": None,
                    "error": self.last_error,
                }

        resolved = self.resolve_symbol(symbol)

        return {
            "connector": self.ENGINE_NAME,
            "version": self.VERSION,

            "connected": self.connected,

            "broker": self.broker,
            "server": self.server,

            "account_type": self.account_type,
            "trade_allowed": self.account_trade_allowed,

            "read_only": self.READ_ONLY,
            "execution_enabled": self.EXECUTION_ENABLED,
            "simulation_enabled": self.SIMULATION_ENABLED,

            "requested_symbol": symbol,
            "resolved_symbol": resolved,
            "symbol_available": resolved is not None,
        }

    # ==================================================================
    # SYMBOL RESOLUTION
    # ==================================================================

    def resolve_symbol(
        self,
        requested_symbol: str,
    ) -> Optional[str]:
        """
        Resolve a requested symbol against symbols available in MT5.

        Example:

            XAUUSD
                ->
            XAUUSD...
        """

        if not requested_symbol:
            return None

        requested = requested_symbol.strip().upper()

        # --------------------------------------------------------------
        # Direct match
        # --------------------------------------------------------------

        info = mt5.symbol_info(requested)

        if info is not None:
            if not info.visible:
                mt5.symbol_select(requested, True)

            return requested

        # --------------------------------------------------------------
        # Search available symbols
        # --------------------------------------------------------------

        symbols = mt5.symbols_get()

        if symbols is None:
            self.last_error = mt5.last_error()
            return None

        candidates = []

        for item in symbols:

            name = item.name.upper()

            if name == requested:
                candidates.append(item.name)
                continue

            if name.startswith(requested):
                candidates.append(item.name)
                continue

            if requested in name:
                candidates.append(item.name)

        if not candidates:
            return None

        # Prefer shortest match.
        candidates.sort(key=len)

        resolved = candidates[0]

        mt5.symbol_select(resolved, True)

        return resolved

    # ==================================================================
    # LIVE TICK
    # ==================================================================

    def get_tick(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Read the current live MT5 tick.
        """

        if not self.connected:
            if not self.connect():
                return None

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return None

        tick = mt5.symbol_info_tick(resolved)

        if tick is None:
            self.last_error = mt5.last_error()
            return None

        tick_time = datetime.fromtimestamp(
            tick.time,
            tz=timezone.utc,
        )

        bid = float(tick.bid)
        ask = float(tick.ask)

        mid = None

        if bid and ask:
            mid = (bid + ask) / 2.0

        spread = None

        if bid and ask:
            spread = ask - bid

        return {
            "symbol": resolved,

            "time": tick_time,
            "time_msc": getattr(
                tick,
                "time_msc",
                None,
            ),

            "bid": bid,
            "ask": ask,
            "last": float(tick.last),

            "volume": int(tick.volume),
            "volume_real": float(
                getattr(
                    tick,
                    "volume_real",
                    0.0,
                )
            ),

            "spread": spread,
            "mid": mid,
        }

    # ==================================================================
    # HISTORICAL RATES
    # ==================================================================

    def _normalize_mt5_timeframe(
        self,
        timeframe: Any,
    ) -> Optional[int]:
        """
        Convert a human-readable timeframe or an existing MT5
        timeframe constant into the integer constant required by
        the MetaTrader5 Python API.

        Accepted examples:

            "M1"
            "M5"
            "M15"
            "M30"
            "H1"
            "H4"
            "D1"
            "W1"
            "MN1"

        Existing integer MT5 constants are also accepted.

        This method performs no market-data generation.
        """

        if timeframe is None:
            self.last_error = (
                -2,
                "Timeframe cannot be None.",
            )
            return None

        # Already an MT5 timeframe constant.
        if isinstance(timeframe, int):
            return timeframe

        if not isinstance(timeframe, str):
            self.last_error = (
                -2,
                f"Unsupported timeframe type: "
                f"{type(timeframe).__name__}",
            )
            return None

        value = timeframe.strip().upper()

        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M2": mt5.TIMEFRAME_M2,
            "M3": mt5.TIMEFRAME_M3,
            "M4": mt5.TIMEFRAME_M4,
            "M5": mt5.TIMEFRAME_M5,
            "M6": mt5.TIMEFRAME_M6,
            "M10": mt5.TIMEFRAME_M10,
            "M12": mt5.TIMEFRAME_M12,
            "M15": mt5.TIMEFRAME_M15,
            "M20": mt5.TIMEFRAME_M20,
            "M30": mt5.TIMEFRAME_M30,

            "H1": mt5.TIMEFRAME_H1,
            "H2": mt5.TIMEFRAME_H2,
            "H3": mt5.TIMEFRAME_H3,
            "H4": mt5.TIMEFRAME_H4,
            "H6": mt5.TIMEFRAME_H6,
            "H8": mt5.TIMEFRAME_H8,
            "H12": mt5.TIMEFRAME_H12,

            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }

        normalized = timeframe_map.get(value)

        if normalized is None:
            self.last_error = (
                -2,
                f"Unsupported MT5 timeframe: {value}",
            )
            return None

        return normalized

    def get_rates(
        self,
        symbol: str,
        timeframe: Any,
        count: int = 100,
    ) -> Optional[Any]:
        """
        Retrieve real historical MT5 rates.

        The public interface accepts either:

            - human-readable timeframe strings, e.g. "M1"
            - native MT5 integer timeframe constants

        The conversion to the MT5 API constant happens inside
        the connector layer.

        READ-ONLY:
            This method only reads market data.
            It never places, modifies, or closes trades.
        """

        if not self.connected:
            if not self.connect():
                return None

        if not isinstance(count, int) or count <= 0:
            self.last_error = (
                -2,
                "Historical candle count must be a positive integer.",
            )
            return None

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return None

        mt5_timeframe = self._normalize_mt5_timeframe(
            timeframe
        )

        if mt5_timeframe is None:
            return None

        try:

            rates = mt5.copy_rates_from_pos(
                resolved,
                mt5_timeframe,
                0,
                count,
            )

        except Exception as exc:

            self.last_error = mt5.last_error()

            if not self.last_error or self.last_error[0] == 1:
                self.last_error = (
                    -1,
                    f"{type(exc).__name__}: {exc}",
                )

            return None

        if rates is None:

            self.last_error = mt5.last_error()

            return None

        # Successful request.
        self.last_error = mt5.last_error()

        return rates

    # ==================================================================
    # HISTORICAL RATES BY DATE
    # ==================================================================

    def get_rates_range(
        self,
        symbol: str,
        timeframe: Any,
        start: datetime,
        end: datetime,
    ) -> Optional[Any]:
        """
        Retrieve real historical MT5 candles between two UTC
        timestamps.

        Accepts either a human-readable timeframe such as "M1"
        or a native MT5 timeframe integer.

        READ-ONLY.
        """

        if not self.connected:
            if not self.connect():
                return None

        if not isinstance(start, datetime):
            self.last_error = (
                -2,
                "start must be a datetime.",
            )
            return None

        if not isinstance(end, datetime):
            self.last_error = (
                -2,
                "end must be a datetime.",
            )
            return None

        if start.tzinfo is None:
            start = start.replace(
                tzinfo=timezone.utc
            )
        else:
            start = start.astimezone(
                timezone.utc
            )

        if end.tzinfo is None:
            end = end.replace(
                tzinfo=timezone.utc
            )
        else:
            end = end.astimezone(
                timezone.utc
            )

        if end <= start:
            self.last_error = (
                -2,
                "end must be later than start.",
            )
            return None

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return None

        mt5_timeframe = self._normalize_mt5_timeframe(
            timeframe
        )

        if mt5_timeframe is None:
            return None

        try:

            rates = mt5.copy_rates_range(
                resolved,
                mt5_timeframe,
                start,
                end,
            )

        except Exception as exc:

            self.last_error = mt5.last_error()

            if not self.last_error or self.last_error[0] == 1:
                self.last_error = (
                    -1,
                    f"{type(exc).__name__}: {exc}",
                )

            return None

        if rates is None:

            self.last_error = mt5.last_error()

            return None

        self.last_error = mt5.last_error()

        return rates

    # ==================================================================
    # SYMBOL INFORMATION
    # ==================================================================

    def get_symbol_info(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Return important broker symbol metadata.
        """

        if not self.connected:
            if not self.connect():
                return None

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return None

        info = mt5.symbol_info(resolved)

        if info is None:
            self.last_error = mt5.last_error()
            return None

        return {
            "requested_symbol": symbol,
            "resolved_symbol": resolved,

            "description": info.description,

            "digits": info.digits,
            "point": info.point,

            "trade_contract_size":
                info.trade_contract_size,

            "volume_min":
                info.volume_min,

            "volume_max":
                info.volume_max,

            "volume_step":
                info.volume_step,

            "visible":
                info.visible,

            "trade_mode":
                info.trade_mode,
        }

    # ==================================================================
    # ACCOUNT INFORMATION
    # ==================================================================

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Read current account information.
        """

        if not self.connected:
            if not self.connect():
                return None

        account = mt5.account_info()

        if account is None:
            self.last_error = mt5.last_error()
            return None

        # Refresh cached values.

        self.account_login = account.login
        self.account_currency = account.currency
        self.account_balance = account.balance
        self.account_equity = account.equity
        self.account_leverage = account.leverage
        self.account_trade_allowed = account.trade_allowed

        return {
            "login": account.login,
            "server": account.server,
            "currency": account.currency,

            "balance": account.balance,
            "equity": account.equity,
            "profit": account.profit,

            "margin": account.margin,
            "margin_free": account.margin_free,

            "leverage": account.leverage,

            "trade_allowed":
                account.trade_allowed,
        }

    # ==================================================================
    # ACCOUNT TYPE
    # ==================================================================

    @staticmethod
    def _detect_account_type(
        server: Optional[str],
    ) -> str:
        """
        Best-effort account environment classification.

        This does not claim that every broker names servers using
        DEMO/LIVE. It is therefore deliberately conservative.
        """

        if not server:
            return "UNKNOWN"

        value = server.upper()

        demo_markers = (
            "DEMO",
            "DEMO-",
            "-DEMO",
            "TEST",
            "PRACTICE",
        )

        for marker in demo_markers:

            if marker in value:
                return "DEMO"

        return "LIVE_OR_UNKNOWN"

    # ==================================================================
    # CONNECTION CHECK
    # ==================================================================

    def is_connected(self) -> bool:
        """
        Simple connection state check.
        """

        if not self.connected:
            return False

        terminal = mt5.terminal_info()

        if terminal is None:
            self.connected = False
            self.last_error = mt5.last_error()
            return False

        return bool(terminal.connected)

    # ==================================================================
    # DISPLAY
    # ==================================================================

    def print_status(self) -> None:
        """
        Print connector status.
        """

        status = self.status()

        print()
        print("=" * 70)
        print("MT5 CONNECTOR STATUS")
        print("=" * 70)

        print(
            f"Connector       : "
            f"{status['connector']}"
        )

        print(
            f"Version         : "
            f"{status['version']}"
        )

        print(
            f"Connected       : "
            f"{status['connected']}"
        )

        print(
            f"Broker          : "
            f"{status['broker']}"
        )

        print(
            f"Server          : "
            f"{status['server']}"
        )

        print(
            f"Terminal        : "
            f"{status['terminal']}"
        )

        print(
            f"Build           : "
            f"{status['build']}"
        )

        print(
            f"Account         : "
            f"{status['account_login']}"
        )

        print(
            f"Account Type    : "
            f"{status['account_type']}"
        )

        print(
            f"Currency        : "
            f"{status['account_currency']}"
        )

        print(
            f"Balance         : "
            f"{status['balance']}"
        )

        print(
            f"Equity          : "
            f"{status['equity']}"
        )

        print(
            f"Leverage        : "
            f"1:{status['leverage']}"
        )

        print(
            f"Trade Allowed   : "
            f"{status['trade_allowed']}"
        )

        print(
            f"Read Only       : "
            f"{status['read_only']}"
        )

        print(
            f"Execution       : "
            f"{status['execution_enabled']}"
        )

        print(
            f"Simulation      : "
            f"{status['simulation_enabled']}"
        )

        print("=" * 70)


__all__ = [
    "MT5Connector",
]