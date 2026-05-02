import smtplib
import os
import streamlit as st
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def send_custom_email(recipient_email, subject, body, attachment_data=None, attachment_name=None):
    # Dynamiczne pobieranie danych logowania
    if "email" in st.secrets:
        sender_email = st.secrets["email"]["user"]
        password = st.secrets["email"]["pass"]
    else:
        sender_email = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASS")

    if not sender_email or not password:
        print("Błąd: Brak danych logowania do serwera SMTP.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    if attachment_data:
        # Konwersja na bytes jeśli current_gpx to string
        data_to_attach = attachment_data
        if isinstance(data_to_attach, str):
            data_to_attach = data_to_attach.encode('utf-8')

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(data_to_attach)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={attachment_name}")
        msg.attach(part)

    try:
        # Używamy kontekstu 'with', żeby serwer zawsze się poprawnie zamykał
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Błąd wysyłki e-mail: {e}")
        return False