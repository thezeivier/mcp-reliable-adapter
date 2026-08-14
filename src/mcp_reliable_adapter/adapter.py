"""Durable support-ticket adapter built around SQLite and a transactional outbox."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class SupportSaaS(Protocol):
    def create_ticket(self, *, subject: str, description: str, idempotency_key: str) -> str: ...


class IdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for a different request."""


class DeliveryError(RuntimeError):
    """Normalized retryable failure raised by a downstream SaaS adapter."""


class ReliableAdapter:
    """Accept work durably, then deliver it to a third-party SaaS at least once.

    The downstream idempotency key turns possible duplicate attempts into one
    logical operation when the SaaS honors it.
    """

    def __init__(
        self,
        database: str | Path,
        saas: SupportSaaS,
        *,
        clock: Callable[[], float] = time.time,
        max_attempts: int = 4,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not math.isfinite(base_backoff_seconds) or base_backoff_seconds <= 0:
            raise ValueError("base_backoff_seconds must be finite and positive")
        if not math.isfinite(max_backoff_seconds) or max_backoff_seconds <= 0:
            raise ValueError("max_backoff_seconds must be finite and positive")
        if str(database) == ":memory:":
            raise ValueError(":memory: is unsupported because the adapter uses multiple connections")
        self.database = str(database)
        self.saas = saas
        self.clock = clock
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_hash TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    ticket_id TEXT PRIMARY KEY REFERENCES tickets(id),
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL REFERENCES tickets(id),
                    event TEXT NOT NULL,
                    details TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                );
                """
            )
            # A process can stop after claiming an item. Requeueing is safe because
            # the same idempotency key is forwarded on every attempt.
            db.execute("UPDATE outbox SET state = 'queued' WHERE state = 'processing'")

    @staticmethod
    def _request_hash(subject: str, description: str) -> str:
        encoded = json.dumps(
            {"description": description, "subject": subject},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _audit(
        self, db: sqlite3.Connection, ticket_id: str, event: str, details: dict[str, object]
    ) -> None:
        db.execute(
            "INSERT INTO audit_log(ticket_id, event, details, occurred_at) VALUES (?, ?, ?, ?)",
            (ticket_id, event, json.dumps(details, sort_keys=True), self.clock()),
        )

    def submit_support_ticket(
        self, *, subject: str, description: str, idempotency_key: str
    ) -> dict[str, object]:
        """Persist a ticket and its outbox record atomically before returning."""
        if not subject.strip() or not description.strip() or not idempotency_key.strip():
            raise ValueError("subject, description and idempotency_key are required")
        request_hash = self._request_hash(subject, description)
        now = self.clock()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM tickets WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise IdempotencyConflict(
                        "idempotency_key already belongs to a different request"
                    )
                self._audit(db, existing["id"], "duplicate_submission", {})
                return self._ticket_dict(existing)

            ticket_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO tickets
                   (id, idempotency_key, request_hash, subject, description, status,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (ticket_id, idempotency_key, request_hash, subject, description, now, now),
            )
            db.execute(
                "INSERT INTO outbox(ticket_id, state, next_attempt_at) VALUES (?, 'queued', ?)",
                (ticket_id, now),
            )
            self._audit(db, ticket_id, "accepted", {"idempotency_key": idempotency_key})
            row = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            return self._ticket_dict(row)

    def process_due(self, *, limit: int = 10) -> int:
        """Attempt due deliveries synchronously; returns the number claimed."""
        if limit < 1:
            return 0
        now = self.clock()
        with self._connect() as db:
            rows = db.execute(
                """SELECT t.*, o.attempts FROM tickets t JOIN outbox o ON o.ticket_id = t.id
                   WHERE o.state = 'queued' AND o.next_attempt_at <= ?
                   ORDER BY o.next_attempt_at, t.created_at LIMIT ?""",
                (now, limit),
            ).fetchall()

        processed = 0
        for row in rows:
            with self._connect() as db:
                claimed = db.execute(
                    """UPDATE outbox SET state = 'processing'
                       WHERE ticket_id = ? AND state = 'queued' AND attempts = ?
                       AND next_attempt_at <= ?""",
                    (row["id"], row["attempts"], now),
                ).rowcount
            if not claimed:
                continue
            processed += 1
            attempt = row["attempts"] + 1
            try:
                external_id = self.saas.create_ticket(
                    subject=row["subject"],
                    description=row["description"],
                    idempotency_key=row["idempotency_key"],
                )
            except DeliveryError as error:
                self._record_failure(row["id"], attempt, error)
            else:
                with self._connect() as db:
                    db.execute(
                        "UPDATE tickets SET status = 'delivered', external_id = ?, updated_at = ? WHERE id = ?",
                        (external_id, self.clock(), row["id"]),
                    )
                    db.execute(
                        "UPDATE outbox SET state = 'delivered', attempts = ?, last_error = NULL WHERE ticket_id = ?",
                        (attempt, row["id"]),
                    )
                    self._audit(
                        db, row["id"], "delivered", {"attempt": attempt, "external_id": external_id}
                    )
        return processed

    def _record_failure(self, ticket_id: str, attempt: int, error: Exception) -> None:
        now = self.clock()
        message = f"{type(error).__name__}: {error}"[:500]
        with self._connect() as db:
            if attempt >= self.max_attempts:
                db.execute(
                    "UPDATE tickets SET status = 'dead_letter', updated_at = ? WHERE id = ?",
                    (now, ticket_id),
                )
                db.execute(
                    "UPDATE outbox SET state = 'dead_letter', attempts = ?, last_error = ? WHERE ticket_id = ?",
                    (attempt, message, ticket_id),
                )
                self._audit(db, ticket_id, "dead_lettered", {"attempt": attempt, "error": message})
                return
            delay = min(
                self.base_backoff_seconds * (2 ** (attempt - 1)), self.max_backoff_seconds
            )
            db.execute(
                """UPDATE outbox SET state = 'queued', attempts = ?, next_attempt_at = ?,
                   last_error = ? WHERE ticket_id = ?""",
                (attempt, now + delay, message, ticket_id),
            )
            self._audit(
                db, ticket_id, "retry_scheduled", {"attempt": attempt, "delay_seconds": delay}
            )

    def get_delivery_status(self, ticket_id: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT t.*, o.attempts, o.next_attempt_at, o.last_error
                   FROM tickets t JOIN outbox o ON o.ticket_id = t.id WHERE t.id = ?""",
                (ticket_id,),
            ).fetchone()
        return None if row is None else self._ticket_dict(row)

    def get_audit_trail(self, ticket_id: str) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT event, details, occurred_at FROM audit_log WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            ).fetchall()
        return [
            {"event": row["event"], "details": json.loads(row["details"]), "at": row["occurred_at"]}
            for row in rows
        ]

    @staticmethod
    def _ticket_dict(row: sqlite3.Row) -> dict[str, object]:
        keys = set(row.keys())
        result: dict[str, object] = {
            "ticket_id": row["id"],
            "status": row["status"],
            "external_id": row["external_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for key in ("attempts", "next_attempt_at", "last_error"):
            if key in keys:
                result[key] = row[key]
        return result
