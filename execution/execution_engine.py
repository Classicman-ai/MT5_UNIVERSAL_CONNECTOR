"""End-to-end MT5 execution orchestration.

This layer deliberately contains no hard-coded maximum risk percentage and
no artificial maximum RRR. Risk sizing belongs to the caller/strategy. The
maximum strategy-supported RRR is derived from the selected structural TP.

Real execution is delegated to MT5Connector. The engine never silently
converts a live request into simulation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ExecutionEngine:
    """Thin, explicit execution layer over :class:`MT5Connector`."""

    ENGINE_NAME = "MT5 END-TO-END EXECUTION ENGINE"
    VERSION = "1.0.0"
    EXECUTION_ENABLED = True
    SIMULATION_ENABLED = False

    def __init__(self, connector: Any):
        if connector is None:
            raise ValueError("MT5 connector is required")
        self.connector = connector

    def status(self) -> Dict[str, Any]:
        base = self.connector.status()
        return {
            "engine": self.ENGINE_NAME,
            "version": self.VERSION,
            "execution_enabled": self.EXECUTION_ENABLED,
            "simulation_enabled": self.SIMULATION_ENABLED,
            "connector_connected": base.get("connected"),
            "account_type": base.get("account_type"),
            "trade_allowed": base.get("trade_allowed"),
            "read_only": base.get("read_only"),
        }

    def preflight(
        self,
        symbol: str,
        volume: float,
        side: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Validate a real execution request without sending it."""
        return self.connector.execution_preflight(
            symbol=symbol,
            volume=volume,
            order_type=side,
            sl=sl,
            tp=tp,
        )

    def execute_market(
        self,
        symbol: str,
        volume: float,
        side: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "MT5 Universal Execution",
    ) -> Dict[str, Any]:
        """Send a real market order through the connector."""
        side = str(side).strip().upper()
        if side == "BUY":
            return self.connector.buy(
                symbol=symbol,
                volume=volume,
                sl=sl,
                tp=tp,
                deviation=deviation,
                magic=magic,
                comment=comment,
            )
        if side == "SELL":
            return self.connector.sell(
                symbol=symbol,
                volume=volume,
                sl=sl,
                tp=tp,
                deviation=deviation,
                magic=magic,
                comment=comment,
            )
        return {"success": False, "reason": "INVALID_ORDER_TYPE", "side": side}

    def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self.connector.modify_position(ticket=ticket, sl=sl, tp=tp)

    def close_position(
        self,
        ticket: int,
        volume: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "MT5 Universal Close",
    ) -> Dict[str, Any]:
        return self.connector.close_position(
            ticket=ticket,
            volume=volume,
            deviation=deviation,
            magic=magic,
            comment=comment,
        )

    def cancel_pending_order(self, ticket: int) -> Dict[str, Any]:
        return self.connector.cancel_pending_order(ticket=ticket)

    @staticmethod
    def calculate_strategy_rrr(
        side: str,
        entry: float,
        stop_loss: float,
        best_tp: float,
    ) -> Dict[str, Any]:
        """Calculate RRR from the actual structural TP; no maximum cap."""
        side = str(side).strip().upper()
        entry = float(entry)
        stop_loss = float(stop_loss)
        best_tp = float(best_tp)

        if side == "BUY":
            risk = entry - stop_loss
            reward = best_tp - entry
        elif side == "SELL":
            risk = stop_loss - entry
            reward = entry - best_tp
        else:
            return {"valid": False, "reason": "INVALID_ORDER_TYPE"}

        if risk <= 0:
            return {"valid": False, "reason": "INVALID_STOP_DISTANCE"}
        if reward <= 0:
            return {"valid": False, "reason": "INVALID_TP_DISTANCE"}

        return {
            "valid": True,
            "side": side,
            "entry": entry,
            "stop_loss": stop_loss,
            "best_tp": best_tp,
            "risk_distance": risk,
            "reward_distance": reward,
            "rrr": reward / risk,
            "max_rrr": reward / risk,
            "rrr_source": "STRUCTURAL_TP_DISTANCE",
        }


__all__ = ["ExecutionEngine"]
