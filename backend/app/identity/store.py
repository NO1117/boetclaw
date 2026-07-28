"""SQLite WAL store for users, sessions, ACL, and audit."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.identity.models import AuditRecord, ResourceAcl, SessionRecord, UserRecord, utc_now_iso

SCHEMA_VERSION = 1


class IdentityStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.identity_sqlite_path
        self._enforce_workspace_path = db_path is None
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            resolved = self.db_path.resolve()
            if ".." in self.db_path.parts:
                raise ValueError("identity sqlite path must not contain parent traversal")
            if self._enforce_workspace_path:
                workspace_root = settings.workspace_dir.resolve()
                if workspace_root not in resolved.parents and resolved != workspace_root:
                    raise ValueError("identity sqlite path must stay under workspace_dir")
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate_schema()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def backup(self, dest: Path | None = None) -> Path:
        with self._lock:
            conn = self._conn_required()
            target = dest or (self.db_path.parent / f"identity-backup-{uuid.uuid4().hex[:8]}.sqlite3")
            target.parent.mkdir(parents=True, exist_ok=True)
            backup_conn = sqlite3.connect(str(target))
            try:
                conn.backup(backup_conn)
            finally:
                backup_conn.close()
            return target

    def _conn_required(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("identity store not initialized")
        return self._conn

    def _migrate_schema(self) -> None:
        conn = self._conn_required()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if row is None:
            conn.executescript(
                """
                CREATE TABLE schema_meta (version INTEGER NOT NULL);
                INSERT INTO schema_meta(version) VALUES (1);

                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    token_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT NOT NULL DEFAULT '',
                    deleted_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_version INTEGER NOT NULL,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL DEFAULT '',
                    ip TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE INDEX idx_sessions_user ON sessions(user_id);

                CREATE TABLE login_attempts (
                    key TEXT PRIMARY KEY,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE resources (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL DEFAULT '',
                    visibility TEXT NOT NULL DEFAULT 'workspace',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id)
                );

                CREATE TABLE resource_grants (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    granted_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id, user_id)
                );

                CREATE TABLE audit_log (
                    id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT '',
                    resource_id TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL,
                    request_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX idx_audit_created ON audit_log(created_at);
                CREATE INDEX idx_audit_actor ON audit_log(actor_id, created_at);
                """
            )
            conn.commit()
            return
        version = conn.execute("SELECT version FROM schema_meta").fetchone()["version"]
        if version < SCHEMA_VERSION:
            conn.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
            conn.commit()

    # ── users ──────────────────────────────────────────────────────────

    def count_active_users(self) -> int:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT COUNT(*) AS c FROM users WHERE status = 'active'"
            ).fetchone()
            return int(row["c"])

    def count_active_owners(self) -> int:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT COUNT(*) AS c FROM users WHERE status = 'active' AND role = 'owner'"
            ).fetchone()
            return int(row["c"])

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return self._row_user(row) if row else None

    def get_user_by_username(self, username_normalized: str) -> UserRecord | None:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT * FROM users WHERE username_normalized = ?",
                (username_normalized,),
            ).fetchone()
            return self._row_user(row) if row else None

    def list_users(self, *, include_deleted: bool = False) -> list[UserRecord]:
        with self._lock:
            if include_deleted:
                rows = self._conn_required().execute(
                    "SELECT * FROM users ORDER BY created_at ASC"
                ).fetchall()
            else:
                rows = self._conn_required().execute(
                    "SELECT * FROM users WHERE status != 'deleted' ORDER BY created_at ASC"
                ).fetchall()
            return [self._row_user(r) for r in rows]

    def create_user(self, user: UserRecord) -> UserRecord:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            user.created_at = user.created_at or now
            user.updated_at = user.updated_at or now
            conn.execute(
                """
                INSERT INTO users (
                    id, username, username_normalized, display_name, status, role,
                    password_hash, token_version, created_at, updated_at,
                    last_login_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username,
                    user.username_normalized,
                    user.display_name,
                    user.status,
                    user.role,
                    user.password_hash,
                    user.token_version,
                    user.created_at,
                    user.updated_at,
                    user.last_login_at,
                    user.deleted_at,
                ),
            )
            conn.commit()
            return user

    def update_user(self, user_id: str, **fields: Any) -> UserRecord | None:
        """Update user fields. Uses a transaction for last-owner safety when needed."""
        with self._lock:
            conn = self._conn_required()
            existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                return None
            allowed = {
                "username",
                "username_normalized",
                "display_name",
                "status",
                "role",
                "password_hash",
                "token_version",
                "last_login_at",
                "deleted_at",
            }
            updates = {k: v for k, v in fields.items() if k in allowed}
            if not updates:
                return self._row_user(existing)
            updates["updated_at"] = utc_now_iso()
            cols = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE users SET {cols} WHERE id = ?",
                (*updates.values(), user_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._row_user(row) if row else None

    def bump_token_version(self, user_id: str) -> int:
        with self._lock:
            conn = self._conn_required()
            conn.execute(
                "UPDATE users SET token_version = token_version + 1, updated_at = ? WHERE id = ?",
                (utc_now_iso(), user_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT token_version FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return int(row["token_version"]) if row else 0

    def with_last_owner_guard(self, user_id: str, mutate) -> UserRecord:
        """Run mutate(conn, user_row) inside a transaction; refuse last active owner loss."""
        with self._lock:
            conn = self._conn_required()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if row is None:
                    raise LookupError("user not found")
                result = mutate(conn, row)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    # ── sessions ───────────────────────────────────────────────────────

    def create_session(self, session: SessionRecord) -> SessionRecord:
        with self._lock:
            conn = self._conn_required()
            conn.execute(
                """
                INSERT INTO sessions (
                    id, user_id, token_version, csrf_token, created_at, expires_at,
                    revoked_at, last_seen_at, ip, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.user_id,
                    session.token_version,
                    session.csrf_token,
                    session.created_at,
                    session.expires_at,
                    session.revoked_at,
                    session.last_seen_at,
                    session.ip,
                    session.user_agent,
                ),
            )
            conn.commit()
            return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return self._row_session(row) if row else None

    def list_sessions(self, user_id: str, *, active_only: bool = True) -> list[SessionRecord]:
        with self._lock:
            if active_only:
                rows = self._conn_required().execute(
                    "SELECT * FROM sessions WHERE user_id = ? AND revoked_at = '' "
                    "ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = self._conn_required().execute(
                    "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            return [self._row_session(r) for r in rows]

    def revoke_session(self, session_id: str) -> bool:
        with self._lock:
            conn = self._conn_required()
            cur = conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at = ''",
                (utc_now_iso(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def revoke_all_sessions(self, user_id: str) -> int:
        with self._lock:
            conn = self._conn_required()
            cur = conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = ''",
                (utc_now_iso(), user_id),
            )
            conn.commit()
            return cur.rowcount

    def touch_session(self, session_id: str) -> None:
        with self._lock:
            conn = self._conn_required()
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
                (utc_now_iso(), session_id),
            )
            conn.commit()

    # ── login lockout ──────────────────────────────────────────────────

    def get_login_attempt(self, key: str) -> tuple[int, float]:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT fail_count, locked_until FROM login_attempts WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return 0, 0.0
            return int(row["fail_count"]), float(row["locked_until"])

    def record_login_failure(self, key: str, *, now: float, lock_seconds: float) -> tuple[int, float]:
        with self._lock:
            conn = self._conn_required()
            fail_count, locked_until = self.get_login_attempt(key)
            fail_count += 1
            # Escalating lock: 0,0,30,60,120... after 3+ failures
            if fail_count >= 3:
                locked_until = now + lock_seconds * (2 ** max(fail_count - 3, 0))
            conn.execute(
                """
                INSERT INTO login_attempts(key, fail_count, locked_until, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    fail_count = excluded.fail_count,
                    locked_until = excluded.locked_until,
                    updated_at = excluded.updated_at
                """,
                (key, fail_count, locked_until, now),
            )
            conn.commit()
            return fail_count, locked_until

    def clear_login_attempts(self, key: str) -> None:
        with self._lock:
            conn = self._conn_required()
            conn.execute("DELETE FROM login_attempts WHERE key = ?", (key,))
            conn.commit()

    # ── resource ACL ───────────────────────────────────────────────────

    def get_resource_acl(self, resource_type: str, resource_id: str) -> ResourceAcl | None:
        with self._lock:
            conn = self._conn_required()
            row = conn.execute(
                "SELECT * FROM resources WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            ).fetchone()
            if row is None:
                return None
            grants = conn.execute(
                "SELECT user_id, level, granted_by, created_at FROM resource_grants "
                "WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            ).fetchall()
            return ResourceAcl(
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                owner_user_id=row["owner_user_id"],
                visibility=row["visibility"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                grants=[
                    {
                        "user_id": g["user_id"],
                        "level": g["level"],
                        "granted_by": g["granted_by"],
                        "created_at": g["created_at"],
                    }
                    for g in grants
                ],
            )

    def upsert_resource_acl(
        self,
        resource_type: str,
        resource_id: str,
        *,
        owner_user_id: str | None = None,
        visibility: str | None = None,
    ) -> ResourceAcl:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            existing = conn.execute(
                "SELECT * FROM resources WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO resources(resource_type, resource_id, owner_user_id, visibility, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resource_type,
                        resource_id,
                        owner_user_id or "",
                        visibility or "workspace",
                        now,
                        now,
                    ),
                )
            else:
                new_owner = existing["owner_user_id"] if owner_user_id is None else owner_user_id
                new_vis = existing["visibility"] if visibility is None else visibility
                conn.execute(
                    """
                    UPDATE resources SET owner_user_id = ?, visibility = ?, updated_at = ?
                    WHERE resource_type = ? AND resource_id = ?
                    """,
                    (new_owner, new_vis, now, resource_type, resource_id),
                )
            conn.commit()
            acl = self.get_resource_acl(resource_type, resource_id)
            assert acl is not None
            return acl

    def set_grant(
        self,
        resource_type: str,
        resource_id: str,
        user_id: str,
        level: str,
        granted_by: str = "",
    ) -> None:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            # Ensure resource row exists
            if self.get_resource_acl(resource_type, resource_id) is None:
                self.upsert_resource_acl(resource_type, resource_id)
            conn.execute(
                """
                INSERT INTO resource_grants(resource_type, resource_id, user_id, level, granted_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_type, resource_id, user_id) DO UPDATE SET
                    level = excluded.level,
                    granted_by = excluded.granted_by,
                    created_at = excluded.created_at
                """,
                (resource_type, resource_id, user_id, level, granted_by, now),
            )
            conn.commit()

    def revoke_grant(self, resource_type: str, resource_id: str, user_id: str) -> bool:
        with self._lock:
            conn = self._conn_required()
            cur = conn.execute(
                "DELETE FROM resource_grants WHERE resource_type = ? AND resource_id = ? AND user_id = ?",
                (resource_type, resource_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def list_resource_ids_for_user(
        self, resource_type: str, user_id: str
    ) -> list[str]:
        with self._lock:
            rows = self._conn_required().execute(
                """
                SELECT resource_id FROM resources
                WHERE resource_type = ? AND (
                    owner_user_id = ? OR visibility = 'workspace'
                    OR resource_id IN (
                        SELECT resource_id FROM resource_grants
                        WHERE resource_type = ? AND user_id = ?
                    )
                )
                """,
                (resource_type, user_id, resource_type, user_id),
            ).fetchall()
            return [r["resource_id"] for r in rows]

    # ── audit ──────────────────────────────────────────────────────────

    def append_audit(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            conn = self._conn_required()
            record.created_at = record.created_at or utc_now_iso()
            conn.execute(
                """
                INSERT INTO audit_log (
                    id, actor_id, actor_type, action, resource_type, resource_id,
                    result, request_id, source, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.actor_id,
                    record.actor_type,
                    record.action,
                    record.resource_type,
                    record.resource_id,
                    record.result,
                    record.request_id,
                    record.source,
                    record.detail,
                    record.created_at,
                ),
            )
            conn.commit()
            return record

    def query_audit(
        self,
        *,
        actor_id: str | None = None,
        after: str | None = None,
        limit: int = 50,
    ) -> list[AuditRecord]:
        with self._lock:
            clauses: list[str] = []
            params: list[Any] = []
            if actor_id:
                clauses.append("actor_id = ?")
                params.append(actor_id)
            if after:
                clauses.append("created_at > ?")
                params.append(after)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(min(max(limit, 1), 200))
            rows = self._conn_required().execute(
                f"SELECT * FROM audit_log {where} ORDER BY created_at ASC LIMIT ?",
                params,
            ).fetchall()
            return [self._row_audit(r) for r in rows]

    @staticmethod
    def _row_user(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            username=row["username"],
            username_normalized=row["username_normalized"],
            display_name=row["display_name"],
            status=row["status"],
            role=row["role"],
            password_hash=row["password_hash"],
            token_version=row["token_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"] or "",
            deleted_at=row["deleted_at"] or "",
        )

    @staticmethod
    def _row_session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            token_version=row["token_version"],
            csrf_token=row["csrf_token"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"] or "",
            last_seen_at=row["last_seen_at"] or "",
            ip=row["ip"] or "",
            user_agent=row["user_agent"] or "",
        )

    @staticmethod
    def _row_audit(row: sqlite3.Row) -> AuditRecord:
        return AuditRecord(
            id=row["id"],
            actor_id=row["actor_id"],
            actor_type=row["actor_type"],
            action=row["action"],
            resource_type=row["resource_type"] or "",
            resource_id=row["resource_id"] or "",
            result=row["result"],
            request_id=row["request_id"] or "",
            source=row["source"] or "",
            detail=row["detail"] or "",
            created_at=row["created_at"],
        )


identity_store = IdentityStore()
