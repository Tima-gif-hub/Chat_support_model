from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from .domain import RuntimeEvent, new_id, utc_now
from .errors import ConflictError, NotFoundError


def normalize_complaint(value: str) -> str:
    return " ".join(value.casefold().split())


def complaint_key(workspace_id: str, conversation_id: str, text: str) -> str:
    raw = f"{workspace_id}\0{conversation_id}\0{normalize_complaint(text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS conversations (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, customer_id TEXT,
 summary TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 role TEXT NOT NULL,
 content TEXT NOT NULL, request_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaint_drafts (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 payload TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','awaiting_confirmation','failed')),
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaints (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
 conversation_id TEXT NOT NULL REFERENCES conversations(id),
 customer_id TEXT, complaint_text TEXT NOT NULL, category TEXT NOT NULL CHECK(category='complaint'),
 complaint_type TEXT NOT NULL, customer_context TEXT NOT NULL, consent_source TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
 internal_notes TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaint_outbox (
 id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES complaints(id),
 event_type TEXT NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL, published_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
 id TEXT PRIMARY KEY, event_type TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT,
 aggregate_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
 id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id), rating INTEGER NOT NULL,
 comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, UNIQUE(message_id)
);
CREATE TABLE IF NOT EXISTS runtime_events (
 conversation_id TEXT NOT NULL REFERENCES conversations(id), sequence INTEGER NOT NULL,
 request_id TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(conversation_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_complaints_open ON complaints(status, created_at);
"""


class SQLiteRepository:
    """Transactional reference repository used for tests and the CPU-local runtime."""

    def __init__(self, path: str = ":memory:"):
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.connection.executescript(SCHEMA)

    def _transaction(self, operation: Callable[[sqlite3.Connection], Any]) -> Any:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                result = operation(self.connection)
                self.connection.execute("COMMIT")
                return result
            except Exception:
                self.connection.execute("ROLLBACK")
                raise

    def create_conversation(
        self, workspace_id: str, customer_id: str | None, expires_at: str
    ) -> dict[str, Any]:
        item = {
            "id": new_id("cnv"),
            "workspace_id": workspace_id,
            "customer_id": customer_id,
            "summary": "",
            "created_at": utc_now(),
            "expires_at": expires_at,
        }
        with self._lock:
            self.connection.execute(
                "INSERT INTO conversations VALUES "
                "(:id,:workspace_id,:customer_id,:summary,:created_at,:expires_at)",
                item,
            )
        return item

    def conversation(self, conversation_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM conversations WHERE id=?", (conversation_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("conversation not found")
        result = dict(row)
        result["messages"] = self.messages(conversation_id)
        return result

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, role, content, request_id, created_at FROM messages "
            "WHERE conversation_id=? ORDER BY created_at,id",
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_summary(self, conversation_id: str, summary: str) -> None:
        with self._lock:
            self.connection.execute(
                "UPDATE conversations SET summary=? WHERE id=?", (summary, conversation_id)
            )

    def add_message(
        self, conversation_id: str, role: str, content: str, request_id: str | None
    ) -> str:
        message_id = new_id("msg")
        with self._lock:
            self.connection.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                (message_id, conversation_id, role, content, request_id, utc_now()),
            )
        return message_id

    def save_events(self, conversation_id: str, events: list[RuntimeEvent]) -> None:
        with self._lock:
            start = self.connection.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM runtime_events WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()[0]
            for offset, event in enumerate(events, 1):
                event.sequence = start + offset
                self.connection.execute(
                    "INSERT INTO runtime_events VALUES (?,?,?,?,?,?)",
                    (
                        conversation_id,
                        event.sequence,
                        event.request_id,
                        event.event,
                        json.dumps(event.data),
                        utc_now(),
                    ),
                )

    def events(self, conversation_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        self.conversation(conversation_id)
        rows = self.connection.execute(
            "SELECT event,request_id,sequence,data FROM runtime_events "
            "WHERE conversation_id=? AND sequence>? ORDER BY sequence",
            (conversation_id, after_sequence),
        ).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def create_draft(self, conversation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        item = {
            "id": new_id("drf"),
            "conversation_id": conversation_id,
            "payload": payload,
            "state": "awaiting_confirmation",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self.connection.execute(
                "INSERT INTO complaint_drafts VALUES (?,?,?,?,?,?)",
                (item["id"], conversation_id, json.dumps(payload), item["state"], now, now),
            )
        return item

    def draft(self, conversation_id: str, draft_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM complaint_drafts WHERE id=? AND conversation_id=?",
            (draft_id, conversation_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("complaint draft not found")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def preserve_failed_draft(self, draft_id: str) -> None:
        with self._lock:
            self.connection.execute(
                "UPDATE complaint_drafts SET state='failed',updated_at=? WHERE id=?",
                (utc_now(), draft_id),
            )

    def delete_draft(self, conversation_id: str, draft_id: str) -> None:
        with self._lock:
            count = self.connection.execute(
                "DELETE FROM complaint_drafts WHERE id=? AND conversation_id=?",
                (draft_id, conversation_id),
            ).rowcount
        if not count:
            raise NotFoundError("complaint draft not found")

    def submit_complaint(
        self,
        workspace_id: str,
        conversation_id: str,
        customer_id: str | None,
        payload: dict[str, Any],
        consent_source: str,
        actor_type: str = "customer",
    ) -> dict[str, Any]:
        key = complaint_key(workspace_id, conversation_id, payload["complaint_text"])

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            existing = connection.execute(
                "SELECT id,status,created_at FROM complaints WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing:
                connection.execute(
                    "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
                    (
                        new_id("aud"),
                        "complaint.duplicate",
                        actor_type,
                        customer_id,
                        existing["id"],
                        "{}",
                        utc_now(),
                    ),
                )
                return {
                    "complaint_id": existing["id"],
                    "status": existing["status"],
                    "duplicate": True,
                    "created_at": existing["created_at"],
                }
            now = utc_now()
            complaint_id = new_id("cmp")
            connection.execute(
                "INSERT INTO complaints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    complaint_id,
                    workspace_id,
                    conversation_id,
                    customer_id,
                    payload["complaint_text"],
                    "complaint",
                    payload["complaint_type"],
                    payload.get("customer_context", ""),
                    consent_source,
                    key,
                    "queued",
                    "",
                    1,
                    now,
                    now,
                ),
            )
            event_payload = json.dumps({"complaint_id": complaint_id, "status": "queued"})
            connection.execute(
                "INSERT INTO complaint_outbox VALUES (?,?,?,?,?,NULL)",
                (new_id("out"), complaint_id, "complaint.queued", event_payload, now),
            )
            connection.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
                (
                    new_id("aud"),
                    "complaint.created",
                    actor_type,
                    customer_id,
                    complaint_id,
                    json.dumps({"consent_source": consent_source}),
                    now,
                ),
            )
            return {
                "complaint_id": complaint_id,
                "status": "queued",
                "duplicate": False,
                "created_at": now,
            }

        return self._transaction(operation)

    def list_complaints(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM complaints"
        args: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            args = (status,)
        rows = self.connection.execute(
            query + " ORDER BY created_at DESC LIMIT ?", (*args, limit)
        ).fetchall()
        return [dict(row) for row in rows]

    def complaint(self, complaint_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM complaints WHERE id=?", (complaint_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("complaint not found")
        return dict(row)

    def update_complaint(
        self, complaint_id: str, version: int, status: str, internal_notes: str, actor_id: str
    ) -> dict[str, Any]:
        if status not in {"queued", "acknowledged", "resolved", "failed"}:
            raise ValueError("invalid complaint status")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            now = utc_now()
            count = connection.execute(
                "UPDATE complaints SET status=?,internal_notes=?,version=version+1,updated_at=? "
                "WHERE id=? AND version=?",
                (status, internal_notes, now, complaint_id, version),
            ).rowcount
            if not count:
                exists = connection.execute(
                    "SELECT 1 FROM complaints WHERE id=?", (complaint_id,)
                ).fetchone()
                if exists:
                    raise ConflictError("complaint version conflict")
                raise NotFoundError("complaint not found")
            connection.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
                (
                    new_id("aud"),
                    "complaint.status_changed",
                    "manager",
                    actor_id,
                    complaint_id,
                    json.dumps({"status": status}),
                    now,
                ),
            )
            return dict(
                connection.execute(
                    "SELECT * FROM complaints WHERE id=?", (complaint_id,)
                ).fetchone()
            )

        return self._transaction(operation)

    def add_feedback(self, message_id: str, rating: int, comment: str) -> dict[str, Any]:
        if rating not in {-1, 1}:
            raise ValueError("rating must be -1 or 1")
        item = {
            "id": new_id("fdb"),
            "message_id": message_id,
            "rating": rating,
            "comment": comment[:1000],
            "created_at": utc_now(),
        }
        try:
            with self._lock:
                self.connection.execute(
                    "INSERT INTO feedback VALUES (:id,:message_id,:rating,:comment,:created_at)",
                    item,
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError("feedback already exists or message is unknown") from exc
        return item

    def message_conversation(self, message_id: str) -> str:
        row = self.connection.execute(
            "SELECT conversation_id FROM messages WHERE id=?", (message_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("message not found")
        return str(row[0])

    def audit_events(self, aggregate_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM audit_events WHERE aggregate_id=? ORDER BY created_at,id",
            (aggregate_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def ready(self) -> bool:
        try:
            return self.connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False
