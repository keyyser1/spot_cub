import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models
import auth_utils
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# IDs des prix Stripe (à configurer dans .env)
STRIPE_PRICES = {
    "mensuel": os.getenv("STRIPE_PRICE_MENSUEL"),
    "trimestriel": os.getenv("STRIPE_PRICE_TRIMESTRIEL"),
    "annuel": os.getenv("STRIPE_PRICE_ANNUEL"),
}
STRIPE_PRICE_PONCTUEL = os.getenv("STRIPE_PRICE_PONCTUEL")

PLANS_INFO = {
    "mensuel": {"nom": "Mensuel", "prix_affiche": "59 €/mois", "description": "Cours illimités chaque mois"},
    "trimestriel": {"nom": "Trimestriel", "prix_affiche": "149 €/trimestre", "description": "Économisez 28 € — 3 mois d'accès illimité"},
    "annuel": {"nom": "Annuel", "prix_affiche": "499 €/an", "description": "Économisez 209 € — La meilleure offre"},
}


@router.get("/checkout/{plan}")
async def checkout(request: Request, plan: str, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if plan not in STRIPE_PRICES or not STRIPE_PRICES[plan]:
        raise HTTPException(status_code=400, detail="Plan invalide ou non configuré")

    # Créer ou récupérer le client Stripe
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name,
        )
        user.stripe_customer_id = customer.id
        db.commit()

    try:
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICES[plan], "quantity": 1}],
            mode="subscription",
            success_url=f"{BASE_URL}/abonnement/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/tarifs?message=annule",
            metadata={"user_id": str(user.id), "plan": plan},
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/checkout-ponctuel/{class_session_id}")
async def checkout_ponctuel(request: Request, class_session_id: int, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not STRIPE_PRICE_PONCTUEL:
        raise HTTPException(status_code=400, detail="Tarif ponctuel non configuré")

    session_obj = db.query(models.ClassSession).filter(models.ClassSession.id == class_session_id).first()
    if not session_obj or session_obj.annulee:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    if session_obj.places_restantes <= 0:
        raise HTTPException(status_code=400, detail="Plus de places disponibles")

    # Déjà inscrit ?
    existing = (
        db.query(models.Booking)
        .filter(
            models.Booking.user_id == user.id,
            models.Booking.session_id == class_session_id,
            models.Booking.statut == "confirme",
        )
        .first()
    )
    if existing:
        return RedirectResponse("/planning?msg=deja_inscrit", status_code=302)

    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email, name=user.full_name)
        user.stripe_customer_id = customer.id
        db.commit()

    try:
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_PONCTUEL, "quantity": 1}],
            mode="payment",
            success_url=f"{BASE_URL}/planning?msg=reservation_ok",
            cancel_url=f"{BASE_URL}/planning?msg=paiement_annule",
            metadata={
                "user_id": str(user.id),
                "class_session_id": str(class_session_id),
                "type": "ponctuel",
            },
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/success")
async def success(request: Request, session_id: str, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    return RedirectResponse("/dashboard?msg=abonnement_actif", status_code=302)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Webhook invalide")

    if event["type"] == "checkout.session.completed":
        cs = event["data"]["object"]
        if cs.get("mode") == "payment" and cs.get("metadata", {}).get("type") == "ponctuel":
            _create_ponctuel_booking(db, cs)
        else:
            _activate_subscription(db, cs)

    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub_data = event["data"]["object"]
        _update_subscription(db, sub_data)

    return {"status": "ok"}


def _create_ponctuel_booking(db: Session, cs: dict):
    meta = cs.get("metadata", {})
    user_id = int(meta.get("user_id", 0))
    class_session_id = int(meta.get("class_session_id", 0))
    if not user_id or not class_session_id:
        return

    # Déjà inscrit ?
    existing = (
        db.query(models.Booking)
        .filter(
            models.Booking.user_id == user_id,
            models.Booking.session_id == class_session_id,
            models.Booking.statut == "confirme",
        )
        .first()
    )
    if existing:
        return

    session_obj = db.query(models.ClassSession).filter(models.ClassSession.id == class_session_id).first()
    if not session_obj or session_obj.annulee or session_obj.places_restantes <= 0:
        return

    booking = models.Booking(user_id=user_id, session_id=class_session_id)
    session_obj.places_restantes -= 1
    db.add(booking)
    db.commit()


def _activate_subscription(db: Session, cs: dict):
    user_id = int(cs.get("metadata", {}).get("user_id", 0))
    plan = cs.get("metadata", {}).get("plan")
    stripe_sub_id = cs.get("subscription")

    if not user_id or not plan:
        return

    # Récupérer les détails de la subscription Stripe
    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
    period_end = datetime.utcfromtimestamp(stripe_sub["current_period_end"])

    sub = db.query(models.Subscription).filter(models.Subscription.user_id == user_id).first()
    if sub:
        sub.stripe_subscription_id = stripe_sub_id
        sub.plan = plan
        sub.statut = "actif"
        sub.current_period_end = period_end
    else:
        sub = models.Subscription(
            user_id=user_id,
            stripe_subscription_id=stripe_sub_id,
            plan=plan,
            statut="actif",
            current_period_end=period_end,
        )
        db.add(sub)
    db.commit()


def _update_subscription(db: Session, sub_data: dict):
    stripe_sub_id = sub_data["id"]
    sub = db.query(models.Subscription).filter(
        models.Subscription.stripe_subscription_id == stripe_sub_id
    ).first()
    if not sub:
        return

    status_map = {
        "active": "actif",
        "canceled": "annule",
        "incomplete": "inactif",
        "past_due": "inactif",
        "unpaid": "inactif",
    }
    sub.statut = status_map.get(sub_data["status"], "inactif")
    if sub_data.get("current_period_end"):
        sub.current_period_end = datetime.utcfromtimestamp(sub_data["current_period_end"])
    db.commit()


@router.post("/annuler")
async def annuler_abonnement(request: Request, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    if not user or not user.subscription:
        return RedirectResponse("/dashboard", status_code=302)

    sub = user.subscription
    if sub.stripe_subscription_id:
        try:
            stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
            sub.statut = "annule"
            db.commit()
        except stripe.error.StripeError:
            pass

    return RedirectResponse("/dashboard?msg=abonnement_annule", status_code=302)
