from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    prenom = Column(String, nullable=False)
    nom = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="client")  # client | admin
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)

    @property
    def full_name(self):
        return f"{self.prenom} {self.nom}"

    @property
    def has_active_subscription(self):
        if not self.subscription:
            return False
        if self.subscription.statut != "active":
            return False
        if self.subscription.current_period_end and self.subscription.current_period_end < datetime.utcnow():
            return False
        return True


class Course(Base):
    """Cours récurrent (ex: Pilates Mat, chaque Lundi 09h00)"""
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    titre = Column(String, nullable=False)
    description = Column(Text, default="")
    niveau = Column(String, default="Tous niveaux")  # Débutant, Intermédiaire, Avancé, Tous niveaux
    jour_semaine = Column(Integer, nullable=False)  # 0=Lundi … 6=Dimanche
    heure = Column(String, nullable=False)  # "09:00"
    duree_minutes = Column(Integer, default=60)
    capacite_max = Column(Integer, default=10)
    actif = Column(Boolean, default=True)

    sessions = relationship("ClassSession", back_populates="course", cascade="all, delete-orphan")

    JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    @property
    def jour_nom(self):
        return self.JOURS[self.jour_semaine]


class ClassSession(Base):
    """Instance concrète d'un cours (ex: Lundi 15 Jan à 09h00)"""
    __tablename__ = "class_sessions"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    date_heure = Column(DateTime, nullable=False)
    places_restantes = Column(Integer, nullable=False)
    annulee = Column(Boolean, default=False)

    course = relationship("Course", back_populates="sessions")
    bookings = relationship("Booking", back_populates="session", cascade="all, delete-orphan")

    @property
    def nb_inscrits(self):
        return len([b for b in self.bookings if b.statut == "confirme"])


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    statut = Column(String, default="confirme")  # confirme | annule | liste_attente
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    session = relationship("ClassSession", back_populates="bookings")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    stripe_subscription_id = Column(String, nullable=True)
    plan = Column(String, nullable=True)  # mensuel | trimestriel | annuel
    statut = Column(String, default="inactif")  # actif | inactif | annule
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscription")

    PLANS = {
        "mensuel": {"nom": "Mensuel", "prix": 5900, "interval": "month", "interval_count": 1},
        "trimestriel": {"nom": "Trimestriel", "prix": 14900, "interval": "month", "interval_count": 3},
        "annuel": {"nom": "Annuel", "prix": 49900, "interval": "year", "interval_count": 1},
    }
