from passlib.context import CryptContext
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_current_user(request: Request, db: Session) -> models.User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_login(request: Request, db: Session) -> models.User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
        )
    return user


def require_admin(request: Request, db: Session) -> models.User:
    user = require_login(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé à l'administrateur")
    return user
