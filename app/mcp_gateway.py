from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


class MCPToolError(RuntimeError):
    pass


class MCPGateway:
    """Local demo MCP-style tool gateway. No external banking system is connected."""
    REFUND_TOOL = "mcp://banking-ledger/credit-refund"

    def execute_refund_credit(self, *, allowed_tools: list[str], thread_id: str, amount: float, currency: str, approver_id: str) -> dict[str, Any]:
        if self.REFUND_TOOL not in allowed_tools:
            raise MCPToolError(f"Agent is not authorised for {self.REFUND_TOOL}")
        if amount <= 0 or amount > 10000:
            raise MCPToolError("Refund amount is outside the demo tool's allowed range")
        # Intentionally simulated: never connects to a real financial ledger.
        return {
            "tool": self.REFUND_TOOL,
            "result": "SIMULATED_CREDIT_POSTED",
            "transaction_id": f"SIM-{thread_id[:8].upper()}",
            "amount": round(amount, 2),
            "currency": currency,
            "approved_by": approver_id,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "environment": "MVP_SIMULATION_ONLY",
        }
