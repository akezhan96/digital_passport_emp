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

SECRET = os.getenv("AUTH_SECRET", "dev-only-secret-change-me").encode()
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

    if payload.get("exp", 0) < time.time():
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
VIEWER_WRITES = {"/api/v1/matching-runs"}

# Reads restricted to admin.
ADMIN_ONLY_READS = {"/api/v1/audit-log"}


def path_requires_admin(method: str, path: str) -> bool:
    if path in ADMIN_ONLY_READS:
        return True
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    return path not in VIEWER_WRITES


def extract_token(request: Request) -> Optional[str]:
    """Header first; query string as a fallback so <img> and download links,
    which cannot carry headers, still authenticate."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


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
