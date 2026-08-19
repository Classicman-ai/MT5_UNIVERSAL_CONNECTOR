"""
MT5 UNIVERSAL CONNECTOR
PHASE 0 - MT5 CONNECTION + MARKET DATA + EXECUTION

Responsibilities:
    - Connect to the local MetaTrader 5 terminal
    - Detect account/environment
    - Resolve broker-specific symbols
    - Read live tick data
    - Read historical OHLC candles
    - Read account information
    - Read positions and pending orders
    - Execute market orders
    - Modify positions
    - Close positions
    - Create/cancel pending orders
    - Provide execution results and broker retcodes
    - Support both DEMO and LIVE accounts
    - Keep simulation separate from real MT5 execution

IMPORTANT:
    Connecting does NOT execute a trade.

    Real execution occurs only when one of the explicit execution
    methods is called.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import MetaTrader5 as mt5


class MT5Connector:
    """
    Central MT5 connection and execution layer.

    Higher-level engines should communicate with MT5 through this
    connector instead of calling MetaTrader5 directly.
    """

    ENGINE_NAME = "MT5 Universal Connector"
    VERSION = "2.0.0-PHASE0"

    # --------------------------------------------------------------
    # CAPABILITIES
    # --------------------------------------------------------------

    READ_ONLY = False
    EXECUTION_ENABLED = True
    SIMULATION_ENABLED = False

    SUPPORTED_ACCOUNT_TYPES = (
        "DEMO",
        "LIVE",
        "LIVE_OR_UNKNOWN",
        "UNKNOWN",
    )

    def __init__(self) -> None:
        self.connected: bool = False
        self.initialized: bool = False

        self.last_error: Optional[Any] = None
        self.last_execution: Optional[Dict[str, Any]] = None

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

    # ==============================================================
    # CONNECTION
    # ==============================================================

    def connect(self) -> bool:
        """Initialize and validate the MT5 terminal connection."""

        if self.connected and self.is_connected():
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

            self.broker = getattr(terminal, "company", None)
            self.server = getattr(account, "server", None)
            self.terminal = getattr(terminal, "name", None)
            self.build = getattr(terminal, "build", None)

            self._refresh_account(account)

            self.account_type = self._detect_account_type(
                self.server
            )

            self.connected = bool(
                getattr(terminal, "connected", True)
            )

            self.last_error = None

            return self.connected

        except Exception as exc:
            self.last_error = (
                -1,
                f"{type(exc).__name__}: {exc}",
            )

            self.connected = False
            self.initialized = False

            return False

    # ==============================================================
    # DISCONNECT
    # ==============================================================

    def disconnect(self) -> None:
        """Close the MT5 Python connection."""

        if self.initialized:
            try:
                mt5.shutdown()
            except Exception:
                pass

        self.connected = False
        self.initialized = False

    # ==============================================================
    # ACCOUNT REFRESH
    # ==============================================================

    def _refresh_account(self, account: Any) -> None:
        self.account_login = getattr(account, "login", None)
        self.account_currency = getattr(account, "currency", None)
        self.account_balance = getattr(account, "balance", None)
        self.account_equity = getattr(account, "equity", None)
        self.account_leverage = getattr(account, "leverage", None)
        self.account_trade_allowed = getattr(
            account,
            "trade_allowed",
            None,
        )

    # ==============================================================
    # STATUS
    # ==============================================================

    def status(self) -> Dict[str, Any]:
        """Return complete connector status."""

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
            "last_execution": self.last_execution,
        }

    # ==============================================================
    # VALIDATION
    # ==============================================================

    def validate(self, symbol: str = "XAUUSD") -> Dict[str, Any]:
        """Validate connection, account and requested symbol."""

        if not self.connected:
            if not self.connect():
                return {
                    "connector": self.ENGINE_NAME,
                    "version": self.VERSION,
                    "connected": False,
                    "symbol_available": False,
                    "requested_symbol": symbol,
                    "resolved_symbol": None,
                    "execution_enabled": self.EXECUTION_ENABLED,
                    "simulation_enabled": self.SIMULATION_ENABLED,
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

    # ==============================================================
    # SYMBOL RESOLUTION
    # ==============================================================

    def resolve_symbol(
        self,
        requested_symbol: str,
    ) -> Optional[str]:
        """Resolve a requested symbol against broker symbols."""

        if not requested_symbol:
            return None

        requested = requested_symbol.strip().upper()

        info = mt5.symbol_info(requested)

        if info is not None:
            if not info.visible:
                mt5.symbol_select(requested, True)

            return requested

        symbols = mt5.symbols_get()

        if symbols is None:
            self.last_error = mt5.last_error()
            return None

        candidates = []

        for item in symbols:
            name = item.name.upper()

            if name == requested:
                candidates.append(item.name)
            elif name.startswith(requested):
                candidates.append(item.name)
            elif requested in name:
                candidates.append(item.name)

        if not candidates:
            return None

        candidates.sort(key=len)

        resolved = candidates[0]

        if not mt5.symbol_select(resolved, True):
            self.last_error = mt5.last_error()
            return None

        return resolved

    # ==============================================================
    # LIVE TICK
    # ==============================================================

    def get_tick(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:
        """Read the current live MT5 tick."""

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
        spread = None

        if bid and ask:
            mid = (bid + ask) / 2.0
            spread = ask - bid

        return {
            "symbol": resolved,
            "time": tick_time,
            "time_msc": getattr(tick, "time_msc", None),
            "bid": bid,
            "ask": ask,
            "last": float(getattr(tick, "last", 0.0)),
            "volume": int(getattr(tick, "volume", 0)),
            "volume_real": float(
                getattr(tick, "volume_real", 0.0)
            ),
            "spread": spread,
            "mid": mid,
        }

    # ==============================================================
    # TIMEFRAME NORMALIZATION
    # ==============================================================

    def _normalize_mt5_timeframe(
        self,
        timeframe: Any,
    ) -> Optional[int]:

        if timeframe is None:
            self.last_error = (
                -2,
                "Timeframe cannot be None.",
            )
            return None

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

    # ==============================================================
    # HISTORICAL RATES
    # ==============================================================

    def get_rates(
        self,
        symbol: str,
        timeframe: Any,
        count: int = 100,
    ) -> Optional[Any]:
        """Retrieve historical MT5 rates."""

        if not self.connected:
            if not self.connect():
                return None

        if not isinstance(count, int) or count <= 0:
            self.last_error = (
                -2,
                "Historical candle count must be positive.",
            )
            return None

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return None

        mt5_timeframe = self._normalize_mt5_timeframe(timeframe)

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
            self.last_error = (
                -1,
                f"{type(exc).__name__}: {exc}",
            )
            return None

        if rates is None:
            self.last_error = mt5.last_error()
            return None

        self.last_error = None

        return rates

    # ==============================================================
    # HISTORICAL RANGE
    # ==============================================================

    def get_rates_range(
        self,
        symbol: str,
        timeframe: Any,
        start: datetime,
        end: datetime,
    ) -> Optional[Any]:
        """Retrieve historical candles between two UTC timestamps."""

        if not self.connected:
            if not self.connect():
                return None

        if not isinstance(start, datetime):
            self.last_error = (-2, "start must be datetime.")
            return None

        if not isinstance(end, datetime):
            self.last_error = (-2, "end must be datetime.")
            return None

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        else:
            start = start.astimezone(timezone.utc)

        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)

        if end <= start:
            self.last_error = (
                -2,
                "end must be later than start.",
            )
            return None

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return None

        mt5_timeframe = self._normalize_mt5_timeframe(timeframe)

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
            self.last_error = (
                -1,
                f"{type(exc).__name__}: {exc}",
            )
            return None

        if rates is None:
            self.last_error = mt5.last_error()
            return None

        self.last_error = None

        return rates

    # ==============================================================
    # SYMBOL INFORMATION
    # ==============================================================

    def get_symbol_info(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:

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

            "trade_contract_size": info.trade_contract_size,

            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,

            "visible": info.visible,
            "trade_mode": info.trade_mode,

            "trade_tick_size": getattr(
                info,
                "trade_tick_size",
                None,
            ),

            "trade_tick_value": getattr(
                info,
                "trade_tick_value",
                None,
            ),

            "filling_mode": getattr(
                info,
                "filling_mode",
                None,
            ),

            "order_mode": getattr(
                info,
                "order_mode",
                None,
            ),
        }

    # ==============================================================
    # ACCOUNT INFORMATION
    # ==============================================================

    def get_account_info(self) -> Optional[Dict[str, Any]]:

        if not self.connected:
            if not self.connect():
                return None

        account = mt5.account_info()

        if account is None:
            self.last_error = mt5.last_error()
            return None

        self._refresh_account(account)

        return {
            "login": account.login,
            "server": account.server,
            "currency": account.currency,

            "balance": account.balance,
            "equity": account.equity,
            "profit": account.profit,

            "margin": account.margin,
            "margin_free": account.margin_free,
            "margin_level": getattr(
                account,
                "margin_level",
                None,
            ),

            "leverage": account.leverage,

            "trade_allowed": account.trade_allowed,
            "trade_expert": getattr(
                account,
                "trade_expert",
                None,
            ),

            "account_type": self.account_type,
        }

    # ==============================================================
    # ACCOUNT TYPE
    # ==============================================================

    @staticmethod
    def _detect_account_type(
        server: Optional[str],
    ) -> str:

        if not server:
            return "UNKNOWN"

        value = server.upper()

        demo_markers = (
            "DEMO",
            "TEST",
            "PRACTICE",
        )

        for marker in demo_markers:
            if marker in value:
                return "DEMO"

        live_markers = (
            "LIVE",
            "REAL",
        )

        for marker in live_markers:
            if marker in value:
                return "LIVE"

        return "LIVE_OR_UNKNOWN"

    # ==============================================================
    # CONNECTION CHECK
    # ==============================================================

    def is_connected(self) -> bool:

        if not self.connected:
            return False

        terminal = mt5.terminal_info()

        if terminal is None:
            self.connected = False
            self.last_error = mt5.last_error()
            return False

        self.connected = bool(
            getattr(terminal, "connected", False)
        )

        return self.connected

    # ==============================================================
    # EXECUTION PRE-FLIGHT
    # ==============================================================

    def execution_preflight(
        self,
        symbol: str,
        volume: float,
        order_type: str = "BUY",
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validate an execution request without sending an order.

        This method NEVER places a trade.
        """

        if not self.EXECUTION_ENABLED:
            return {
                "allowed": False,
                "reason": "EXECUTION_DISABLED",
            }

        if not self.connected:
            if not self.connect():
                return {
                    "allowed": False,
                    "reason": "MT5_CONNECTION_FAILED",
                    "error": self.last_error,
                }

        account = mt5.account_info()

        if account is None:
            return {
                "allowed": False,
                "reason": "ACCOUNT_INFO_UNAVAILABLE",
                "error": mt5.last_error(),
            }

        self._refresh_account(account)

        if not bool(getattr(account, "trade_allowed", False)):
            return {
                "allowed": False,
                "reason": "ACCOUNT_TRADING_NOT_ALLOWED",
            }

        resolved = self.resolve_symbol(symbol)

        if resolved is None:
            return {
                "allowed": False,
                "reason": "SYMBOL_NOT_FOUND",
            }

        info = mt5.symbol_info(resolved)

        if info is None:
            return {
                "allowed": False,
                "reason": "SYMBOL_INFO_UNAVAILABLE",
            }

        try:
            volume = float(volume)
        except (TypeError, ValueError):
            return {
                "allowed": False,
                "reason": "INVALID_VOLUME",
            }

        volume_min = float(info.volume_min)
        volume_max = float(info.volume_max)
        volume_step = float(info.volume_step)

        if volume < volume_min:
            return {
                "allowed": False,
                "reason": "VOLUME_BELOW_MINIMUM",
                "volume": volume,
                "volume_min": volume_min,
            }

        if volume > volume_max:
            return {
                "allowed": False,
                "reason": "VOLUME_ABOVE_MAXIMUM",
                "volume": volume,
                "volume_max": volume_max,
            }

        if volume_step > 0:
            steps = round(
                (volume - volume_min) / volume_step
            )

            normalized_volume = (
                volume_min + steps * volume_step
            )

            if abs(normalized_volume - volume) > 1e-9:
                return {
                    "allowed": False,
                    "reason": "INVALID_VOLUME_STEP",
                    "volume": volume,
                    "volume_step": volume_step,
                }

        order_type = str(order_type).upper().strip()

        if order_type not in ("BUY", "SELL"):
            return {
                "allowed": False,
                "reason": "INVALID_ORDER_TYPE",
            }

        tick = mt5.symbol_info_tick(resolved)

        if tick is None:
            return {
                "allowed": False,
                "reason": "TICK_UNAVAILABLE",
            }

        if price is None:
            price = (
                float(tick.ask)
                if order_type == "BUY"
                else float(tick.bid)
            )

        return {
            "allowed": True,

            "symbol": resolved,
            "order_type": order_type,
            "volume": volume,
            "price": float(price),

            "sl": sl,
            "tp": tp,

            "account_type": self.account_type,
            "account_login": self.account_login,

            "trade_allowed": self.account_trade_allowed,
            "balance": self.account_balance,
            "equity": self.account_equity,

            "volume_min": volume_min,
            "volume_max": volume_max,
            "volume_step": volume_step,

            "execution_enabled": True,
            "simulation": False,
        }

    # ==============================================================
    # MARKET ORDER
    # ==============================================================

    def place_market_order(
        self,
        symbol: str,
        volume: float,
        order_type: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "MT5 Universal Connector",
        type_filling: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a real MT5 market order.

        BUY  -> current ASK
        SELL -> current BID

        This method sends a REAL MT5 order when execution is enabled.
        """

        preflight = self.execution_preflight(
            symbol=symbol,
            volume=volume,
            order_type=order_type,
            sl=sl,
            tp=tp,
        )

        if not preflight.get("allowed"):
            self.last_execution = {
                "success": False,
                "stage": "PREFLIGHT",
                **preflight,
            }

            return self.last_execution

        resolved = preflight["symbol"]
        order_type = preflight["order_type"]
        volume = preflight["volume"]
        price = preflight["price"]

        mt5_order_type = (
            mt5.ORDER_TYPE_BUY
            if order_type == "BUY"
            else mt5.ORDER_TYPE_SELL
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": resolved,
            "volume": volume,
            "type": mt5_order_type,
            "price": price,
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": str(comment),
            "type_time": mt5.ORDER_TIME_GTC,
        }

        if sl is not None:
            request["sl"] = float(sl)

        if tp is not None:
            request["tp"] = float(tp)

        if type_filling is not None:
            request["type_filling"] = int(type_filling)

        result = self._send_order(
            request,
            operation="MARKET_ORDER",
        )

        return result

    # ==============================================================
    # BUY
    # ==============================================================

    def buy(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "MT5 Universal BUY",
    ) -> Dict[str, Any]:

        return self.place_market_order(
            symbol=symbol,
            volume=volume,
            order_type="BUY",
            sl=sl,
            tp=tp,
            deviation=deviation,
            magic=magic,
            comment=comment,
        )

    # ==============================================================
    # SELL
    # ==============================================================

    def sell(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "MT5 Universal SELL",
    ) -> Dict[str, Any]:

        return self.place_market_order(
            symbol=symbol,
            volume=volume,
            order_type="SELL",
            sl=sl,
            tp=tp,
            deviation=deviation,
            magic=magic,
            comment=comment,
        )

    # ==============================================================
    # SEND ORDER INTERNAL
    # ==============================================================

    def _send_order(
        self,
        request: Dict[str, Any],
        operation: str,
    ) -> Dict[str, Any]:

        if not self.EXECUTION_ENABLED:
            result = {
                "success": False,
                "operation": operation,
                "reason": "EXECUTION_DISABLED",
            }

            self.last_execution = result

            return result

        try:
            result = mt5.order_send(request)

        except Exception as exc:
            self.last_error = (
                -1,
                f"{type(exc).__name__}: {exc}",
            )

            response = {
                "success": False,
                "operation": operation,
                "request": request,
                "error": self.last_error,
            }

            self.last_execution = response

            return response

        if result is None:
            self.last_error = mt5.last_error()

            response = {
                "success": False,
                "operation": operation,
                "request": request,
                "error": self.last_error,
            }

            self.last_execution = response

            return response

        retcode = getattr(result, "retcode", None)

        success = retcode in (
            mt5.TRADE_RETCODE_DONE,
            mt5.TRADE_RETCODE_DONE_PARTIAL,
            mt5.TRADE_RETCODE_PLACED,
        )

        response = {
            "success": bool(success),
            "operation": operation,

            "retcode": retcode,
            "retcode_name": self._retcode_name(retcode),

            "order": getattr(result, "order", None),
            "deal": getattr(result, "deal", None),

            "volume": getattr(result, "volume", None),
            "price": getattr(result, "price", None),

            "bid": getattr(result, "bid", None),
            "ask": getattr(result, "ask", None),

            "request": request,

            "comment": getattr(result, "comment", None),
            "external_id": getattr(
                result,
                "external_id",
                None,
            ),

            "account_type": self.account_type,
            "account_login": self.account_login,
        }

        self.last_execution = response

        if success:
            self.last_error = None
        else:
            self.last_error = (
                retcode,
                getattr(result, "comment", None),
            )

        return response

    # ==============================================================
    # RETCODE
    # ==============================================================

    @staticmethod
    def _retcode_name(retcode: Any) -> str:

        if retcode is None:
            return "UNKNOWN"

        names = {
            getattr(mt5, name): name
            for name in dir(mt5)
            if name.startswith("TRADE_RETCODE_")
        }

        return names.get(retcode, "UNKNOWN")

    # ==============================================================
    # POSITIONS
    # ==============================================================

    def get_positions(
        self,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return currently open MT5 positions."""

        if not self.connected:
            if not self.connect():
                return []

        resolved = None

        if symbol:
            resolved = self.resolve_symbol(symbol)

            if resolved is None:
                return []

        positions = (
            mt5.positions_get(symbol=resolved)
            if resolved
            else mt5.positions_get()
        )

        if positions is None:
            self.last_error = mt5.last_error()
            return []

        return [
            self._position_to_dict(position)
            for position in positions
        ]

    # ==============================================================
    # POSITION DICT
    # ==============================================================

    @staticmethod
    def _position_to_dict(position: Any) -> Dict[str, Any]:

        return {
            "ticket": getattr(position, "ticket", None),
            "time": getattr(position, "time", None),
            "time_msc": getattr(position, "time_msc", None),

            "symbol": getattr(position, "symbol", None),
            "type": getattr(position, "type", None),

            "volume": getattr(position, "volume", None),

            "price_open": getattr(
                position,
                "price_open",
                None,
            ),

            "sl": getattr(position, "sl", None),
            "tp": getattr(position, "tp", None),

            "price_current": getattr(
                position,
                "price_current",
                None,
            ),

            "swap": getattr(position, "swap", None),
            "profit": getattr(position, "profit", None),

            "magic": getattr(position, "magic", None),
            "comment": getattr(position, "comment", None),
        }

    # ==============================================================
    # MODIFY POSITION
    # ==============================================================

    def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Modify SL/TP of an existing position."""

        if not self.EXECUTION_ENABLED:
            return {
                "success": False,
                "operation": "MODIFY_POSITION",
                "reason": "EXECUTION_DISABLED",
            }

        if not self.connected:
            if not self.connect():
                return {
                    "success": False,
                    "operation": "MODIFY_POSITION",
                    "reason": "MT5_CONNECTION_FAILED",
                    "error": self.last_error,
                }

        positions = mt5.positions_get(ticket=int(ticket))

        if not positions:
            return {
                "success": False,
                "operation": "MODIFY_POSITION",
                "reason": "POSITION_NOT_FOUND",
                "ticket": ticket,
            }

        position = positions[0]

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": int(ticket),
        }

        if sl is not None:
            request["sl"] = float(sl)

        if tp is not None:
            request["tp"] = float(tp)

        return self._send_order(
            request,
            operation="MODIFY_POSITION",
        )

    # ==============================================================
    # CLOSE POSITION
    # ==============================================================

    def close_position(
        self,
        ticket: int,
        volume: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "MT5 Universal CLOSE",
    ) -> Dict[str, Any]:
        """Close an existing MT5 position."""

        if not self.EXECUTION_ENABLED:
            return {
                "success": False,
                "operation": "CLOSE_POSITION",
                "reason": "EXECUTION_DISABLED",
            }

        if not self.connected:
            if not self.connect():
                return {
                    "success": False,
                    "operation": "CLOSE_POSITION",
                    "reason": "MT5_CONNECTION_FAILED",
                    "error": self.last_error,
                }

        positions = mt5.positions_get(ticket=int(ticket))

        if not positions:
            return {
                "success": False,
                "operation": "CLOSE_POSITION",
                "reason": "POSITION_NOT_FOUND",
                "ticket": ticket,
            }

        position = positions[0]

        symbol = position.symbol

        tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            return {
                "success": False,
                "operation": "CLOSE_POSITION",
                "reason": "TICK_UNAVAILABLE",
                "ticket": ticket,
            }

        close_volume = (
            float(volume)
            if volume is not None
            else float(position.volume)
        )

        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_volume,
            "type": order_type,
            "position": int(ticket),
            "price": price,
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": str(comment),
            "type_time": mt5.ORDER_TIME_GTC,
        }

        return self._send_order(
            request,
            operation="CLOSE_POSITION",
        )

    # ==============================================================
    # PENDING ORDERS
    # ==============================================================

    def get_pending_orders(
        self,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return currently active pending orders."""

        if not self.connected:
            if not self.connect():
                return []

        resolved = None

        if symbol:
            resolved = self.resolve_symbol(symbol)

            if resolved is None:
                return []

        orders = (
            mt5.orders_get(symbol=resolved)
            if resolved
            else mt5.orders_get()
        )

        if orders is None:
            self.last_error = mt5.last_error()
            return []

        return [
            {
                "ticket": getattr(order, "ticket", None),
                "time_setup": getattr(
                    order,
                    "time_setup",
                    None,
                ),
                "symbol": getattr(order, "symbol", None),
                "type": getattr(order, "type", None),
                "volume_initial": getattr(
                    order,
                    "volume_initial",
                    None,
                ),
                "volume_current": getattr(
                    order,
                    "volume_current",
                    None,
                ),
                "price_open": getattr(
                    order,
                    "price_open",
                    None,
                ),
                "sl": getattr(order, "sl", None),
                "tp": getattr(order, "tp", None),
                "magic": getattr(order, "magic", None),
                "comment": getattr(order, "comment", None),
            }
            for order in orders
        ]

    # ==============================================================
    # CANCEL PENDING ORDER
    # ==============================================================

    def cancel_pending_order(
        self,
        ticket: int,
    ) -> Dict[str, Any]:
        """Cancel an existing pending order."""

        if not self.EXECUTION_ENABLED:
            return {
                "success": False,
                "operation": "CANCEL_PENDING_ORDER",
                "reason": "EXECUTION_DISABLED",
            }

        if not self.connected:
            if not self.connect():
                return {
                    "success": False,
                    "operation": "CANCEL_PENDING_ORDER",
                    "reason": "MT5_CONNECTION_FAILED",
                    "error": self.last_error,
                }

        orders = mt5.orders_get(ticket=int(ticket))

        if not orders:
            return {
                "success": False,
                "operation": "CANCEL_PENDING_ORDER",
                "reason": "ORDER_NOT_FOUND",
                "ticket": ticket,
            }

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(ticket),
        }

        return self._send_order(
            request,
            operation="CANCEL_PENDING_ORDER",
        )

    # ==============================================================
    # LAST EXECUTION
    # ==============================================================

    def get_last_execution(self) -> Optional[Dict[str, Any]]:
        return self.last_execution

    # ==============================================================
    # DISPLAY
    # ==============================================================

    def print_status(self) -> None:

        status = self.status()

        print()
        print("=" * 70)
        print("MT5 CONNECTOR STATUS")
        print("=" * 70)

        print(f"Connector       : {status['connector']}")
        print(f"Version         : {status['version']}")
        print(f"Connected       : {status['connected']}")
        print(f"Broker          : {status['broker']}")
        print(f"Server          : {status['server']}")
        print(f"Terminal        : {status['terminal']}")
        print(f"Build           : {status['build']}")
        print(f"Account         : {status['account_login']}")
        print(f"Account Type    : {status['account_type']}")
        print(f"Currency        : {status['account_currency']}")
        print(f"Balance         : {status['balance']}")
        print(f"Equity          : {status['equity']}")
        print(f"Leverage        : 1:{status['leverage']}")
        print(f"Trade Allowed   : {status['trade_allowed']}")

        print()
        print(f"Read Only       : {status['read_only']}")
        print(f"Execution       : {status['execution_enabled']}")
        print(f"Simulation      : {status['simulation_enabled']}")

        print("=" * 70)


__all__ = [
    "MT5Connector",
]