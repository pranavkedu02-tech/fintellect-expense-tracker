"""
Sends emails via Gmail's SMTP server using Python's built-in smtplib
and email.mime, with TLS encryption and Gmail App Password auth.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587  # TLS


def send_email(to_email, subject, html_body):
    """
    Sends an HTML email to a single recipient. Returns True on success,
    False on failure (never raises, so a failed email never crashes
    the view that triggered it).
    """
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        print("Warning: email credentials not configured in .env")
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"Fintellect <{settings.EMAIL_HOST_USER}>"
    message["To"] = to_email

    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.sendmail(settings.EMAIL_HOST_USER, to_email, message.as_string())
        return True
    except Exception as e:
        print(f"Warning: failed to send email to {to_email}: {e}")
        return False