"""Identity service: bootstrap, login, users, sessions, ACL, audit."""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.identity.models import AuditRecord, ResourceAcl, SessionRecord, UserRecord, utc_now_iso
from app.identity.passwords import hash_password, needs_rehash, verify_password
from app.identity.permissions import (
    VALID_GRANT_LEVELS,
    VALID_ROLES,
    VALID_VISIBILITIES,
    GrantLevel,
    permissions_for_role,
)
from app.identity.store import IdentityStore, identity_store
from app.identity.usernames import normalize_username, validate_display_name
from app.security.console_auth import create_user_token, verify_user_token


class IdentityService:
    def __init__(self, store: IdentityStore | None = None) -> None:
        self.store = store or identity_store
        self._initialized = False

    def initialize(self) -> None:
        if not self._initialized:
            self.store.initialize()
            self._initialized = True

    def close(self) -> None:
        self.store.close()
        self._initialized = False

    # ── mode / bootstrap ───────────────────────────────────────────────

    def has_users(self) -> bool:
        self.initialize()
        return self.store.count_active_users() > 0

    def is_open_mode(self) -> bool:
        """Trusted local open mode: no users and no auth configured."""
        if self.has_users():
            return False
        return not settings.api_token and not settings.console_password

    def login_required(self) -> bool:
        if self.has_users():
            return True
        return bool(settings.console_password or settings.api_token)

    def bootstrap_needed(self) -> bool:
        return not self.has_users()

    def _client_is_local(self, client_host: str | None) -> bool:
        if not client_host:
            return False
        return client_host in {"127.0.0.1", "::1", "localhost", "testclient"}

    def can_bootstrap(self, *, client_host: str | None, bootstrap_token: str = "") -> bool:
        if not self.bootstrap_needed():
            return False
        expected = settings.bootstrap_token
        if expected and bootstrap_token and secrets.compare_digest(bootstrap_token, expected):
            return True
        if expected and not bootstrap_token:
            return False
        return self._client_is_local(client_host)

    def bootstrap_owner(
        self,
        *,
        username: str,
        password: str,
        display_name: str = "",
        client_host: str | None = None,
        bootstrap_token: str = "",
        ip: str = "",
        user_agent: str = "",
    ) -> tuple[UserRecord, SessionRecord, str]:
        self.initialize()
        if not self.can_bootstrap(client_host=client_host, bootstrap_token=bootstrap_token):
            raise HTTPException(status_code=403, detail="Bootstrap not allowed")
        if self.has_users():
            raise HTTPException(status_code=409, detail="Already bootstrapped")
        user = self._create_user_record(
            username=username,
            password=password,
            display_name=display_name or username,
            role="owner",
        )
        self.store.create_user(user)
        session, token = self._issue_session(user, ip=ip, user_agent=user_agent)
        self.audit(
            actor_id=user.id,
            actor_type="user",
            action="bootstrap.owner",
            resource_type="user",
            resource_id=user.id,
            result="success",
            source=ip,
        )
        return user, session, token

    # ── login / sessions ───────────────────────────────────────────────

    def _lock_seconds(self) -> float:
        return float(settings.login_lock_base_seconds)

    def _check_lock(self, *keys: str) -> None:
        now = time.time()
        for key in keys:
            _, locked_until = self.store.get_login_attempt(key)
            if locked_until > now:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts; try again later",
                    headers={"Retry-After": str(max(1, int(locked_until - now)))},
                )

    def _fail_login(self, *keys: str) -> None:
        now = time.time()
        for key in keys:
            self.store.record_login_failure(
                key, now=now, lock_seconds=self._lock_seconds()
            )
        # Uniform response — do not reveal whether account exists.
        raise HTTPException(status_code=401, detail="Invalid credentials")

    def login(
        self,
        *,
        username: str = "",
        password: str,
        ip: str = "",
        user_agent: str = "",
    ) -> tuple[UserRecord | None, SessionRecord | None, str, dict[str, Any]]:
        """Login with username+password, or legacy CONSOLE_PASSWORD-only."""
        self.initialize()
        account_key = f"user:{(username or '').strip().casefold() or '_'}"
        ip_key = f"ip:{ip or 'unknown'}"
        self._check_lock(account_key, ip_key)

        # Prefer user accounts when present.
        if username and self.has_users():
            try:
                norm = normalize_username(username)
            except ValueError:
                self.audit(
                    actor_id="",
                    actor_type="user",
                    action="login.failed",
                    result="denied",
                    source=ip,
                    detail="invalid_username",
                )
                self._fail_login(account_key, ip_key)
            user = self.store.get_user_by_username(norm)
            if user is None or user.status != "active":
                self.audit(
                    actor_id=user.id if user else "",
                    actor_type="user",
                    action="login.failed",
                    result="denied",
                    source=ip,
                    detail="unknown_or_disabled",
                )
                self._fail_login(account_key, ip_key)
            if not verify_password(password, user.password_hash):
                self.audit(
                    actor_id=user.id,
                    actor_type="user",
                    action="login.failed",
                    resource_type="user",
                    resource_id=user.id,
                    result="denied",
                    source=ip,
                )
                self._fail_login(account_key, ip_key)
            if needs_rehash(user.password_hash):
                self.store.update_user(user.id, password_hash=hash_password(password))
            self.store.clear_login_attempts(account_key)
            self.store.clear_login_attempts(ip_key)
            self.store.update_user(user.id, last_login_at=utc_now_iso())
            session, token = self._issue_session(user, ip=ip, user_agent=user_agent)
            self.audit(
                actor_id=user.id,
                actor_type="user",
                action="login.success",
                resource_type="user",
                resource_id=user.id,
                result="success",
                source=ip,
            )
            return user, session, token, {"mode": "user"}

        # Legacy CONSOLE_PASSWORD compat (password-only or username empty).
        if settings.console_password and secrets.compare_digest(
            password, settings.console_password
        ):
            self.store.clear_login_attempts(account_key)
            self.store.clear_login_attempts(ip_key)
            from app.security.console_auth import create_console_token

            token = create_console_token(subject="console")
            self.audit(
                actor_id="console_legacy",
                actor_type="console_legacy",
                action="login.success",
                result="success",
                source=ip,
                detail="console_password",
            )
            return None, None, token, {
                "mode": "console_legacy",
                "deprecate_console_password": self.has_users(),
            }

        # Password-only against a single-user or username omitted with users:
        # still uniform failure.
        self.audit(
            actor_id="",
            actor_type="user",
            action="login.failed",
            result="denied",
            source=ip,
        )
        self._fail_login(account_key, ip_key)
        raise AssertionError("unreachable")  # pragma: no cover

    def _issue_session(
        self, user: UserRecord, *, ip: str = "", user_agent: str = ""
    ) -> tuple[SessionRecord, str]:
        ttl = max(settings.console_jwt_ttl_minutes, 1)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl)
        session = SessionRecord(
            id=uuid.uuid4().hex,
            user_id=user.id,
            token_version=user.token_version,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            last_seen_at=now.isoformat(),
            ip=ip,
            user_agent=user_agent[:256],
        )
        self.store.create_session(session)
        token = create_user_token(
            user_id=user.id,
            role=user.role,
            token_version=user.token_version,
            session_id=session.id,
            ttl_minutes=ttl,
        )
        return session, token

    def logout_session(self, session_id: str) -> None:
        self.initialize()
        if session_id:
            self.store.revoke_session(session_id)

    def revoke_all_sessions(self, user_id: str, *, bump_version: bool = True) -> int:
        self.initialize()
        if bump_version:
            self.store.bump_token_version(user_id)
        count = self.store.revoke_all_sessions(user_id)
        self.audit(
            actor_id=user_id,
            actor_type="user",
            action="sessions.revoke_all",
            resource_type="user",
            resource_id=user_id,
            result="success",
            detail=f"count={count}",
        )
        return count

    def resolve_user_token(self, token: str) -> tuple[UserRecord, SessionRecord] | None:
        self.initialize()
        payload = verify_user_token(token)
        if not payload:
            return None
        user_id = str(payload.get("sub", ""))
        session_id = str(payload.get("sid", ""))
        token_version = int(payload.get("tv", 0))
        user = self.store.get_user(user_id)
        if user is None or user.status != "active":
            return None
        if user.token_version != token_version:
            return None
        session = self.store.get_session(session_id)
        if session is None or session.revoked_at:
            return None
        if session.token_version != token_version:
            return None
        # Expiry also checked in JWT; double-check session row.
        try:
            exp = datetime.fromisoformat(session.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
        return user, session

    # ── users CRUD ─────────────────────────────────────────────────────

    def _create_user_record(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        role: str,
    ) -> UserRecord:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        norm = normalize_username(username)
        display = validate_display_name(display_name or username)
        if self.store.get_user_by_username(norm):
            raise HTTPException(status_code=409, detail="Username already exists")
        return UserRecord(
            id=uuid.uuid4().hex,
            username=username.strip(),
            username_normalized=norm,
            display_name=display,
            status="active",
            role=role,
            password_hash=hash_password(password),
            token_version=1,
        )

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str = "",
        role: str = "operator",
        actor_role: str,
        actor_id: str,
    ) -> UserRecord:
        self.initialize()
        if role == "owner" and actor_role != "owner":
            raise HTTPException(status_code=403, detail="Forbidden")
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        user = self._create_user_record(
            username=username,
            password=password,
            display_name=display_name,
            role=role,
        )
        self.store.create_user(user)
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="user.create",
            resource_type="user",
            resource_id=user.id,
            result="success",
            detail=f"role={role}",
        )
        return user

    def list_users_public(self) -> list[dict[str, Any]]:
        self.initialize()
        return [u.to_public_dict() for u in self.store.list_users()]

    def get_user_public(self, user_id: str) -> dict[str, Any] | None:
        self.initialize()
        user = self.store.get_user(user_id)
        if user is None or user.status == "deleted":
            return None
        return user.to_public_dict(permissions=list(permissions_for_role(user.role)))

    def update_user(
        self,
        user_id: str,
        *,
        actor_role: str,
        actor_id: str,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> UserRecord:
        self.initialize()

        def _mutate(conn, row):
            target_role = row["role"]
            target_status = row["status"]
            new_role = role if role is not None else target_role
            new_status = status if status is not None else target_status
            if new_role not in VALID_ROLES:
                raise HTTPException(status_code=400, detail="Invalid role")
            if new_status not in {"active", "disabled"}:
                raise HTTPException(status_code=400, detail="Invalid status")

            # admin cannot touch owners
            if target_role == "owner" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Forbidden")
            if new_role == "owner" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Forbidden")

            losing_owner = (
                target_role == "owner"
                and target_status == "active"
                and (new_role != "owner" or new_status != "active")
            )
            if losing_owner:
                owners = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE status = 'active' AND role = 'owner'"
                ).fetchone()["c"]
                if int(owners) <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail="Cannot disable, demote, or delete the last owner",
                    )

            fields: dict[str, Any] = {"updated_at": utc_now_iso()}
            if display_name is not None:
                fields["display_name"] = validate_display_name(display_name)
            if role is not None:
                fields["role"] = new_role
            if status is not None:
                fields["status"] = new_status
            if status == "disabled" or (role is not None and role != target_role):
                fields["token_version"] = int(row["token_version"]) + 1
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = ''",
                    (utc_now_iso(), user_id),
                )
            cols = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), user_id))
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self.store._row_user(updated)

        try:
            user = self.store.with_last_owner_guard(user_id, _mutate)
        except LookupError:
            raise HTTPException(status_code=404, detail="Not found") from None
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="user.update",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )
        return user

    def delete_user(self, user_id: str, *, actor_role: str, actor_id: str) -> None:
        self.initialize()

        def _mutate(conn, row):
            if row["status"] == "deleted":
                return self.store._row_user(row)
            if row["role"] == "owner" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Forbidden")
            if row["role"] == "owner" and row["status"] == "active":
                owners = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE status = 'active' AND role = 'owner'"
                ).fetchone()["c"]
                if int(owners) <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail="Cannot disable, demote, or delete the last owner",
                    )
            now = utc_now_iso()
            conn.execute(
                """
                UPDATE users SET status = 'deleted', deleted_at = ?, updated_at = ?,
                    token_version = token_version + 1
                WHERE id = ?
                """,
                (now, now, user_id),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = ''",
                (now, user_id),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self.store._row_user(updated)

        try:
            self.store.with_last_owner_guard(user_id, _mutate)
        except LookupError:
            raise HTTPException(status_code=404, detail="Not found") from None
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="user.delete",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )

    def reset_password(
        self,
        user_id: str,
        new_password: str,
        *,
        actor_role: str,
        actor_id: str,
    ) -> None:
        self.initialize()
        user = self.store.get_user(user_id)
        if user is None or user.status == "deleted":
            raise HTTPException(status_code=404, detail="Not found")
        if user.role == "owner" and actor_role != "owner":
            raise HTTPException(status_code=403, detail="Forbidden")
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        self.store.update_user(user_id, password_hash=hash_password(new_password))
        self.revoke_all_sessions(user_id, bump_version=True)
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="user.reset_password",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )

    def change_own_password(
        self, user_id: str, *, current_password: str, new_password: str
    ) -> SessionRecord:
        self.initialize()
        user = self.store.get_user(user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=404, detail="Not found")
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        self.store.update_user(user_id, password_hash=hash_password(new_password))
        self.revoke_all_sessions(user_id, bump_version=True)
        user = self.store.get_user(user_id)
        assert user is not None
        session, _token = self._issue_session(user)
        self.audit(
            actor_id=user_id,
            actor_type="user",
            action="password.change",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )
        return session

    # ── resource ACL ───────────────────────────────────────────────────

    def ensure_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        owner_user_id: str = "",
        visibility: str = "workspace",
    ) -> ResourceAcl:
        self.initialize()
        if visibility not in VALID_VISIBILITIES:
            raise HTTPException(status_code=400, detail="Invalid visibility")
        existing = self.store.get_resource_acl(resource_type, resource_id)
        if existing is None:
            return self.store.upsert_resource_acl(
                resource_type,
                resource_id,
                owner_user_id=owner_user_id,
                visibility=visibility,
            )
        return existing

    def set_visibility(
        self,
        resource_type: str,
        resource_id: str,
        visibility: str,
        *,
        actor_id: str,
    ) -> ResourceAcl:
        self.initialize()
        if visibility not in VALID_VISIBILITIES:
            raise HTTPException(status_code=400, detail="Invalid visibility")
        acl = self.store.upsert_resource_acl(
            resource_type, resource_id, visibility=visibility
        )
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="acl.visibility",
            resource_type=resource_type,
            resource_id=resource_id,
            result="success",
            detail=visibility,
        )
        return acl

    def grant_access(
        self,
        resource_type: str,
        resource_id: str,
        user_id: str,
        level: str,
        *,
        actor_id: str,
    ) -> ResourceAcl:
        self.initialize()
        if level not in VALID_GRANT_LEVELS:
            raise HTTPException(status_code=400, detail="Invalid grant level")
        target = self.store.get_user(user_id)
        if target is None or target.status != "active":
            raise HTTPException(status_code=404, detail="Not found")
        self.ensure_resource(resource_type, resource_id)
        self.store.set_grant(
            resource_type, resource_id, user_id, level, granted_by=actor_id
        )
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="acl.grant",
            resource_type=resource_type,
            resource_id=resource_id,
            result="success",
            detail=f"user={user_id};level={level}",
        )
        acl = self.store.get_resource_acl(resource_type, resource_id)
        assert acl is not None
        return acl

    def revoke_access(
        self,
        resource_type: str,
        resource_id: str,
        user_id: str,
        *,
        actor_id: str,
    ) -> ResourceAcl:
        self.initialize()
        self.store.revoke_grant(resource_type, resource_id, user_id)
        self.audit(
            actor_id=actor_id,
            actor_type="user",
            action="acl.revoke",
            resource_type=resource_type,
            resource_id=resource_id,
            result="success",
            detail=f"user={user_id}",
        )
        acl = self.store.get_resource_acl(resource_type, resource_id)
        if acl is None:
            return self.ensure_resource(resource_type, resource_id)
        return acl

    def get_acl(self, resource_type: str, resource_id: str) -> ResourceAcl:
        self.initialize()
        acl = self.store.get_resource_acl(resource_type, resource_id)
        if acl is None:
            return ResourceAcl(
                resource_type=resource_type,
                resource_id=resource_id,
                owner_user_id="",
                visibility="workspace",
            )
        return acl

    # ── audit ──────────────────────────────────────────────────────────

    def audit(
        self,
        *,
        actor_id: str,
        actor_type: str,
        action: str,
        result: str,
        resource_type: str = "",
        resource_id: str = "",
        request_id: str = "",
        source: str = "",
        detail: str = "",
    ) -> None:
        self.initialize()
        # Never persist secrets in detail.
        safe = detail
        for needle in ("password", "token", "api_key", "secret", "csrf"):
            if needle in safe.lower():
                safe = "[redacted]"
                break
        self.store.append_audit(
            AuditRecord(
                id=uuid.uuid4().hex,
                actor_id=actor_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                request_id=request_id,
                source=source,
                detail=safe[:500],
            )
        )

    def query_audit(
        self,
        *,
        actor_id: str | None = None,
        after: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.initialize()
        return [
            r.to_public_dict()
            for r in self.store.query_audit(actor_id=actor_id, after=after, limit=limit)
        ]


identity_service = IdentityService()
