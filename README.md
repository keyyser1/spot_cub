# 🧘 Studio Pilates — Application Web

Site vitrine + réservations + abonnements Stripe, déployé sur Railway.

## Stack
- **Backend** : FastAPI (Python)
- **Base de données** : PostgreSQL (Railway)
- **Paiements** : Stripe (abonnements récurrents)
- **Templates** : Jinja2 + Tailwind CSS

## Fonctionnalités

### Clients
- Inscription / connexion
- Voir le planning hebdomadaire
- Réserver des cours (abonnement requis)
- Annuler ses réservations
- Gérer son abonnement (résiliation)

### Admin
- Créer/désactiver des cours récurrents
- Voir le planning avec inscrits par séance
- Annuler une séance
- Liste des clients et statuts d'abonnement
- KPIs : clients, abonnés actifs, cours actifs

---

## Déploiement sur Railway

### 1. Créer le projet Railway

```bash
# Installer Railway CLI
npm install -g @railway/cli

# Login
railway login

# Nouveau projet
railway init
```

### 2. Ajouter PostgreSQL

Dans le dashboard Railway : **New > Database > Add PostgreSQL**
Railway injecte `DATABASE_URL` automatiquement.

### 3. Variables d'environnement

Dans Railway → Variables, ajoutez toutes les variables de `.env.example`.

```
SECRET_KEY=<générez avec: python -c "import secrets; print(secrets.token_hex(32))">
BASE_URL=https://votre-app.up.railway.app
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_MENSUEL=price_...
STRIPE_PRICE_TRIMESTRIEL=price_...
STRIPE_PRICE_ANNUEL=price_...
SETUP_SECRET=<votre-secret>
ADMIN_EMAIL=admin@studio.fr
ADMIN_PASSWORD=<mot-de-passe-fort>
```

### 4. Déployer

```bash
railway up
```

### 5. Créer le compte admin (une seule fois)

Visitez : `https://votre-app.up.railway.app/setup-admin?secret=VOTRE_SETUP_SECRET`

### 6. Configurer Stripe

**Créer les produits Stripe :**

1. Aller sur [dashboard.stripe.com](https://dashboard.stripe.com)
2. Produits → Créer un produit "Abonnement Studio Pilates"
3. Ajouter 3 prix récurrents :
   - Mensuel : 59€/mois → copier le Price ID → `STRIPE_PRICE_MENSUEL`
   - Trimestriel : 149€ tous les 3 mois → `STRIPE_PRICE_TRIMESTRIEL`  
   - Annuel : 499€/an → `STRIPE_PRICE_ANNUEL`

**Configurer le webhook Stripe :**

1. Stripe Dashboard → Developers → Webhooks → Add endpoint
2. URL : `https://votre-app.up.railway.app/abonnement/webhook`
3. Événements à écouter :
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copier le **Signing secret** → `STRIPE_WEBHOOK_SECRET`

---

## Structure du projet

```
studio-pilates/
├── main.py                  # App FastAPI, routes principales
├── database.py              # Connexion DB
├── models.py                # Modèles SQLAlchemy
├── auth_utils.py            # Hachage passwords, sessions
├── session_utils.py         # Génération auto des séances
├── routers/
│   ├── auth_router.py       # Login, register, logout
│   ├── planning_router.py   # Planning + réservations
│   ├── subscription_router.py  # Stripe checkout + webhook
│   └── admin_router.py      # Dashboard admin
├── templates/
│   ├── base.html            # Layout commun
│   ├── index.html           # Page d'accueil
│   ├── planning.html        # Planning public
│   ├── tarifs.html          # Abonnements
│   ├── dashboard.html       # Espace client
│   ├── auth/login.html
│   ├── auth/register.html
│   └── admin/               # Interface admin
├── static/style.css
├── requirements.txt
└── railway.toml
```

## Personnalisation

- **Nom du studio** : chercher "Studio Pilates" dans les templates
- **Adresse / contact** : footer dans `base.html`
- **Prix** : dans `tarifs.html` (affichage) + Stripe Dashboard (facturation)
- **Couleurs** : palette `sage` dans `base.html` (config Tailwind)
