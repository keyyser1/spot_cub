from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models
import auth_utils
import session_utils

router = APIRouter()
templates = Jinja2Templates(directory="templates")
from datetime import timedelta as _timedelta
templates.env.globals["timedelta"] = _timedelta


@router.get("/", response_class=HTMLResponse)
async def planning_page(request: Request, semaine: int = 0, db: Session = Depends(get_db)):
    # Génère les sessions manquantes
    session_utils.ensure_sessions(db)

    planning, monday, sunday = session_utils.get_weekly_planning(db, week_offset=semaine)
    user = auth_utils.get_current_user(request, db)

    # Récupérer les réservations de l'utilisateur connecté
    user_bookings = set()
    if user:
        bookings = (
            db.query(models.Booking)
            .filter(models.Booking.user_id == user.id, models.Booking.statut == "confirme")
            .all()
        )
        user_bookings = {b.session_id for b in bookings}

    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    return templates.TemplateResponse("planning.html", {
        "request": request,
        "user": user,
        "planning": planning,
        "jours": jours,
        "monday": monday,
        "sunday": sunday,
        "semaine": semaine,
        "user_bookings": user_bookings,
    })


@router.post("/reserver/{session_id}")
async def reserver(request: Request, session_id: int, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not user.has_active_subscription:
        return RedirectResponse("/tarifs?message=abonnement_requis", status_code=302)

    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    if not session or session.annulee:
        raise HTTPException(status_code=404, detail="Séance introuvable")

    # Déjà inscrit ?
    existing = (
        db.query(models.Booking)
        .filter(
            models.Booking.user_id == user.id,
            models.Booking.session_id == session_id,
            models.Booking.statut == "confirme",
        )
        .first()
    )
    if existing:
        return RedirectResponse("/planning?msg=deja_inscrit", status_code=302)

    if session.places_restantes <= 0:
        raise HTTPException(status_code=400, detail="Plus de places disponibles")

    booking = models.Booking(user_id=user.id, session_id=session_id)
    session.places_restantes -= 1
    db.add(booking)
    db.commit()

    return RedirectResponse("/planning?msg=reservation_ok", status_code=302)


@router.post("/annuler/{booking_id}")
async def annuler(request: Request, booking_id: int, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    booking = (
        db.query(models.Booking)
        .filter(models.Booking.id == booking_id, models.Booking.user_id == user.id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Réservation introuvable")

    booking.statut = "annule"
    booking.session.places_restantes += 1
    db.commit()

    return RedirectResponse("/dashboard?msg=annulation_ok", status_code=302)
