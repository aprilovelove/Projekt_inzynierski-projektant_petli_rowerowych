from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import streamlit as st
from datetime import datetime

#inicjalizacja zmiennej na adres URL bazy danych
SQLALCHEMY_DATABASE_URL = None

#sprawdzamy czy aplikacja działą w chmurze Streamlit i czy w zakładce Secrets jest zdefiniowana sekcja database, except daje pass bo testowo aplikacja bywa uruchamiana lokalnie
try:
    if "database" in st.secrets:
        SQLALCHEMY_DATABASE_URL = st.secrets["database"]["url"]
except Exception:
    pass

# Jeśli poprzedni krok nie znalazł adresu (czyli aplikacja jest uruchamiana lokalnie), używamy load_dotenv() aby z pliku .env wyciągnąć adres adres bazy NeonDB
if not SQLALCHEMY_DATABASE_URL:
    from dotenv import load_dotenv

    load_dotenv()
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# jeżeli żadne z powyższych połączeń nie zadziałało to rzucamy błąd
if not SQLALCHEMY_DATABASE_URL:
    raise ConnectionError(
        "Nie znaleziono adresu bazy danych! "
        "Upewnij się, że masz skonfigurowane Secrets w Streamlit Cloud "
        "lub plik .env lokalnie z kluczem DATABASE_URL."
    )

#ta linijka podmienia tekst z bo w nowych wersjach SQLAlchemy musi być postgresql://
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# tworzy obiekt engine (silnik połączenia z bazą)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  #przed każdym zapyaniem sprawdza czy połączenie z chmurą jest aktywne
    connect_args={"sslmode": "require"} #wymusza szyfrowanie ruchu SSL ( to wymóg NeonDB)
)
Base = declarative_base() # tworzy instancję klasy bazowej ORM - fundament do budowy struktur tabel


# --- TABELE ---

class User(Base):
    __tablename__ = 'users'     #nazwa tabeli + kolumny
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    reset_code = Column(String, nullable=True)
    routes = relationship("SavedRoute", back_populates="owner")  # relacja


class SavedRoute(Base):
    __tablename__ = 'routes'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String, nullable=False)
    geojson_data = Column(Text, nullable=False)
    visibility = Column(String, default='private')

    owner = relationship("User", back_populates="routes")
    # relacje ; ta poniżej gwarantuje, że po usunięciu trasy z bazy usuwane są także dotyczące jej opinie i oceny
    reviews = relationship("RouteReview", back_populates="route", cascade="all, delete-orphan")


# tabela z ocenami tras
class RouteReview(Base):
    __tablename__ = 'route_reviews'
    id = Column(Integer, primary_key=True)
    route_id = Column(Integer, ForeignKey('routes.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=True)  # Ocena 1-5
    comment = Column(Text, nullable=True)  # Treść komentarza
    created_at = Column(DateTime, default=datetime.utcnow)  # Automatyczna data wpisu

    # Relacje
    route = relationship("SavedRoute", back_populates="reviews")
    user = relationship("User")


# --- KONFIGURACJA SESJI  związanej z naszym silnikiem bazy danych
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# to w sumie chyba po nic xd, można użyć w main żeby było mniej kodu, ale nie chce mi sie tego ruszać
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()