import bcrypt
import re
import random
import string
from app.db.database import User, SessionLocal

#hashuje hasło
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

#sprawdza czy wpisane hasło jest poprawne
def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

#definicja funkcji logowania
def login_user(login_id, password):
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            (User.username == login_id) | (User.email == login_id)
        ).first()

        if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return user
        return None
    except Exception as e:
        print(f"Błąd logowania: {e}")
        return None
    finally:
        db.close()

EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

#definicja funkcji rejestracji
def register_user(username, email, password):
    # 1. Walidacja formatu e-mail
    if not re.match(EMAIL_REGEX, email):
        return "invalid_email"

    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing_user:
            return "exists"

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
        db.close()

#definicja funkcji do obsługi sytuacji z resetem hasła
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