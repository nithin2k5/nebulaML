import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import EmailStr
import os
from dotenv import load_dotenv
from app.core.logging import logger

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@yologenerator.com")

def send_otp_email(to_email: EmailStr, otp: str):
    """
    Sends an OTP email to the user.
    If SMTP credentials are not configured, it simulates sending by logging the OTP.
    """
    subject = "Your Login Verification Code"
    body = f"""
    <html>
        <body>
            <h2>Login Verification</h2>
            <p>Your verification code is: <strong>{otp}</strong></p>
            <p>This code will expire in 10 minutes.</p>
            <p>If you did not request this, please ignore this email.</p>
        </body>
    </html>
    """

    # If no SMTP_HOST is configured, just print to console for development/testing
    if not SMTP_HOST:
        logger.info(f"==== MOCK EMAIL SENT ====")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"OTP Code: {otp}")
        logger.info(f"=========================")
        return True

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USERNAME and SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"OTP email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {str(e)}")
        # Fallback to logger so the user isn't stuck if credentials fail during testing
        logger.info(f"Mock Fallback OTP: {otp}")
        return False
