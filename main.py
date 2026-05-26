import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, get_db
import models
import auth_utils
from routers import auth_router, planning_router, subscription_router, admin_router

# Créer les tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Studio Pilates", docs_url=None, redoc_url=None)

# Middleware sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "changez-moi-en-production"),
)

# Fichiers statiques & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
from datetime import timedelta as _timedelta
templates = Jinja2Templates(directory="templates")
templates.env.globals["timedelta"] = _timedelta

# Routers
app.include_router(auth_router.router, prefix="/auth")
app.include_router(planning_router.router, prefix="/planning")
app.include_router(subscription_router.router, prefix="/abonnement")
app.include_router(admin_router.router, prefix="/admin")


# ─── Pages publiques ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/tarifs", response_class=HTMLResponse)
async def tarifs(request: Request, message: str = None, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    return templates.TemplateResponse("tarifs.html", {
        "request": request,
        "user": user,
        "message": message,
    })


# ─── Espace client ────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, msg: str = None, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    from datetime import datetime
    bookings = (
        db.query(models.Booking)
        .filter(
            models.Booking.user_id == user.id,
            models.Booking.statut == "confirme",
        )
        .order_by(models.Booking.created_at.desc())
        .all()
    )
    # Séparer passé / futur
    now = datetime.utcnow()
    a_venir = [b for b in bookings if b.session.date_heure >= now]
    historique = [b for b in bookings if b.session.date_heure < now][:10]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "a_venir": a_venir,
        "historique": historique,
        "msg": msg,
    })


# ─── Créer le premier compte admin (one-shot) ─────────────────────────────────

@app.get("/setup-admin")
async def setup_admin(
    request: Request,
    secret: str,
    db: Session = Depends(get_db),
):
    setup_secret = os.getenv("SETUP_SECRET", "")
    if not setup_secret or secret != setup_secret:
        return {"error": "Non autorisé"}

    admin = db.query(models.User).filter(models.User.role == "admin").first()
    if admin:
        return {"message": "Compte admin déjà existant", "email": admin.email}

    admin_email = os.getenv("ADMIN_EMAIL", "admin@studio.fr")
    admin_password = os.getenv("ADMIN_PASSWORD", "changez-moi")

    admin = models.User(
        prenom="Admin",
        nom="Studio",
        email=admin_email,
        password_hash=auth_utils.hash_password(admin_password),
        role="admin",
    )
    db.add(admin)
    db.commit()
    return {"message": "Compte admin créé", "email": admin_email}
