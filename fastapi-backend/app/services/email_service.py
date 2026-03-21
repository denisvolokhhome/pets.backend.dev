"""Reusable email service for sending transactional emails via SMTP."""
import logging
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import aiosmtplib
import certifi

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Async email service using aiosmtplib.

    Usage:
        service = EmailService(settings)
        await service.send_email(to="user@example.com", subject="Hi", html="<p>Hello</p>")
    """

    def __init__(self, settings: Settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_email = settings.smtp_from_email
        self.from_name = settings.smtp_from_name
        self.use_tls = settings.smtp_tls

    @property
    def is_configured(self) -> bool:
        """Check if SMTP is configured (host and user are set)."""
        return bool(self.host and self.user)

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
    ) -> bool:
        """
        Send an email. Returns True on success, False on failure.

        Args:
            to: Recipient email address
            subject: Email subject line
            html: HTML body content
            text: Optional plain-text fallback
        """
        if not self.is_configured:
            logger.warning("SMTP not configured — email not sent to %s", to)
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to
        msg["Subject"] = subject

        if text:
            msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        try:
            tls_context = ssl.create_default_context(cafile=certifi.where())
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=self.use_tls,
                tls_context=tls_context,
            )
            logger.info("Email sent to %s — subject: %s", to, subject)
            return True
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", to, exc)
            return False

    # ── Convenience helpers (reusable across the app) ──────────────

    async def send_password_reset(
        self, to: str, token: str, frontend_url: str
    ) -> bool:
        """Send password-reset email with a link containing the token."""
        reset_url = f"{frontend_url}/reset-password?token={token}"
        html = _render_password_reset(reset_url)
        return await self.send_email(
            to=to,
            subject="Reset your Breedly password",
            html=html,
            text=f"Reset your password: {reset_url}",
        )

    async def send_welcome(self, to: str, name: str) -> bool:
        """Send a welcome email after registration."""
        html = _render_welcome(name)
        return await self.send_email(
            to=to,
            subject="Welcome to Breedly!",
            html=html,
            text=f"Welcome to Breedly, {name}!",
        )


# ── Simple HTML templates ──────────────────────────────────────────

def _base_wrapper(content: str) -> str:
    return f"""
    <div style="font-family: 'Poppins', Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 24px; color: #1f2937;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; width: 56px; height: 56px; line-height: 56px; border-radius: 50%;
                    background: linear-gradient(135deg, #ff6b6b, #4ecdc4); color: white; font-size: 28px; font-weight: 700;">
          B
        </div>
        <h2 style="margin: 12px 0 0; font-size: 22px; font-weight: 700; color: #1f2937;">Breedly</h2>
      </div>
      {content}
      <p style="margin-top: 40px; font-size: 12px; color: #9ca3af; text-align: center;">
        &copy; Breedly &mdash; Connecting breeders with loving families.
      </p>
    </div>
    """


def _render_password_reset(reset_url: str) -> str:
    return _base_wrapper(f"""
      <h3 style="font-size: 18px; font-weight: 600;">Reset your password</h3>
      <p style="font-size: 14px; line-height: 1.6; color: #4b5563;">
        We received a request to reset your password. Click the button below to choose a new one.
        If you didn't request this, you can safely ignore this email.
      </p>
      <div style="text-align: center; margin: 28px 0;">
        <a href="{reset_url}"
           style="display: inline-block; padding: 12px 32px; background: linear-gradient(135deg, #ff6b6b, #ff5252);
                  color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px;">
          Reset Password
        </a>
      </div>
      <p style="font-size: 12px; color: #9ca3af;">This link expires in 1 hour.</p>
    """)


def _render_welcome(name: str) -> str:
    return _base_wrapper(f"""
      <h3 style="font-size: 18px; font-weight: 600;">Welcome, {name}!</h3>
      <p style="font-size: 14px; line-height: 1.6; color: #4b5563;">
        Thanks for joining Breedly. You're all set to start managing your breeding program
        or find your perfect companion.
      </p>
    """)
