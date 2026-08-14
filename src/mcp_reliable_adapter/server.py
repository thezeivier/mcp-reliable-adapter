"""MCP stdio entry point exposing the reliable adapter as two tools."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, cast

from mcp.server.fastmcp import FastMCP

from .adapter import IdempotencyConflict, ReliableAdapter
from .fake_saas import FakeSupportSaaS

mcp = FastMCP("mcp-reliable-adapter")


class ToolResponse(TypedDict, total=False):
    """JSON object returned by both MCP tools."""

    status: str
    ticket_id: str
    external_id: str | None
    created_at: float
    updated_at: float
    attempts: int
    next_attempt_at: float
    last_error: str | None
    error: str


@lru_cache(maxsize=1)
def get_adapter() -> ReliableAdapter:
    database = Path(os.getenv("ADAPTER_DB_PATH", "adapter.db"))
    return ReliableAdapter(database, FakeSupportSaaS())


@mcp.tool()
def submit_support_ticket(
    subject: str, description: str, idempotency_key: str
) -> ToolResponse:
    """Durably accept a support ticket for asynchronous downstream delivery."""
    try:
        return cast(
            ToolResponse,
            get_adapter().submit_support_ticket(
                subject=subject, description=description, idempotency_key=idempotency_key
            ),
        )
    except IdempotencyConflict as error:
        return {"status": "conflict", "error": str(error)}


@mcp.tool()
def get_delivery_status(ticket_id: str) -> ToolResponse:
    """Return the current durable delivery state for a submitted ticket."""
    adapter = get_adapter()
    adapter.process_due()
    return cast(
        ToolResponse, adapter.get_delivery_status(ticket_id) or {"status": "not_found"}
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
