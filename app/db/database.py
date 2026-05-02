from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import streamlit as st

# 1. PRÓBA POBRANIA URL (Najpierw Secrets, potem .env)
SQLALCHEMY_DATABASE_URL = None

# Sprawdzamy w Streamlit Secrets (dla chmury)
try:
    if "database" in st.secrets:
        SQLALCHEMY_DATABASE_URL = st.secrets["database"]["url"]
except Exception:
    pass

# Jeśli nie znaleziono w Secrets, szukamy w os.environ (dla PyCharm / .env)
if not SQLALCHEMY_DATABASE_URL:
    # Upewnij się, że w pliku .env masz linię: DATABASE_URL=postgresql://...
    from dotenv import load_dotenv
    load_dotenv()
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# 2. KONTROLA BŁĘDÓW I FIX FORMATU
if not SQLALCHEMY_DATABASE_URL:
    raise ConnectionError(
        "Nie znaleziono adresu bazy danych! "
        "Upewnij się, że masz skonfigurowane Secrets w Streamlit Cloud "
        "lub plik .env lokalnie z kluczem DATABASE_URL."
    )

# Konieczna zamiana postgres:// na postgresql:// dla SQLAlchemy
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. POŁĄCZENIE
# Dodajemy pool_pre_ping=True oraz connect_args dla stabilności SSL
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}
)
Base = declarative_base()

# --- MODELE (bez zmian) ---
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    reset_code = Column(String, nullable=True)
    routes = relationship("SavedRoute", back_populates="owner")

class SavedRoute(Base):
    __tablename__ = 'routes'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String, nullable=False)
    geojson_data = Column(Text, nullable=False)
    visibility = Column(String, default='private')
    owner = relationship("User", back_populates="routes")

# --- KONFIGURACJA SESJI ---
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()