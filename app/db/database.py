from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv() # To wymusza wczytanie pliku .env

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Zabezpieczenie: jeśli nie ma adresu w .env, użyj lokalnej bazy (żeby projekt nie padł)
if not SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = "sqlite:///./bike_app.db"
elif SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)


Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)  # NOWOŚĆ
    password = Column(String, nullable=False)
    reset_code = Column(String, nullable=True)          # NOWOŚĆ (na potrzeby resetu)
    routes = relationship("SavedRoute", back_populates="owner")

class SavedRoute(Base):
    __tablename__ = 'routes'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String, nullable=False)
    geojson_data = Column(Text, nullable=False)
    visibility = Column(String, default='private') # 'private' lub 'public'
    owner = relationship("User", back_populates="routes")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()