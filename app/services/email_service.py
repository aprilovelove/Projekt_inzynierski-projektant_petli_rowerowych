import smtplib #Importuje wbudowaną w Pythona bibliotekę klienta protokołu SMTP. Odpowiada za fizyczne nawiązanie połączenia, zalogowanie się i przepchnięcie wiadomości przez serwer pocztowy
import os
import streamlit as st
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase            #MIME - komponenty do wysłania maila ; tekstu i załączników
from email import encoders

#definicja funkcji do wysyłki uniwersalnego maila
def send_custom_email(recipient_email, subject, body, attachment_data=None, attachment_name=None):
    #Bezpieczna próba odczytania konfiguracji konta e-mail z chmury Streamlit Cloud.
    sender_email = None
    password = None

    try:
        if "email" in st.secrets:
            sender_email = st.secrets["email"]["user"]
            password = st.secrets["email"]["pass"]
    except Exception:
        pass  # Jeśli nie ma sekretów, szukamy dalej

    #próba pobrania z .env (dla uruchomień testowych z terminala)
    if not sender_email or not password:
        from dotenv import load_dotenv
        load_dotenv()
        sender_email = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASS")

    #walidacja - bezpiecznik - jak nie ma maila to błąd
    if not sender_email or not password:
        st.error("Błąd: Nie skonfigurowano danych serwera e-mail (Secrets lub .env).")
        return False

    # Budowa wiadomości
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    if attachment_data: #obsługa załącznika gpx
        data_to_attach = attachment_data
        if isinstance(data_to_attach, str):
            data_to_attach = data_to_attach.encode('utf-8')

        part = MIMEBase('application', 'octet-stream') #tworzymy obiekt załącznika binarnego bo tylko taki obsługuje sieć internetowa
        part.set_payload(data_to_attach)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={attachment_name}")
        msg.attach(part)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:   #inicjalizacja połączenia z serwerem SMTP firmy Google
            server.starttls()                           #konstrukcja with ...as zapewnia zamknięcie połączenia po zakończeniu wysyłki
            server.login(sender_email, password)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Błąd SMTP: {e}")  #bezpiecznik
        return False