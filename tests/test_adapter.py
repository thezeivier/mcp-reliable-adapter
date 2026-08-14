from __future__ import annotations

import asyncio
import sqlite3

import pytest

from mcp_reliable_adapter import FakeSupportSaaS, IdempotencyConflict, ReliableAdapter
from mcp_reliable_adapter.server import mcp


class Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


def submit(adapter: ReliableAdapter, key: str = "request-001") -> dict[str, object]:
    return adapter.submit_support_ticket(
        subject="Cannot export report",
        description="The CSV export finishes without a download.",
        idempotency_key=key,
    )


def test_repeated_submission_returns_one_ticket(tmp_path, clock):
    adapter = ReliableAdapter(tmp_path / "adapter.db", FakeSupportSaaS(), clock=clock)

    first = submit(adapter)
    second = submit(adapter)

    assert first["ticket_id"] == second["ticket_id"]
    assert [event["event"] for event in adapter.get_audit_trail(first["ticket_id"])] == [
        "accepted",
        "duplicate_submission",
    ]


def test_idempotency_key_rejects_different_payload(tmp_path, clock):
    adapter = ReliableAdapter(tmp_path / "adapter.db", FakeSupportSaaS(), clock=clock)
    submit(adapter)

    with pytest.raises(IdempotencyConflict):
        adapter.submit_support_ticket(
            subject="Different request", description="Different body", idempotency_key="request-001"
        )


def test_successful_delivery_updates_status_and_audit(tmp_path, clock):
    saas = FakeSupportSaaS()
    adapter = ReliableAdapter(tmp_path / "adapter.db", saas, clock=clock)
    accepted = submit(adapter)

    assert adapter.process_due() == 1
    status = adapter.get_delivery_status(accepted["ticket_id"])

    assert status["status"] == "delivered"
    assert status["external_id"] == "FAKE-0001"
    assert status["attempts"] == 1
    assert [event["event"] for event in adapter.get_audit_trail(accepted["ticket_id"])] == [
        "accepted",
        "delivered",
    ]


def test_retry_waits_for_exponential_backoff(tmp_path, clock):
    adapter = ReliableAdapter(
        tmp_path / "adapter.db",
        FakeSupportSaaS(failures_before_success=2),
        clock=clock,
        base_backoff_seconds=5,
    )
    accepted = submit(adapter)

    adapter.process_due()
    assert adapter.get_delivery_status(accepted["ticket_id"])["attempts"] == 1
    assert adapter.process_due() == 0
    clock.advance(5)
    adapter.process_due()
    assert adapter.process_due() == 0
    clock.advance(10)
    adapter.process_due()

    assert adapter.get_delivery_status(accepted["ticket_id"])["status"] == "delivered"
    delays = [
        event["details"]["delay_seconds"]
        for event in adapter.get_audit_trail(accepted["ticket_id"])
        if event["event"] == "retry_scheduled"
    ]
    assert delays == [5, 10]


def test_exhausted_retries_go_to_dead_letter(tmp_path, clock):
    adapter = ReliableAdapter(
        tmp_path / "adapter.db",
        FakeSupportSaaS(always_fail=True),
        clock=clock,
        max_attempts=2,
        base_backoff_seconds=3,
    )
    accepted = submit(adapter)

    adapter.process_due()
    clock.advance(3)
    adapter.process_due()
    status = adapter.get_delivery_status(accepted["ticket_id"])

    assert status["status"] == "dead_letter"
    assert status["attempts"] == 2
    assert "simulated upstream outage" in status["last_error"]
    assert adapter.get_audit_trail(accepted["ticket_id"])[-1]["event"] == "dead_lettered"


def test_restart_recovers_claimed_work(tmp_path, clock):
    database = tmp_path / "adapter.db"
    first = ReliableAdapter(database, FakeSupportSaaS(), clock=clock)
    accepted = submit(first)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE outbox SET state = 'processing' WHERE ticket_id = ?", (accepted["ticket_id"],))

    restarted = ReliableAdapter(database, FakeSupportSaaS(), clock=clock)

    assert restarted.process_due() == 1
    assert restarted.get_delivery_status(accepted["ticket_id"])["status"] == "delivered"


def test_stale_candidate_cannot_bypass_backoff_or_reset_attempts(tmp_path, clock):
    """A worker that read before another failure must not claim the requeued row."""
    database = tmp_path / "adapter.db"
    adapter = ReliableAdapter(database, FakeSupportSaaS(), clock=clock)
    accepted = submit(adapter)

    with sqlite3.connect(database) as db:
        stale_attempts = db.execute(
            "SELECT attempts FROM outbox WHERE ticket_id = ?", (accepted["ticket_id"],)
        ).fetchone()[0]
        db.execute(
            """UPDATE outbox SET attempts = 1, next_attempt_at = ?, state = 'queued'
               WHERE ticket_id = ?""",
            (clock.now + 10, accepted["ticket_id"]),
        )
        claimed = db.execute(
            """UPDATE outbox SET state = 'processing'
               WHERE ticket_id = ? AND state = 'queued' AND attempts = ?
               AND next_attempt_at <= ?""",
            (accepted["ticket_id"], stale_attempts, clock.now),
        ).rowcount

    assert claimed == 0
    assert adapter.process_due() == 0
    assert adapter.get_delivery_status(accepted["ticket_id"])["attempts"] == 1


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("base_backoff_seconds", 0),
        ("base_backoff_seconds", float("nan")),
        ("max_backoff_seconds", -1),
        ("max_backoff_seconds", float("inf")),
    ],
)
def test_invalid_backoff_configuration_is_rejected(tmp_path, keyword, value):
    with pytest.raises(ValueError):
        ReliableAdapter(tmp_path / "adapter.db", FakeSupportSaaS(), **{keyword: value})


def test_in_memory_database_is_rejected_with_actionable_error():
    with pytest.raises(ValueError, match="multiple connections"):
        ReliableAdapter(":memory:", FakeSupportSaaS())


def test_mcp_tools_publish_compatible_input_and_output_schemas():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    submit_tool = tools["submit_support_ticket"]
    assert submit_tool.inputSchema["required"] == [
        "subject",
        "description",
        "idempotency_key",
    ]
    assert submit_tool.outputSchema["type"] == "object"
    # Responses have different shapes (accepted vs. conflict; found vs. not found),
    # so only fields present in each response may be validated as required.
    assert submit_tool.outputSchema.get("required", []) == []
    assert tools["get_delivery_status"].outputSchema["type"] == "object"
