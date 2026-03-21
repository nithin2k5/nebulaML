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
_pwd = os.getenv("SMTP_PASSWORD", "")
SMTP_PASSWORD = _pwd.replace(" ", "") if _pwd else ""
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_FROM", SMTP_USERNAME or "noreply@yologenerator.com"))

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

def send_project_invite_email(to_email: EmailStr, inviter_name: str, project_name: str, role: str, invite_link: str):
    """
    Sends an invitation email to collaborate on a NebulaML project.
    """
    subject = f"You've been invited to collaborate on {project_name}"
    
    # Matching the NebulaML dark theme natively in the email HTML
    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #000000; color: #ffffff; padding: 40px 20px; line-height: 1.6; margin: 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-w-md; margin: 0 auto; background-color: #09090b; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; border-collapse: collapse;">
            <tr>
                <td style="padding: 40px; text-align: left;">
                    <div style="margin-bottom: 24px;">
                        <span style="font-weight: 800; font-size: 24px; color: #ffffff;">Nebula<span style="color: #6366f1;">ML</span></span>
                    </div>
                    <h2 style="font-size: 20px; font-weight: 600; color: #ffffff; margin-top: 0; margin-bottom: 16px;">
                        Collaboration Invite
                    </h2>
                    <p style="color: #a1a1aa; font-size: 16px; margin-bottom: 24px;">
                        <strong>{inviter_name}</strong> has invited you to collaborate on the dataset/project <strong>{project_name}</strong>.
                    </p>
                    <div style="background-color: rgba(99,102,241,0.1); border-left: 4px solid #6366f1; padding: 16px; margin-bottom: 32px; border-radius: 4px;">
                        <p style="color: #e0e7ff; margin: 0; font-size: 14px;"><strong>Role assigned:</strong> {role.title()}</p>
                    </div>
                    <p style="text-align: center; margin-bottom: 32px;">
                        <a href="{invite_link}" style="background-color: #6366f1; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; display: inline-block; font-size: 16px;">
                            Accept Invitation
                        </a>
                    </p>
                    <p style="color: #a1a1aa; font-size: 13px; text-align: center; margin-bottom: 0;">
                        If you don't have a NebulaML account, you will be prompted to create one.<br/>
                        Link expires in 7 days.
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    if not SMTP_HOST:
        logger.info(f"==== MOCK INVITE EMAIL SENT ====")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Link: {invite_link}")
        logger.info(f"================================")
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
            
        logger.info(f"Invite email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send invite email: {str(e)}")
        logger.info(f"Mock Fallback Link: {invite_link}")
        return False
