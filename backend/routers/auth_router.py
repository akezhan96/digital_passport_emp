from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
import os
import time
import threading
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import User, AuditLog
from auth import verify_password, issue_token, current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_attempts = {}
_lock = threading.Lock()


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login")
def login(payload: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip()
    password = payload.password
    key = request.client.host if request.client else "local"
    now = time.monotonic()
    with _lock:
        recent = [t for t in _attempts.get(key, []) if now - t < 60]
        if len(recent) >= 10:
            raise HTTPException(429, "Слишком много попыток. Подождите минуту / Әрекет тым көп. Бір минут күтіңіз")
        _attempts[key] = recent + [now]

    user = db.query(User).filter(User.username == username).first()

    # Same message either way, so the response cannot enumerate accounts.
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Неверный логин или пароль")

    user.last_login_at = datetime.utcnow()
    db.add(AuditLog(action="login", entity_type="user", entity_id=user.id,
                    changed_by=user.username))
    db.commit()

    token = issue_token(user)
    with _lock:
        _attempts.pop(key, None)
    response.set_cookie("hr_session", token, httponly=True, samesite="strict",
                        secure=os.getenv("COOKIE_SECURE", "0") == "1", max_age=43200)
    response.headers["Cache-Control"] = "no-store"
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == current_user(request)["sub"]).first()
    if user:
        user.auth_version = (user.auth_version or 0) + 1
        db.commit()
    response.delete_cookie("hr_session")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    payload = current_user(request)
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(401, "Учётная запись недоступна")
    return {
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
    }
