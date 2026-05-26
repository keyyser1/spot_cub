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
        _activate_subscription(db, cs)

    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub_data = event["data"]["object"]
        _update_subscription(db, sub_data)

    return {"status": "ok"}


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
