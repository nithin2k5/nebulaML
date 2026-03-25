import html
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

THEME_BG = "#09090b"
THEME_CARD = "#101013"
THEME_BORDER = "#27272a"
THEME_TEXT = "#fafafa"
THEME_MUTED = "#a1a1aa"
THEME_ACCENT = "#6b4eff"
THEME_ACCENT_SOFT = "rgba(107, 78, 255, 0.12)"
THEME_FONT = "-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _nebula_email_shell(inner_html: str, page_title: str = "NebulaML") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <title>{html.escape(page_title)}</title>
</head>
<body style="margin:0;padding:0;background-color:{THEME_BG};font-family:{THEME_FONT};color:{THEME_TEXT};line-height:1.6;-webkit-font-smoothing:antialiased;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{THEME_BG};padding:40px 16px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background-color:{THEME_CARD};border:1px solid {THEME_BORDER};border-radius:16px;overflow:hidden;box-shadow:0 25px 50px -12px rgba(0,0,0,0.45);">
                    <tr>
                        <td style="padding:36px 40px 28px 40px;border-bottom:1px solid {THEME_BORDER};">
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td>
                                        <span style="font-weight:800;font-size:22px;letter-spacing:-0.04em;color:{THEME_TEXT};">Nebula<span style="color:{THEME_ACCENT};">ML</span></span>
                                    </td>
                                    <td align="right" style="font-size:11px;color:{THEME_MUTED};text-transform:uppercase;letter-spacing:0.12em;">Vision AI</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:32px 40px 40px 40px;">
                            {inner_html}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px 28px 40px;border-top:1px solid {THEME_BORDER};background-color:rgba(0,0,0,0.25);">
                            <p style="margin:0;font-size:12px;color:{THEME_MUTED};text-align:center;line-height:1.5;">
                                &copy; NebulaML &mdash; Dataset versioning, training &amp; deployment in one flow.<br/>
                                <span style="opacity:0.85;">You received this because of an action on your account.</span>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def send_otp_email(to_email: EmailStr, otp: str):
    """
    Sends an OTP email to the user.
    If SMTP credentials are not configured, it simulates sending by logging the OTP.
    """
    subject = "Your NebulaML verification code"
    safe_otp = html.escape(otp.strip())
    inner = f"""
            <p style="margin:0 0 8px 0;font-size:13px;font-weight:600;color:{THEME_ACCENT};text-transform:uppercase;letter-spacing:0.08em;">Security</p>
            <h1 style="margin:0 0 16px 0;font-size:22px;font-weight:600;color:{THEME_TEXT};letter-spacing:-0.02em;">Your verification code</h1>
            <p style="margin:0 0 24px 0;font-size:15px;color:{THEME_MUTED};">
                Use this one-time code to continue signing in. It expires in <strong style="color:{THEME_TEXT};">10 minutes</strong>.
            </p>
            <div style="text-align:center;margin:28px 0 28px 0;">
                <div style="display:inline-block;padding:20px 36px;background:linear-gradient(145deg, {THEME_ACCENT_SOFT} 0%, rgba(24,24,27,0.9) 100%);border:1px solid {THEME_BORDER};border-radius:12px;">
                    <span style="font-size:32px;font-weight:700;letter-spacing:0.35em;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:{THEME_TEXT};">{safe_otp}</span>
                </div>
            </div>
            <p style="margin:0;font-size:13px;color:{THEME_MUTED};text-align:center;">
                If you didn&apos;t request this email, you can safely ignore it. Your account stays protected.
            </p>
    """
    body = _nebula_email_shell(inner, "Verify your email — NebulaML")

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
        logger.info(f"Mock Fallback OTP: {otp}")
        return False


def send_project_invite_email(to_email: EmailStr, inviter_name: str, project_name: str, role: str, invite_link: str):
    """
    Sends an invitation email to collaborate on a NebulaML project.
    """
    subject = f"You've been invited — {project_name} · NebulaML"
    inv = html.escape(inviter_name or "A teammate")
    proj = html.escape(project_name or "a project")
    role_safe = html.escape((role or "member").title())
    link_href = html.escape(invite_link, quote=True)
    link_display = html.escape(invite_link)

    inner = f"""
            <p style="margin:0 0 8px 0;font-size:13px;font-weight:600;color:{THEME_ACCENT};text-transform:uppercase;letter-spacing:0.08em;">Collaboration</p>
            <h1 style="margin:0 0 16px 0;font-size:22px;font-weight:600;color:{THEME_TEXT};letter-spacing:-0.02em;">You&apos;re invited to a project</h1>
            <p style="margin:0 0 24px 0;font-size:15px;color:{THEME_MUTED};">
                <strong style="color:{THEME_TEXT};">{inv}</strong> invited you to work on <strong style="color:{THEME_TEXT};">{proj}</strong> on NebulaML.
            </p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;background-color:{THEME_BG};border:1px solid {THEME_BORDER};border-radius:10px;">
                <tr>
                    <td style="padding:16px 18px;border-left:4px solid {THEME_ACCENT};">
                        <p style="margin:0;font-size:12px;color:{THEME_MUTED};text-transform:uppercase;letter-spacing:0.06em;">Role</p>
                        <p style="margin:6px 0 0 0;font-size:16px;font-weight:600;color:{THEME_TEXT};">{role_safe}</p>
                    </td>
                </tr>
            </table>
            <div style="text-align:center;margin:8px 0 24px 0;">
                <a href="{link_href}" style="display:inline-block;background:linear-gradient(180deg, {THEME_ACCENT} 0%, #5b21f5 100%);color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:600;font-size:15px;box-shadow:0 4px 14px rgba(107,78,255,0.35);">Accept invitation</a>
            </div>
            <p style="margin:0;font-size:12px;color:{THEME_MUTED};text-align:center;line-height:1.5;">
                No account yet? You&apos;ll be guided to sign up first.<br/>
                This link is personal &mdash; expires in 7 days.
            </p>
            <p style="margin:20px 0 0 0;font-size:11px;color:{THEME_MUTED};word-break:break-all;text-align:center;opacity:0.85;">
                Or paste: <span style="color:{THEME_ACCENT};">{link_display}</span>
            </p>
    """
    body = _nebula_email_shell(inner, f"Invite — {project_name}")

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
