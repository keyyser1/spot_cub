from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import models


def ensure_sessions(db: Session, weeks_ahead: int = 4):
    """Génère automatiquement les sessions pour les N prochaines semaines."""
    today = datetime.utcnow().date()
    # Début de la semaine courante (lundi)
    monday = today - timedelta(days=today.weekday())

    courses = db.query(models.Course).filter(models.Course.actif == True).all()

    for course in courses:
        for week_offset in range(weeks_ahead):
            week_start = monday + timedelta(weeks=week_offset)
            session_date = week_start + timedelta(days=course.jour_semaine)

            # Parser l'heure
            heure, minute = map(int, course.heure.split(":"))
            session_dt = datetime(
                session_date.year, session_date.month, session_date.day,
                heure, minute
            )

            # Ne pas créer de sessions passées
            if session_dt < datetime.utcnow() - timedelta(hours=1):
                continue

            # Vérifier si la session existe déjà
            exists = db.query(models.ClassSession).filter(
                models.ClassSession.course_id == course.id,
                models.ClassSession.date_heure == session_dt,
            ).first()

            if not exists:
                session = models.ClassSession(
                    course_id=course.id,
                    date_heure=session_dt,
                    places_restantes=course.capacite_max,
                )
                db.add(session)

    db.commit()


def get_weekly_planning(db: Session, week_offset: int = 0):
    """Retourne le planning pour une semaine donnée, organisé par jour."""
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)

    monday_dt = datetime(monday.year, monday.month, monday.day, 0, 0)
    sunday_dt = datetime(sunday.year, sunday.month, sunday.day, 23, 59)

    sessions = (
        db.query(models.ClassSession)
        .filter(
            models.ClassSession.date_heure >= monday_dt,
            models.ClassSession.date_heure <= sunday_dt,
            models.ClassSession.annulee == False,
        )
        .order_by(models.ClassSession.date_heure)
        .all()
    )

    # Organiser par jour (0=Lundi … 6=Dimanche)
    planning = {i: [] for i in range(7)}
    for s in sessions:
        day_idx = s.date_heure.weekday()
        planning[day_idx].append(s)

    return planning, monday, sunday
