from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
import auth_utils
import session_utils
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")
from datetime import timedelta as _timedelta
templates.env.globals["timedelta"] = _timedelta


def _get_admin(request: Request, db: Session):
    user = auth_utils.get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=303, headers={"Location": "/"})
    return user


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    admin = _get_admin(request, db)
    session_utils.ensure_sessions(db)

    total_clients = db.query(models.User).filter(models.User.role == "client").count()
    abonnes_actifs = (
        db.query(models.Subscription)
        .filter(models.Subscription.statut == "actif")
        .count()
    )
    total_cours = db.query(models.Course).filter(models.Course.actif == True).count()

    # Prochaines sessions (7 jours)
    from datetime import timedelta
    now = datetime.utcnow()
    prochaines = (
        db.query(models.ClassSession)
        .filter(
            models.ClassSession.date_heure >= now,
            models.ClassSession.date_heure <= now + timedelta(days=7),
            models.ClassSession.annulee == False,
        )
        .order_by(models.ClassSession.date_heure)
        .limit(10)
        .all()
    )

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": admin,
        "total_clients": total_clients,
        "abonnes_actifs": abonnes_actifs,
        "total_cours": total_cours,
        "prochaines": prochaines,
    })


# ─── Gestion des cours ────────────────────────────────────────────────────────

@router.get("/cours", response_class=HTMLResponse)
async def admin_cours(request: Request, db: Session = Depends(get_db)):
    admin = _get_admin(request, db)
    cours = db.query(models.Course).order_by(models.Course.jour_semaine, models.Course.heure).all()
    return templates.TemplateResponse("admin/courses.html", {
        "request": request,
        "user": admin,
        "cours": cours,
    })


@router.post("/cours/creer")
async def creer_cours(
    request: Request,
    titre: str = Form(...),
    description: str = Form(""),
    niveau: str = Form("Tous niveaux"),
    jour_semaine: int = Form(...),
    heure: str = Form(...),
    duree_minutes: int = Form(60),
    capacite_max: int = Form(10),
    db: Session = Depends(get_db),
):
    _get_admin(request, db)
    cours = models.Course(
        titre=titre,
        description=description,
        niveau=niveau,
        jour_semaine=jour_semaine,
        heure=heure,
        duree_minutes=duree_minutes,
        capacite_max=capacite_max,
    )
    db.add(cours)
    db.commit()
    return RedirectResponse("/admin/cours", status_code=302)


@router.post("/cours/{cours_id}/toggle")
async def toggle_cours(request: Request, cours_id: int, db: Session = Depends(get_db)):
    _get_admin(request, db)
    cours = db.query(models.Course).filter(models.Course.id == cours_id).first()
    if not cours:
        raise HTTPException(status_code=404)
    cours.actif = not cours.actif
    db.commit()
    return RedirectResponse("/admin/cours", status_code=302)


@router.post("/cours/{cours_id}/supprimer")
async def supprimer_cours(request: Request, cours_id: int, db: Session = Depends(get_db)):
    _get_admin(request, db)
    cours = db.query(models.Course).filter(models.Course.id == cours_id).first()
    if not cours:
        raise HTTPException(status_code=404)
    db.delete(cours)
    db.commit()
    return RedirectResponse("/admin/cours", status_code=302)


# ─── Gestion des sessions ─────────────────────────────────────────────────────

@router.get("/sessions", response_class=HTMLResponse)
async def admin_sessions(request: Request, semaine: int = 0, db: Session = Depends(get_db)):
    admin = _get_admin(request, db)
    session_utils.ensure_sessions(db)
    planning, monday, sunday = session_utils.get_weekly_planning(db, week_offset=semaine)
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    return templates.TemplateResponse("admin/sessions.html", {
        "request": request,
        "user": admin,
        "planning": planning,
        "jours": jours,
        "monday": monday,
        "sunday": sunday,
        "semaine": semaine,
    })


@router.post("/sessions/{session_id}/annuler")
async def annuler_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    _get_admin(request, db)
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404)
    session.annulee = True
    db.commit()
    return RedirectResponse("/admin/sessions", status_code=302)


# ─── Gestion des clients ──────────────────────────────────────────────────────

@router.get("/clients", response_class=HTMLResponse)
async def admin_clients(request: Request, db: Session = Depends(get_db)):
    admin = _get_admin(request, db)
    clients = (
        db.query(models.User)
        .filter(models.User.role == "client")
        .order_by(models.User.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("admin/clients.html", {
        "request": request,
        "user": admin,
        "clients": clients,
    })
