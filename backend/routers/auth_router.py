from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User, AuditLog
from auth import verify_password, issue_token, current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
def login(payload: Dict[str, Any], db: Session = Depends(get_db)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    user = db.query(User).filter(User.username == username).first()

    # Same message either way, so the response cannot enumerate accounts.
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Неверный логин или пароль")

    user.last_login_at = datetime.utcnow()
    db.add(AuditLog(action="login", entity_type="user", entity_id=user.id,
                    changed_by=user.username))
    db.commit()

    return {
        "token": issue_token(user),
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
    }


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
