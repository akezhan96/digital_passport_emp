"""Authentication and role gating.

Two roles:
  admin  -- full access: catalogues, custom fields, methodology, employee
            data entry and verification, decisions, audit trail.
  viewer -- read and analyse: browse profiles, vacancies, run matching and
            read the calculation cards. No writes, no audit trail.

Scope note: this is credential auth suitable for an internal demo, not an
identity system. Passwords are PBKDF2-hashed and tokens are HMAC-signed, but
there is no refresh, revocation, lockout or MFA, and the signing key falls
back to a constant when AUTH_SECRET is unset.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from models import User
from runtime import PRODUCTION

SECRET = os.getenv("AUTH_SECRET", "dev-only-secret-change-me").encode()
if PRODUCTION and (len(SECRET) < 32 or SECRET == b"dev-only-secret-change-me"):
    raise RuntimeError("Production requires a random AUTH_SECRET of at least 32 characters")
TOKEN_TTL_SECONDS = 12 * 60 * 60
PBKDF2_ROUNDS = 120_000


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 salt.encode(), PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     salt.encode(), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(user: User) -> str:
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
        "ver": user.auth_version or 0,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def read_token(token: str) -> Optional[dict]:
    """Return the payload when the signature and expiry are both good."""
    try:
        body, signature = token.split(".")
    except ValueError:
        return None

    expected = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("exp"), (int, float)):
        return None
    if payload.get("exp", 0) < time.time() or payload.get("role") not in ("admin", "viewer", "demo_editor"):
        return None
    return payload


# ---------------------------------------------------------------------------
# Request gating
# ---------------------------------------------------------------------------

# Reachable without a token at all.
PUBLIC_PATHS = {
    "/health",
    "/api/v1/auth/login",
    "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect",
}

# Writes a viewer is allowed to perform: running an analysis is the point of
# the read-only role, and a matching run only creates a computed snapshot.
VIEWER_WRITES = {
    "/api/v1/matching-runs",
    "/api/v1/analytics/run",             # answering a question is analysis
    "/api/v1/analytics/employee-ranking",
    "/api/v1/analytics/disposal-statistics",
    "/api/v1/analytics/custom/preview",  # so is building one ad hoc
    "/api/v1/analytics/saved",           # and keeping one it built
    "/api/v1/assistant/interpret",
    "/api/v1/auth/logout",
}


def _viewer_may_write(path: str) -> bool:
    """Saved queries are the viewer's own working notes, not master data, so
    the role may keep and discard them. Ownership -- a viewer touching only
    what it saved itself -- is enforced in the router, which is the only place
    that can see who owns the row."""
    return path.startswith("/api/v1/analytics/saved/") or any(
        path == prefix or path.startswith(prefix + "/") for prefix in
        ("/api/v1/assistant/requests", "/api/v1/assistant/conversations", "/api/v1/assistant/reports"))

# Reads restricted to admin.
ADMIN_ONLY_READS = {"/api/v1/audit-log", "/api/v1/admin/deployment"}


def path_requires_admin(method: str, path: str) -> bool:
    if path.startswith("/api/v1/custom-values/assessment/"):
        return True
    if path.startswith("/api/v1/employees/") and path.endswith(("/history", "/usage")):
        return True
    if path in ADMIN_ONLY_READS or path.startswith("/api/v1/admin/"):
        return True
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if path in VIEWER_WRITES or _viewer_may_write(path):
        return False
    return True


def extract_token(request: Request) -> Optional[str]:
    """CLI bearer header or browser HttpOnly cookie; never URL credentials."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get("hr_session")


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if request.method == "OPTIONS" or path in PUBLIC_PATHS \
            or path.startswith("/static"):
        return await call_next(request)

    from fastapi.responses import JSONResponse

    token = extract_token(request)
    payload = read_token(token) if token else None

    if not payload:
        return JSONResponse(status_code=401,
                            content={"detail": "Требуется вход в систему"})

    # Tokens cannot outlive a disabled account, password reset or role change.
    # The two-user workstation does not need a distributed session store.
    from database import SessionLocal
    with SessionLocal() as db:
        account = db.query(User).filter(User.username == payload.get("sub")).first()
        if (not account or not account.is_active
                or (account.auth_version or 0) != payload.get("ver", 0)
                or account.role != payload.get("role")):
            return JSONResponse(status_code=401, content={"detail": "Сессия завершена / Сеанс аяқталды"})

    # Cookie sessions are HttpOnly and SameSite=Strict; also check the origin
    # for browser writes. CLI clients authenticate using the bearer header.
    if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("authorization"):
        origin = request.headers.get("origin")
        allowed = {str(request.base_url).rstrip("/")}
        allowed.update(o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip())
        if not PRODUCTION:
            allowed.update({"http://localhost:5173", "http://127.0.0.1:5173"})
        if origin and origin not in allowed:
            return JSONResponse(status_code=403, content={"detail": "Недопустимый источник запроса / Сұрау көзі рұқсат етілмеген"})

    if payload["role"] == "demo_editor":
        if (payload["sub"] != getattr(request.app.state, "demo_editor_username", None)
                or path == "/api/v1/admin" or path.startswith("/api/v1/admin/")):
            return JSONResponse(status_code=403, content={"detail": "Недостаточно прав / Рұқсат жеткіліксіз"})
        # HR handlers already implement edits for admins. The service maintenance
        # routes stay reserved for the operator, and the signed role remains distinct.
        payload = {**payload, "role": "admin"}
    if path_requires_admin(request.method, path) and payload.get("role") != "admin":
        return JSONResponse(
            status_code=403,
            content={"detail": "Недостаточно прав: действие доступно "
                               "только администратору"},
        )

    request.state.user = payload
    return await call_next(request)


def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Требуется вход в систему")
    return user


def seed_users(db: Session):
    """Create the two demo accounts if they are absent."""
    if PRODUCTION:
        return []
    demo = [
        ("admin", "admin", "admin", "Администратор системы"),
        ("user", "user", "viewer", "Пользователь (просмотр и анализ)"),
    ]
    created = []
    for username, password, role, display_name in demo:
        if db.query(User).filter(User.username == username).first():
            continue
        db.add(User(username=username, password_hash=hash_password(password),
                    role=role, display_name=display_name, is_active=True))
        created.append(username)
    if created:
        db.commit()
    return created
