"""Reliable MCP-to-SaaS delivery adapter."""

from .adapter import IdempotencyConflict, ReliableAdapter
from .fake_saas import FakeSupportSaaS

__all__ = ["FakeSupportSaaS", "IdempotencyConflict", "ReliableAdapter"]
