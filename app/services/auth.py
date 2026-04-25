import bcrypt
import re
import random
import string
from app.db.database import User, SessionLocal

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def register_user(username, password):
    db = SessionLocal()
    if db.query(User).filter_by(username=username).first():
        db.close()
        return False
    new_user = User(username=username, password=hash_password(password))
    db.add(new_user)
    db.commit()
    db.close()
    return True


def login_user(login_id, password):
    db = SessionLocal()
    try:
        # ZMIANA: Szukamy dopasowania w kolumnie username LUB email
        user = db.query(User).filter(
            (User.username == login_id) | (User.email == login_id)
        ).first()

        # Jeśli użytkownik istnieje, sprawdzamy hasło
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return user
        return None
    except Exception as e:
        print(f"Błąd logowania: {e}")
        return None
    finally:
        db.close()

EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'


def register_user(username, email, password):
    # 1. Walidacja formatu e-mail
    if not re.match(EMAIL_REGEX, email):
        return "invalid_email"

    db = SessionLocal()
    try:
        # 2. Sprawdzenie, czy nazwa użytkownika lub e-mail już istnieją
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing_user:
            return "exists"

        # 3. Tworzenie nowego użytkownika (z uwzględnieniem pola email!)
        new_user = User(
            username=username,
            email=email,
            password=hash_password(password)
        )

        db.add(new_user)
        db.commit()  # Zapisanie zmian w bazie Neon
        return "success"

    except Exception as e:
        print(f"Błąd podczas rejestracji: {e}")
        db.rollback()  # W razie błędu wycofujemy zmiany
        return "error"
    finally:
        db.close()  # Zawsze zamykamy sesję

def initiate_password_reset(email):
    db = SessionLocal()
    user = db.query(User).filter_by(email=email).first()
    if user:
        code = ''.join(random.choices(string.digits, k=6))
        user.reset_code = code
        db.commit()
        db.close()
        return code
    db.close()
    return None