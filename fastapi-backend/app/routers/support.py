"""Support request routes."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.user import User
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)
settings = Settings()

router = APIRouter(prefix="/api/support", tags=["support"])

CATEGORIES = [
    "account_conversion",
    "account_issue",
    "billing",
    "bug_report",
    "feature_request",
    "verification",
    "other",
]

CATEGORY_LABELS = {
    "account_conversion": "Account Conversion",
    "account_issue": "Account Issue",
    "billing": "Billing",
    "bug_report": "Bug Report",
    "feature_request": "Feature Request",
    "verification": "Verification",
    "other": "Other",
}


class SupportRequest(BaseModel):
    category: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)


class SupportResponse(BaseModel):
    request_number: str
    message: str


def _generate_request_number() -> str:
    """Generate a trackable request number like BR-20260324-A1B2C3."""
    now = datetime.now(timezone.utc)
    short_id = uuid.uuid4().hex[:6].upper()
    return f"BR-{now.strftime('%Y%m%d')}-{short_id}"


def _render_support_to_admin(
    request_number: str,
    category: str,
    subject: str,
    message: str,
    user_email: str,
    user_name: str | None,
    user_id: str,
    is_breeder: bool,
) -> str:
    account_type = "Breeder" if is_breeder else "Pet Seeker"
    return f"""
    <div style="font-family: 'Poppins', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1f2937;">
      <div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
        <strong style="font-size: 16px;">Support Request {request_number}</strong>
      </div>
      <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 8px 12px; font-weight: 600; color: #6b7280; width: 140px;">Request #</td><td style="padding: 8px 12px;">{request_number}</td></tr>
        <tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Category</td><td style="padding: 8px 12px;">{CATEGORY_LABELS.get(category, category)}</td></tr>
        <tr><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Subject</td><td style="padding: 8px 12px;">{subject}</td></tr>
        <tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">From</td><td style="padding: 8px 12px;">{user_name or 'N/A'} &lt;{user_email}&gt;</td></tr>
        <tr><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Account Type</td><td style="padding: 8px 12px;">{account_type}</td></tr>
        <tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">User ID</td><td style="padding: 8px 12px; font-size: 12px;">{user_id}</td></tr>
      </table>
      <div style="margin-top: 20px; padding: 16px; background: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
        <strong style="display: block; margin-bottom: 8px; color: #374151;">Message:</strong>
        <p style="margin: 0; white-space: pre-wrap; line-height: 1.6; color: #4b5563;">{message}</p>
      </div>
    </div>
    """


def _render_confirmation_to_user(
    request_number: str,
    category: str,
    subject: str,
    user_name: str | None,
) -> str:
    name = user_name or "there"
    return f"""
    <div style="font-family: 'Poppins', Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 24px; color: #1f2937;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; width: 56px; height: 56px; line-height: 56px; border-radius: 50%;
                    background: linear-gradient(135deg, #ff6b6b, #4ecdc4); color: white; font-size: 28px; font-weight: 700;">
          B
        </div>
        <h2 style="margin: 12px 0 0; font-size: 22px; font-weight: 700; color: #1f2937;">Breedly</h2>
      </div>
      <h3 style="font-size: 18px; font-weight: 600;">Hi {name}, we got your request!</h3>
      <p style="font-size: 14px; line-height: 1.6; color: #4b5563;">
        Your support request has been received. Here are the details for your records:
      </p>
      <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <p style="margin: 0 0 8px; font-size: 14px;"><strong>Request Number:</strong> {request_number}</p>
        <p style="margin: 0 0 8px; font-size: 14px;"><strong>Category:</strong> {CATEGORY_LABELS.get(category, category)}</p>
        <p style="margin: 0; font-size: 14px;"><strong>Subject:</strong> {subject}</p>
      </div>
      <p style="font-size: 14px; line-height: 1.6; color: #4b5563;">
        Please keep your request number handy if you need to follow up. You can reply to this email
        or reference <strong>{request_number}</strong> in any future communication.
      </p>
      <p style="margin-top: 40px; font-size: 12px; color: #9ca3af; text-align: center;">
        &copy; Breedly &mdash; Connecting breeders with loving families.
      </p>
    </div>
    """


@router.get("/categories")
async def get_categories():
    """Return available support request categories."""
    return [{"value": k, "label": v} for k, v in CATEGORY_LABELS.items()]


@router.post("/request", response_model=SupportResponse)
async def submit_support_request(
    data: SupportRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Submit a support request. Sends email to support and confirmation to user."""
    if data.category not in CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}",
        )

    request_number = _generate_request_number()
    email_service = EmailService(settings)

    # Send to support
    admin_html = _render_support_to_admin(
        request_number=request_number,
        category=data.category,
        subject=data.subject,
        message=data.message,
        user_email=user.email,
        user_name=user.name,
        user_id=str(user.id),
        is_breeder=user.is_breeder,
    )
    admin_sent = await email_service.send_email(
        to="support@breedly.us",
        subject=f"[{request_number}] {CATEGORY_LABELS.get(data.category, data.category)}: {data.subject}",
        html=admin_html,
        text=f"Request {request_number}\nFrom: {user.email}\nCategory: {data.category}\nSubject: {data.subject}\n\n{data.message}",
    )

    # Send confirmation to user
    user_html = _render_confirmation_to_user(
        request_number=request_number,
        category=data.category,
        subject=data.subject,
        user_name=user.name,
    )
    user_sent = await email_service.send_email(
        to=user.email,
        subject=f"Breedly Support — Request {request_number} received",
        html=user_html,
        text=f"Your support request {request_number} has been received. Category: {CATEGORY_LABELS.get(data.category, data.category)}, Subject: {data.subject}",
    )

    if not admin_sent:
        logger.error(f"Failed to send support email for {request_number}")

    if not user_sent:
        logger.warning(f"Failed to send confirmation email to {user.email} for {request_number}")

    logger.info(f"Support request {request_number} submitted by user {user.id} ({user.email})")

    return SupportResponse(
        request_number=request_number,
        message="Your support request has been submitted. Check your email for confirmation.",
    )
