import smtplib
import os
import streamlit as st
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def send_custom_email(recipient_email, subject, body, attachment_data=None, attachment_name=None):
    # 1. PRÓBA POBRANIA Z SECRETS (Dla Streamlit Cloud)
    sender_email = None
    password = None

    try:
        if "email" in st.secrets:
            sender_email = st.secrets["email"]["user"]
            password = st.secrets["email"]["pass"]
    except Exception:
        pass  # Jeśli nie ma sekretów, szukamy dalej

    # 2. PRÓBA POBRANIA Z ENV (Dla PyCharm)
    if not sender_email or not password:
        from dotenv import load_dotenv
        load_dotenv()
        sender_email = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASS")

    # 3. WALIDACJA
    if not sender_email or not password:
        st.error("Błąd: Nie skonfigurowano danych serwera e-mail (Secrets lub .env).")
        return False

    # Budowa wiadomości
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    if attachment_data:
        data_to_attach = attachment_data
        if isinstance(data_to_attach, str):
            data_to_attach = data_to_attach.encode('utf-8')

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(data_to_attach)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={attachment_name}")
        msg.attach(part)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Błąd SMTP: {e}")
        return False