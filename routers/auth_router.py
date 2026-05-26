from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models
import auth_utils

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if not user or not auth_utils.verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Email ou mot de passe incorrect"},
        )
    request.session["user_id"] = user.id
    if user.role == "admin":
        return RedirectResponse("/admin/dashboard", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": None})


@router.post("/register")
async def register(
    request: Request,
    prenom: str = Form(...),
    nom: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(models.User).filter(models.User.email == email.lower()).first():
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Cet email est déjà utilisé"},
        )
    user = models.User(
        prenom=prenom,
        nom=nom,
        email=email.lower(),
        password_hash=auth_utils.hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
