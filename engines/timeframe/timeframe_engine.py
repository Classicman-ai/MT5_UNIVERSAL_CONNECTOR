"""
MT5 UNIVERSAL CONNECTOR
TIMEFRAME ENGINE
======================================================================

Version:
    2.2.0

Purpose:
    Unified read-only timeframe access layer for the MT5 Universal
    Connector.

Architecture:

    MT5 Terminal
        |
        v
    MT5Connector
        |
        +--> Symbol Resolution
        |
        +--> Native MT5 Historical Rates
        |
        +--> NumPy Structured-Record Normalization
        |
        +--> Timeframe Registry
        |
        +--> Custom Timeframe Aggregation
        |
        v
    Unified Timeframe Engine

Rules:
    - REAL MT5 market data only
    - NO hardcoded prices
    - NO simulated OHLC
    - READ-ONLY
    - NO trade execution
    - NO simulation
    - Native timeframes use real MT5 constants
    - Custom timeframes use real lower-timeframe candles
    - MT5 errors are preserved
    - NumPy structured MT5 records are explicitly supported
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .timeframe_registry import (
    TIMEFRAME_MINUTES,
    NATIVE_TIMEFRAMES,
    CUSTOM_TIMEFRAMES,
    is_native_timeframe,
    is_supported_timeframe,
    timeframe_to_minutes,
)

from .timeframe_aggregator import aggregate_candles


class TimeframeEngine:
    """
    Unified read-only MT5 timeframe engine.
    """

    ENGINE_NAME = "MT5 TIMEFRAME ENGINE"
    VERSION = "2.2.0"
    MODE = "READ_ONLY"
    EXECUTION_ENABLED = False
    SIMULATION_ENABLED = False
    # ==================================================================
    # MT5 TIMEFRAME CONSTANTS
    # ==================================================================

    MT5_TIMEFRAME_CONSTANTS = {
        "M1": "TIMEFRAME_M1",
        "M2": "TIMEFRAME_M2",
        "M3": "TIMEFRAME_M3",
        "M4": "TIMEFRAME_M4",
        "M5": "TIMEFRAME_M5",
        "M6": "TIMEFRAME_M6",
        "M10": "TIMEFRAME_M10",
        "M12": "TIMEFRAME_M12",
        "M15": "TIMEFRAME_M15",
        "M20": "TIMEFRAME_M20",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H2": "TIMEFRAME_H2",
        "H3": "TIMEFRAME_H3",
        "H4": "TIMEFRAME_H4",
        "H6": "TIMEFRAME_H6",
        "H8": "TIMEFRAME_H8",
        "H12": "TIMEFRAME_H12",
        "D1": "TIMEFRAME_D1",
        "W1": "TIMEFRAME_W1",
        "MN1": "TIMEFRAME_MN1",
    }

    def __init__(self, connector: Any):
        self.connector = connector

        self.initialized = False

        self.last_error: Optional[Any] = None
        self.last_error_message: Optional[str] = None

        self.last_symbol: Optional[str] = None
        self.last_timeframe: Optional[str] = None
        self.last_request_count: Optional[int] = None

        self.last_normalization_rejections = 0
        self.last_normalization_total = 0
        self.last_normalization_valid = 0
        self.last_normalization_reason: Optional[str] = None

    # ==================================================================
    # INITIALIZATION
    # ==================================================================

    def initialize(self) -> bool:
        """
        Validate connector availability.

        This method DOES NOT initialize MT5.
        MT5 connection ownership remains with MT5Connector.
        """

        if self.connector is None:
            self.initialized = False
            raise ValueError("MT5 connector is required.")

        connector_methods = (
            "status",
            "resolve_symbol",
            "get_tick",
            "get_candles",
            "get_historical_candles",
            "copy_rates",
            "get_rates",
        )

        available = any(
            callable(getattr(self.connector, name, None))
            for name in connector_methods
        )

        if not available:
            self.initialized = False

            raise AttributeError(
                "Connector does not expose a recognized MT5 "
                "connection/data interface."
            )

        self.initialized = True
        return True

    # ==================================================================
    # TIMEFRAME INFORMATION
    # ==================================================================

    def list_timeframes(self) -> List[str]:
        return list(TIMEFRAME_MINUTES.keys())

    def list_native_timeframes(self) -> List[str]:
        return list(NATIVE_TIMEFRAMES)

    def list_custom_timeframes(self) -> List[str]:
        return list(CUSTOM_TIMEFRAMES)

    def is_supported(self, timeframe: str) -> bool:
        if not timeframe:
            return False

        return is_supported_timeframe(
            str(timeframe).strip().upper()
        )

    def is_native(self, timeframe: str) -> bool:
        if not timeframe:
            return False

        return is_native_timeframe(
            str(timeframe).strip().upper()
        )

    def minutes(self, timeframe: str) -> int:
        value = timeframe_to_minutes(
            str(timeframe).strip().upper()
        )

        if value is None:
            raise ValueError(
                f"{timeframe} does not have a fixed minute duration."
            )

        return int(value)

    # ==================================================================
    # MT5 MODULE DISCOVERY
    # ==================================================================

    def _get_mt5_module(self) -> Optional[Any]:
        """
        Locate the MT5 Python module.

        Priority:
            connector.mt5
            connector._mt5
            connector.MT5
            connector.terminal
            connector._terminal
            direct MetaTrader5 import
        """

        for attribute in (
            "mt5",
            "_mt5",
            "MT5",
            "terminal",
            "_terminal",
        ):
            module = getattr(
                self.connector,
                attribute,
                None,
            )

            if module is not None and callable(
                getattr(
                    module,
                    "copy_rates_from_pos",
                    None,
                )
            ):
                return module

        try:
            import MetaTrader5 as mt5

            return mt5

        except ImportError:
            return None

    # ==================================================================
    # MT5 TIMEFRAME CONSTANT
    # ==================================================================

    def _get_mt5_timeframe_constant(
        self,
        timeframe: str,
    ) -> Any:

        timeframe = str(
            timeframe
        ).strip().upper()

        constant_name = self.MT5_TIMEFRAME_CONSTANTS.get(
            timeframe
        )

        if constant_name is None:
            raise ValueError(
                f"No MT5 timeframe constant mapping exists "
                f"for {timeframe}."
            )

        mt5 = self._get_mt5_module()

        if mt5 is None:
            raise RuntimeError(
                "MetaTrader5 Python module is unavailable."
            )

        constant = getattr(
            mt5,
            constant_name,
            None,
        )

        if constant is None:
            raise RuntimeError(
                f"MetaTrader5 does not expose "
                f"{constant_name}."
            )

        return constant

    # ==================================================================
    # MT5 ERROR HANDLING
    # ==================================================================

    def _read_mt5_error(
        self,
        mt5_module: Optional[Any] = None,
    ) -> Any:

        if mt5_module is None:
            mt5_module = self._get_mt5_module()

        if mt5_module is None:
            return None

        method = getattr(
            mt5_module,
            "last_error",
            None,
        )

        if not callable(method):
            return None

        try:
            return method()

        except Exception as exc:
            return (
                "Unable to read MT5 last_error(): "
                f"{type(exc).__name__}: {exc}"
            )

    def _record_error(
        self,
        message: str,
        mt5_module: Optional[Any] = None,
    ) -> None:

        self.last_error = self._read_mt5_error(
            mt5_module
        )

        self.last_error_message = message

    def _format_error(
        self,
        message: str,
    ) -> str:

        if self.last_error is not None:
            return (
                f"{message}\n"
                f"MT5 last_error(): {self.last_error}"
            )

        return message

    # ==================================================================
    # SYMBOL RESOLUTION
    # ==================================================================

    def resolve_symbol(
        self,
        requested_symbol: str,
    ) -> Optional[str]:

        if not requested_symbol:
            return None

        requested_symbol = str(
            requested_symbol
        ).strip()

        method = getattr(
            self.connector,
            "resolve_symbol",
            None,
        )

        if callable(method):

            try:
                resolved = method(
                    requested_symbol
                )

                if resolved:
                    self.last_symbol = str(
                        resolved
                    )

                    return str(resolved)

            except Exception as exc:

                self._record_error(
                    "Symbol resolution failed: "
                    f"{type(exc).__name__}: {exc}"
                )

                raise

        self.last_symbol = requested_symbol

        return requested_symbol

    # ==================================================================
    # NATIVE CANDLES
    # ==================================================================

    def get_native_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> List[Dict[str, Any]]:

        timeframe = str(
            timeframe
        ).strip().upper()

        if not self.initialized:
            self.initialize()

        if not self.is_supported(timeframe):
            raise ValueError(
                f"Unsupported timeframe: {timeframe}"
            )

        if not self.is_native(timeframe):
            raise ValueError(
                f"{timeframe} is not a native MT5 timeframe."
            )

        if not isinstance(count, int):
            raise TypeError(
                "count must be an integer."
            )

        if count <= 0:
            raise ValueError(
                "count must be greater than zero."
            )

        resolved_symbol = self.resolve_symbol(
            symbol
        )

        if not resolved_symbol:
            raise ValueError(
                f"Unable to resolve symbol: {symbol}"
            )

        self.last_timeframe = timeframe
        self.last_request_count = count

        # Reset normalization diagnostics.
        self.last_normalization_rejections = 0
        self.last_normalization_total = 0
        self.last_normalization_valid = 0
        self.last_normalization_reason = None

        # --------------------------------------------------------------
        # Connector candle interfaces.
        # --------------------------------------------------------------

        connector_methods = (
            "get_candles",
            "get_historical_candles",
            "copy_rates",
            "get_rates",
        )

        for method_name in connector_methods:

            method = getattr(
                self.connector,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = self._call_connector_candle_method(
                method,
                resolved_symbol,
                timeframe,
                count,
            )

            if result is not None:

                return self._normalize_and_validate(
                    result,
                    timeframe,
                )

        # --------------------------------------------------------------
        # Direct MT5 path.
        # --------------------------------------------------------------

        return self._get_rates_direct_mt5(
            resolved_symbol,
            timeframe,
            count,
        )

    # ==================================================================
    # CONNECTOR CANDLE METHOD
    # ==================================================================

    def _call_connector_candle_method(
        self,
        method: Any,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> Optional[Any]:

        mt5 = self._get_mt5_module()

        # --------------------------------------------------------------
        # 1. String positional.
        # --------------------------------------------------------------

        try:
            return method(
                symbol,
                timeframe,
                count,
            )

        except TypeError:
            pass

        except Exception as exc:

            self._record_error(
                "Connector historical candle request failed "
                f"using positional signature: "
                f"{type(exc).__name__}: {exc}",
                mt5,
            )

        # --------------------------------------------------------------
        # 2. String keyword.
        # --------------------------------------------------------------

        try:
            return method(
                symbol=symbol,
                timeframe=timeframe,
                count=count,
            )

        except TypeError:
            pass

        except Exception as exc:

            self._record_error(
                "Connector historical candle request failed "
                f"using keyword signature: "
                f"{type(exc).__name__}: {exc}",
                mt5,
            )

        # --------------------------------------------------------------
        # 3. MT5 constant positional.
        # --------------------------------------------------------------

        try:
            mt5_timeframe = (
                self._get_mt5_timeframe_constant(
                    timeframe
                )
            )

        except Exception:
            return None

        try:
            return method(
                symbol,
                mt5_timeframe,
                count,
            )

        except TypeError:
            pass

        except Exception as exc:

            self._record_error(
                "Connector historical candle request failed "
                f"using MT5 timeframe constant: "
                f"{type(exc).__name__}: {exc}",
                mt5,
            )

        # --------------------------------------------------------------
        # 4. MT5 constant keyword.
        # --------------------------------------------------------------

        try:
            return method(
                symbol=symbol,
                timeframe=mt5_timeframe,
                count=count,
            )

        except TypeError:
            return None

        except Exception as exc:

            self._record_error(
                "Connector historical candle request failed "
                f"using keyword MT5 timeframe constant: "
                f"{type(exc).__name__}: {exc}",
                mt5,
            )

            return None

    # ==================================================================
    # DIRECT MT5 HISTORICAL DATA
    # ==================================================================

    def _get_rates_direct_mt5(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> List[Dict[str, Any]]:

        mt5 = self._get_mt5_module()

        if mt5 is None:

            message = (
                "Historical candle retrieval failed: "
                "MetaTrader5 module is unavailable."
            )

            self._record_error(
                message
            )

            raise RuntimeError(
                self._format_error(message)
            )

        copy_rates = getattr(
            mt5,
            "copy_rates_from_pos",
            None,
        )

        if not callable(copy_rates):

            message = (
                "Historical candle retrieval failed: "
                "MetaTrader5.copy_rates_from_pos() "
                "is unavailable."
            )

            self._record_error(
                message,
                mt5,
            )

            raise RuntimeError(
                self._format_error(message)
            )

        try:

            mt5_timeframe = (
                self._get_mt5_timeframe_constant(
                    timeframe
                )
            )

        except Exception as exc:

            message = (
                "Unable to resolve MT5 timeframe constant "
                f"for {timeframe}: "
                f"{type(exc).__name__}: {exc}"
            )

            self._record_error(
                message,
                mt5,
            )

            raise RuntimeError(
                self._format_error(message)
            ) from exc

        # --------------------------------------------------------------
        # REAL MT5 REQUEST
        # --------------------------------------------------------------

        try:

            rates = copy_rates(
                symbol,
                mt5_timeframe,
                0,
                count,
            )

        except Exception as exc:

            self.last_error = (
                self._read_mt5_error(mt5)
            )

            self.last_error_message = (
                "MT5 copy_rates_from_pos exception: "
                f"{type(exc).__name__}: {exc}"
            )

            raise RuntimeError(
                self._format_error(
                    self.last_error_message
                )
            ) from exc

        # --------------------------------------------------------------
        # None.
        # --------------------------------------------------------------

        if rates is None:

            self.last_error = (
                self._read_mt5_error(mt5)
            )

            message = (
                "MT5 copy_rates_from_pos() returned None "
                f"for symbol={symbol}, "
                f"timeframe={timeframe}, "
                f"count={count}."
            )

            self.last_error_message = message

            raise RuntimeError(
                self._format_error(message)
            )

        # --------------------------------------------------------------
        # Empty.
        # --------------------------------------------------------------

        try:
            result_length = len(rates)

        except Exception:
            result_length = None

        if result_length == 0:

            self.last_error = (
                self._read_mt5_error(mt5)
            )

            message = (
                "MT5 copy_rates_from_pos() returned "
                f"zero candles for symbol={symbol}, "
                f"timeframe={timeframe}, "
                f"count={count}."
            )

            self.last_error_message = message

            raise RuntimeError(
                self._format_error(message)
            )

        # --------------------------------------------------------------
        # Normalize real MT5 data.
        # --------------------------------------------------------------

        return self._normalize_and_validate(
            rates,
            timeframe,
        )

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    def _normalize_and_validate(
        self,
        candles: Any,
        timeframe: str,
    ) -> List[Dict[str, Any]]:

        normalized = self._normalize_candles(
            candles,
            timeframe,
        )

        if not normalized:

            reason = (
                self.last_normalization_reason
                or "unknown normalization failure"
            )

            raise RuntimeError(
                "MT5 historical data was received but "
                f"no valid {timeframe} candles could be "
                f"normalized. "
                f"Rejected={self.last_normalization_rejections}/"
                f"{self.last_normalization_total}. "
                f"Reason={reason}"
            )

        return normalized

    def _normalize_candles(
        self,
        candles: Any,
        timeframe: str,
    ) -> List[Dict[str, Any]]:

        self.last_normalization_total = 0
        self.last_normalization_valid = 0
        self.last_normalization_rejections = 0
        self.last_normalization_reason = None

        if candles is None:
            self.last_normalization_reason = (
                "candle collection is None"
            )
            return []

        normalized: List[Dict[str, Any]] = []

        try:
            iterator = iter(candles)

        except TypeError:

            self.last_normalization_reason = (
                f"object of type {type(candles).__name__} "
                "is not iterable"
            )

            return []

        for candle in iterator:

            self.last_normalization_total += 1

            item = self._normalize_single_candle(
                candle,
                timeframe,
            )

            if item is not None:

                normalized.append(item)
                self.last_normalization_valid += 1

            else:

                self.last_normalization_rejections += 1

        normalized.sort(
            key=lambda item: item["time"]
        )

        if self.last_normalization_rejections > 0:
            self.last_normalization_reason = (
                self.last_normalization_reason
                or "one or more candles failed validation"
            )

        return normalized

    # ==================================================================
    # SINGLE CANDLE NORMALIZATION
    # ==================================================================

    def _normalize_single_candle(
        self,
        candle: Any,
        timeframe: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize one candle.

        IMPORTANT:
            MT5 MetaTrader5.copy_rates_from_pos() normally returns:

                numpy.ndarray

            where every row is:

                numpy.void

            with named fields:

                time
                open
                high
                low
                close
                tick_volume
                spread
                real_volume

        This version explicitly handles that structure.
        """

        try:

            # ==========================================================
            # CASE 1: Python dictionary
            # ==========================================================

            if isinstance(candle, dict):

                timestamp = candle.get(
                    "time",
                    candle.get("timestamp"),
                )

                open_price = candle.get(
                    "open",
                    candle.get("o"),
                )

                high_price = candle.get(
                    "high",
                    candle.get("h"),
                )

                low_price = candle.get(
                    "low",
                    candle.get("l"),
                )

                close_price = candle.get(
                    "close",
                    candle.get("c"),
                )

                tick_volume = candle.get(
                    "tick_volume",
                    candle.get("volume", 0),
                )

                volume = candle.get(
                    "real_volume",
                    candle.get("volume_real", 0.0),
                )

                spread = candle.get(
                    "spread",
                    0,
                )

            # ==========================================================
            # CASE 2: NumPy structured record
            # ==========================================================

            elif self._is_numpy_structured_record(candle):

                timestamp = candle["time"]
                open_price = candle["open"]
                high_price = candle["high"]
                low_price = candle["low"]
                close_price = candle["close"]

                tick_volume = (
                    candle["tick_volume"]
                    if "tick_volume" in candle.dtype.names
                    else 0
                )

                volume = (
                    candle["real_volume"]
                    if "real_volume" in candle.dtype.names
                    else 0
                )

                spread = (
                    candle["spread"]
                    if "spread" in candle.dtype.names
                    else 0
                )

            # ==========================================================
            # CASE 3: Generic object / named attributes
            # ==========================================================

            else:

                timestamp = getattr(
                    candle,
                    "time",
                    None,
                )

                open_price = getattr(
                    candle,
                    "open",
                    None,
                )

                high_price = getattr(
                    candle,
                    "high",
                    None,
                )

                low_price = getattr(
                    candle,
                    "low",
                    None,
                )

                close_price = getattr(
                    candle,
                    "close",
                    None,
                )

                tick_volume = getattr(
                    candle,
                    "tick_volume",
                    getattr(
                        candle,
                        "volume",
                        0,
                    ),
                )

                volume = getattr(
                    candle,
                    "real_volume",
                    0,
                )

                spread = getattr(
                    candle,
                    "spread",
                    0,
                )

            # ==========================================================
            # REQUIRED FIELDS
            # ==========================================================

            if timestamp is None:
                self.last_normalization_reason = (
                    "missing timestamp"
                )
                return None

            if open_price is None:
                self.last_normalization_reason = (
                    "missing open"
                )
                return None

            if high_price is None:
                self.last_normalization_reason = (
                    "missing high"
                )
                return None

            if low_price is None:
                self.last_normalization_reason = (
                    "missing low"
                )
                return None

            if close_price is None:
                self.last_normalization_reason = (
                    "missing close"
                )
                return None

            # ==========================================================
            # TYPE CONVERSION
            # ==========================================================

            timestamp = self._normalize_timestamp(
                timestamp
            )

            open_price = float(
                open_price
            )

            high_price = float(
                high_price
            )

            low_price = float(
                low_price
            )

            close_price = float(
                close_price
            )

            tick_volume = int(
                tick_volume or 0
            )

            volume = float(
                volume or 0.0
            )

            spread = int(
                spread or 0
            )

            # ==========================================================
            # FINITE VALUE VALIDATION
            # ==========================================================

            values = (
                open_price,
                high_price,
                low_price,
                close_price,
            )

            for value in values:

                if value != value:
                    self.last_normalization_reason = (
                        "NaN OHLC value"
                    )
                    return None

                if value in (
                    float("inf"),
                    float("-inf"),
                ):

                    self.last_normalization_reason = (
                        "infinite OHLC value"
                    )
                    return None

            # ==========================================================
            # OHLC STRUCTURAL VALIDATION
            # ==========================================================

            if high_price < max(
                open_price,
                close_price,
                low_price,
            ):

                self.last_normalization_reason = (
                    "invalid OHLC: high below required value"
                )

                return None

            if low_price > min(
                open_price,
                close_price,
                high_price,
            ):

                self.last_normalization_reason = (
                    "invalid OHLC: low above required value"
                )

                return None

            # ==========================================================
            # NORMALIZED CANDLE
            # ==========================================================

            return {
                "time": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "tick_volume": tick_volume,
                "volume": volume,
                "spread": spread,
                "timeframe": timeframe,
            }

        except (
            TypeError,
            ValueError,
            AttributeError,
            OverflowError,
            KeyError,
        ) as exc:

            self.last_normalization_reason = (
                f"{type(exc).__name__}: {exc}"
            )

            return None

    # ==================================================================
    # NUMPY STRUCTURED RECORD DETECTION
    # ==================================================================

    @staticmethod
    def _is_numpy_structured_record(
        candle: Any,
    ) -> bool:
        """
        Detect numpy.void structured records without requiring NumPy
        to be imported at module load time.
        """

        dtype = getattr(
            candle,
            "dtype",
            None,
        )

        if dtype is None:
            return False

        names = getattr(
            dtype,
            "names",
            None,
        )

        if not names:
            return False

        required = {
            "time",
            "open",
            "high",
            "low",
            "close",
        }

        return required.issubset(
            set(names)
        )

    # ==================================================================
    # TIMESTAMP NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_timestamp(
        timestamp: Any,
    ) -> datetime:
        """
        Normalize timestamps into UTC-aware datetime objects.
        """

        if isinstance(
            timestamp,
            datetime,
        ):

            if timestamp.tzinfo is None:

                return timestamp.replace(
                    tzinfo=timezone.utc
                )

            return timestamp.astimezone(
                timezone.utc
            )

        if isinstance(
            timestamp,
            (int, float),
        ):

            return datetime.fromtimestamp(
                float(timestamp),
                tz=timezone.utc,
            )

        if isinstance(
            timestamp,
            str,
        ):

            value = timestamp.strip()

            if value.endswith("Z"):

                value = (
                    value[:-1]
                    + "+00:00"
                )

            parsed = datetime.fromisoformat(
                value
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        # --------------------------------------------------------------
        # NumPy scalar integers.
        # --------------------------------------------------------------

        try:

            if hasattr(
                timestamp,
                "item",
            ):

                value = timestamp.item()

                if isinstance(
                    value,
                    (int, float),
                ):

                    return datetime.fromtimestamp(
                        float(value),
                        tz=timezone.utc,
                    )

        except Exception:
            pass

        raise TypeError(
            "Unsupported timestamp type: "
            f"{type(timestamp).__name__}"
        )

    # ==================================================================
    # UNIFIED CANDLE ACCESS
    # ==================================================================

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> List[Dict[str, Any]]:

        timeframe = str(
            timeframe
        ).strip().upper()

        if not self.is_supported(timeframe):
            raise ValueError(
                f"Unsupported timeframe: {timeframe}"
            )

        if self.is_native(timeframe):

            return self.get_native_candles(
                symbol=symbol,
                timeframe=timeframe,
                count=count,
            )

        return self.get_custom_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
        )

    # ==================================================================
    # CUSTOM TIMEFRAMES
    # ==================================================================

    def get_custom_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> List[Dict[str, Any]]:

        timeframe = str(
            timeframe
        ).strip().upper()

        if not self.is_supported(timeframe):
            raise ValueError(
                f"Unsupported timeframe: {timeframe}"
            )

        if self.is_native(timeframe):

            return self.get_native_candles(
                symbol,
                timeframe,
                count,
            )

        source_timeframe = (
            self._select_source_timeframe(
                timeframe
            )
        )

        required_source_count = (
            self._required_source_count(
                timeframe,
                source_timeframe,
                count,
            )
        )

        source_candles = self.get_native_candles(
            symbol=symbol,
            timeframe=source_timeframe,
            count=required_source_count,
        )

        if not source_candles:

            raise RuntimeError(
                "Custom timeframe aggregation aborted: "
                f"no real {source_timeframe} candles "
                f"were returned for {symbol}."
            )

        aggregated = aggregate_candles(
            source_candles,
            target_timeframe=timeframe,
        )

        if not aggregated:

            raise RuntimeError(
                "Custom timeframe aggregation produced "
                f"no {timeframe} candles from real "
                f"{source_timeframe} data."
            )

        return aggregated[-count:]

    # ==================================================================
    # SOURCE TIMEFRAME SELECTION
    # ==================================================================

    def _select_source_timeframe(
        self,
        target_timeframe: str,
    ) -> str:

        target_minutes = self.minutes(
            target_timeframe
        )

        if target_minutes < 60:
            return "M1"

        if target_minutes % 60 == 0:
            return "H1"

        return "M1"

    # ==================================================================
    # SOURCE COUNT
    # ==================================================================

    def _required_source_count(
        self,
        target_timeframe: str,
        source_timeframe: str,
        target_count: int,
    ) -> int:

        target_minutes = self.minutes(
            target_timeframe
        )

        source_minutes = self.minutes(
            source_timeframe
        )

        if source_minutes <= 0:

            return max(
                target_count * 2,
                100,
            )

        ratio = max(
            1,
            target_minutes // source_minutes,
        )

        return max(
            target_count * ratio
            + ratio * 2,
            100,
        )

    # ==================================================================
    # STATUS
    # ==================================================================

    def status(self) -> Dict[str, Any]:

        return {
            "engine": self.ENGINE_NAME,
            "version": self.VERSION,
            "initialized": self.initialized,
            "mode": self.MODE,
            "execution_enabled": self.EXECUTION_ENABLED,
            "simulation_enabled": self.SIMULATION_ENABLED,
            "native_timeframes": list(
                NATIVE_TIMEFRAMES
            ),
            "custom_timeframes": list(
                CUSTOM_TIMEFRAMES
            ),
            "supported_timeframes": (
                self.list_timeframes()
            ),
            "last_symbol": self.last_symbol,
            "last_timeframe": self.last_timeframe,
            "last_request_count": (
                self.last_request_count
            ),
            "last_error": self.last_error,
            "last_error_message": (
                self.last_error_message
            ),
            "normalization_total": (
                self.last_normalization_total
            ),
            "normalization_valid": (
                self.last_normalization_valid
            ),
            "normalization_rejections": (
                self.last_normalization_rejections
            ),
            "normalization_reason": (
                self.last_normalization_reason
            ),
        }

    # ==================================================================
    # ERROR DIAGNOSTIC
    # ==================================================================

    def get_last_error(self) -> Dict[str, Any]:

        return {
            "error": self.last_error,
            "message": self.last_error_message,
            "symbol": self.last_symbol,
            "timeframe": self.last_timeframe,
            "count": self.last_request_count,
            "normalization_total": (
                self.last_normalization_total
            ),
            "normalization_valid": (
                self.last_normalization_valid
            ),
            "normalization_rejections": (
                self.last_normalization_rejections
            ),
            "normalization_reason": (
                self.last_normalization_reason
            ),
        }

    # ==================================================================
    # REGISTRY DISPLAY
    # ==================================================================

    def print_registry(self) -> None:

        print()
        print("=" * 70)
        print("TIMEFRAME REGISTRY")
        print("=" * 70)

        for timeframe, minutes in (
            TIMEFRAME_MINUTES.items()
        ):

            if minutes is None:

                print(
                    f"{timeframe:<6} -> "
                    "calendar month"
                )

            else:

                native = (
                    "NATIVE"
                    if self.is_native(timeframe)
                    else "CUSTOM"
                )

                print(
                    f"{timeframe:<6} -> "
                    f"{minutes} minute(s) "
                    f"[{native}]"
                )

        print("=" * 70)

    # ==================================================================
    # STATUS DISPLAY
    # ==================================================================

    def print_status(self) -> None:

        status = self.status()

        print()
        print("=" * 70)
        print("TIMEFRAME ENGINE STATUS")
        print("=" * 70)

        print(
            f"Engine          : "
            f"{status['engine']}"
        )

        print(
            f"Version         : "
            f"{status['version']}"
        )

        print(
            f"Initialized     : "
            f"{status['initialized']}"
        )

        print(
            f"Mode            : "
            f"{status['mode']}"
        )

        print(
            f"Execution       : "
            f"{status['execution_enabled']}"
        )

        print(
            f"Simulation      : "
            f"{status['simulation_enabled']}"
        )

        print(
            f"Last Symbol     : "
            f"{status['last_symbol']}"
        )

        print(
            f"Last Timeframe  : "
            f"{status['last_timeframe']}"
        )

        print(
            f"Last Count      : "
            f"{status['last_request_count']}"
        )

        print(
            f"Last MT5 Error  : "
            f"{status['last_error']}"
        )

        print(
            f"Normalized      : "
            f"{status['normalization_valid']}/"
            f"{status['normalization_total']}"
        )

        print(
            f"Rejected        : "
            f"{status['normalization_rejections']}"
        )

        if status["normalization_reason"]:

            print(
                f"Normalize Info  : "
                f"{status['normalization_reason']}"
            )

        if status["last_error_message"]:

            print(
                f"Error Message   : "
                f"{status['last_error_message']}"
            )

        print("=" * 70)


__all__ = [
    "TimeframeEngine",
]



