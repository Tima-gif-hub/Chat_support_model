from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

from .domain import RuntimeEvent, new_id, utc_now
from .errors import ConflictError, NotFoundError
from .storage import complaint_key


class PostgresRepository:
    """Production DB-API adapter. psycopg is imported only when this adapter is selected."""

    def __init__(self, database_url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - deployment packaging
            raise RuntimeError("PostgreSQL mode requires psycopg") from exc
        self.connection = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)
        self._lock = threading.RLock()

    def _transaction(self, operation: Callable[[Any], Any]) -> Any:
        with self._lock, self.connection.transaction():
            return operation(self.connection)

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
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO runtime.conversations "
                "(id,workspace_id,customer_id,summary,created_at,expires_at) "
                "VALUES (%(id)s,%(workspace_id)s,%(customer_id)s,%(summary)s,"
                "%(created_at)s,%(expires_at)s)",
                item,
            )
        return item

    def conversation(self, conversation_id: str) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM runtime.conversations WHERE id=%s", (conversation_id,))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("conversation not found")
        result = dict(row)
        result["created_at"] = str(result["created_at"])
        result["expires_at"] = str(result["expires_at"])
        result["messages"] = self.messages(conversation_id)
        return result

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,role,content,request_id,created_at FROM runtime.messages "
                "WHERE conversation_id=%s ORDER BY created_at,id",
                (conversation_id,),
            )
            messages = [dict(row) for row in cursor.fetchall()]
            # Keep the repository boundary JSON-safe. psycopg returns a Python
            # datetime for timestamptz, while the SQLite reference stores the
            # ISO string; provider history is serialized into model requests.
            for message in messages:
                message["created_at"] = str(message["created_at"])
            return messages

    def set_summary(self, conversation_id: str, summary: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE runtime.conversations SET summary=%s WHERE id=%s",
                (summary, conversation_id),
            )

    def add_message(
        self, conversation_id: str, role: str, content: str, request_id: str | None
    ) -> str:
        message_id = new_id("msg")
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO runtime.messages "
                "(id,conversation_id,role,content,request_id,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (message_id, conversation_id, role, content, request_id, utc_now()),
            )
        return message_id

    def save_events(self, conversation_id: str, events: list[RuntimeEvent]) -> None:
        def operation(connection: Any) -> None:
            with connection.cursor() as cursor:
                # Lock the parent row before calculating MAX(sequence).  A
                # FOR UPDATE on an aggregate query is rejected by PostgreSQL
                # and would make concurrent SSE requests fail.
                cursor.execute(
                    "SELECT id FROM runtime.conversations WHERE id=%s FOR UPDATE",
                    (conversation_id,),
                )
                cursor.execute(
                    "SELECT COALESCE(MAX(sequence),0) AS sequence FROM runtime.events "
                    "WHERE conversation_id=%s",
                    (conversation_id,),
                )
                start = cursor.fetchone()["sequence"]
                for offset, event in enumerate(events, 1):
                    event.sequence = start + offset
                    cursor.execute(
                        "INSERT INTO runtime.events "
                        "(conversation_id,sequence,request_id,event,data,created_at) "
                        "VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                        (
                            conversation_id,
                            event.sequence,
                            event.request_id,
                            event.event,
                            json.dumps(event.data),
                            utc_now(),
                        ),
                    )

        self._transaction(operation)

    def events(self, conversation_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        self.conversation(conversation_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT event,request_id,sequence,data FROM runtime.events "
                "WHERE conversation_id=%s AND sequence>%s ORDER BY sequence",
                (conversation_id, after_sequence),
            )
            return [dict(row) for row in cursor.fetchall()]

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
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO runtime.complaint_drafts "
                "(id,conversation_id,payload,state,created_at,updated_at) "
                "VALUES (%s,%s,%s::jsonb,%s,%s,%s)",
                (item["id"], conversation_id, json.dumps(payload), item["state"], now, now),
            )
        return item

    def draft(self, conversation_id: str, draft_id: str) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM runtime.complaint_drafts WHERE id=%s AND conversation_id=%s",
                (draft_id, conversation_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("complaint draft not found")
        return dict(row)

    def preserve_failed_draft(self, draft_id: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE runtime.complaint_drafts SET state='failed',updated_at=%s WHERE id=%s",
                (utc_now(), draft_id),
            )

    def delete_draft(self, conversation_id: str, draft_id: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM runtime.complaint_drafts WHERE id=%s AND conversation_id=%s",
                (draft_id, conversation_id),
            )
            count = cursor.rowcount
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

        def operation(connection: Any) -> dict[str, Any]:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id,status,created_at FROM runtime.complaints "
                    "WHERE idempotency_key=%s FOR UPDATE",
                    (key,),
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        "INSERT INTO audit.events "
                        "(id,event_type,actor_type,actor_id,aggregate_id,payload,created_at) "
                        "VALUES (%s,'complaint.duplicate',%s,%s,%s,'{}'::jsonb,%s)",
                        (new_id("aud"), actor_type, customer_id, existing["id"], utc_now()),
                    )
                    return {
                        "complaint_id": existing["id"],
                        "status": existing["status"],
                        "duplicate": True,
                        "created_at": str(existing["created_at"]),
                    }
                now, complaint_id = utc_now(), new_id("cmp")
                cursor.execute(
                    "INSERT INTO runtime.complaints "
                    "(id,workspace_id,conversation_id,customer_id,complaint_text,category,"
                    "complaint_type,customer_context,consent_source,idempotency_key,status,"
                    "internal_notes,version,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,'complaint',%s,%s,%s,%s,'queued','',1,%s,%s)",
                    (
                        complaint_id,
                        workspace_id,
                        conversation_id,
                        customer_id,
                        payload["complaint_text"],
                        payload["complaint_type"],
                        payload.get("customer_context", ""),
                        consent_source,
                        key,
                        now,
                        now,
                    ),
                )
                cursor.execute(
                    "INSERT INTO runtime.complaint_outbox "
                    "(id,complaint_id,event_type,payload,created_at) "
                    "VALUES (%s,%s,'complaint.queued',%s::jsonb,%s)",
                    (
                        new_id("out"),
                        complaint_id,
                        json.dumps({"complaint_id": complaint_id, "status": "queued"}),
                        now,
                    ),
                )
                cursor.execute(
                    "INSERT INTO audit.events "
                    "(id,event_type,actor_type,actor_id,aggregate_id,payload,created_at) "
                    "VALUES (%s,'complaint.created',%s,%s,%s,%s::jsonb,%s)",
                    (
                        new_id("aud"),
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
        query = "SELECT * FROM runtime.complaints"
        args: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=%s"
            args = (status,)
        with self.connection.cursor() as cursor:
            cursor.execute(query + " ORDER BY created_at DESC LIMIT %s", (*args, limit))
            return [dict(row) for row in cursor.fetchall()]

    def complaint(self, complaint_id: str) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM runtime.complaints WHERE id=%s", (complaint_id,))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("complaint not found")
        return dict(row)

    def update_complaint(
        self, complaint_id: str, version: int, status: str, internal_notes: str, actor_id: str
    ) -> dict[str, Any]:
        if status not in {"queued", "acknowledged", "resolved", "failed"}:
            raise ValueError("invalid complaint status")

        def operation(connection: Any) -> dict[str, Any]:
            now = utc_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE runtime.complaints SET status=%s,internal_notes=%s,"
                    "version=version+1,updated_at=%s WHERE id=%s AND version=%s RETURNING *",
                    (status, internal_notes, now, complaint_id, version),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute("SELECT 1 FROM runtime.complaints WHERE id=%s", (complaint_id,))
                    if cursor.fetchone():
                        raise ConflictError("complaint version conflict")
                    raise NotFoundError("complaint not found")
                cursor.execute(
                    "INSERT INTO audit.events "
                    "(id,event_type,actor_type,actor_id,aggregate_id,payload,created_at) "
                    "VALUES (%s,'complaint.status_changed','manager',%s,%s,%s::jsonb,%s)",
                    (new_id("aud"), actor_id, complaint_id, json.dumps({"status": status}), now),
                )
                return dict(row)

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
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO runtime.feedback (id,message_id,rating,comment,created_at) "
                    "VALUES (%(id)s,%(message_id)s,%(rating)s,%(comment)s,%(created_at)s)",
                    item,
                )
        except Exception as exc:
            if getattr(exc, "sqlstate", "") == "23505":
                raise ConflictError("feedback already exists") from exc
            raise
        return item

    def message_conversation(self, message_id: str) -> str:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT conversation_id FROM runtime.messages WHERE id=%s", (message_id,)
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("message not found")
        return str(row["conversation_id"])

    def audit_events(self, aggregate_id: str) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM audit.events WHERE aggregate_id=%s ORDER BY created_at,id",
                (aggregate_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def ready(self) -> bool:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('runtime.conversations') IS NOT NULL "
                    "AND to_regclass('runtime.events') IS NOT NULL "
                    "AND to_regclass('audit.events') IS NOT NULL AS ready"
                )
                row = cursor.fetchone()
                return bool(row) and bool(row["ready"])
        except Exception:
            return False
