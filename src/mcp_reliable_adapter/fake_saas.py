"""Deterministic in-memory SaaS double for demos and tests."""

from __future__ import annotations

from .adapter import DeliveryError


class FakeSupportSaaS:
    def __init__(self, *, failures_before_success: int = 0, always_fail: bool = False) -> None:
        self.failures_before_success = failures_before_success
        self.always_fail = always_fail
        self.calls = 0
        self.tickets: dict[str, str] = {}

    def create_ticket(self, *, subject: str, description: str, idempotency_key: str) -> str:
        self.calls += 1
        if self.always_fail or self.calls <= self.failures_before_success:
            raise DeliveryError("simulated upstream outage")
        if idempotency_key not in self.tickets:
            self.tickets[idempotency_key] = f"FAKE-{len(self.tickets) + 1:04d}"
        return self.tickets[idempotency_key]
