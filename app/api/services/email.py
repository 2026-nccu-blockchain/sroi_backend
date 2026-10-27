import logging
from html import escape
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import urlparse

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from app.core.config import get_settings


logger = logging.getLogger(__name__)
EMAIL_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "email"


def _create_brevo_client() -> sib_api_v3_sdk.TransactionalEmailsApi:
    settings = get_settings()

    if not settings.brevo_api_key:
        raise RuntimeError("BREVO_API_KEY 尚未設定")

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = settings.brevo_api_key

    api_client = sib_api_v3_sdk.ApiClient(configuration)

    return sib_api_v3_sdk.TransactionalEmailsApi(api_client)


def send_template_email(
    *,
    recipient_email: str,
    recipient_name: str,
    template_id: int,
    params: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()

    if template_id <= 0:
        raise RuntimeError("Brevo template ID 尚未設定")

    api_instance = _create_brevo_client()

    email = sib_api_v3_sdk.SendSmtpEmail(
        sender={
            "name": settings.brevo_sender_name,
            "email": settings.brevo_sender_email,
        },
        to=[
            {
                "name": recipient_name,
                "email": recipient_email,
            }
        ],
        template_id=template_id,
        params=params or {},
        tags=["sroi-system"],
    )

    try:
        response = api_instance.send_transac_email(email)
    except ApiException as exc:
        logger.exception(
            "Brevo 寄信失敗：status=%s body=%s",
            getattr(exc, "status", None),
            getattr(exc, "body", None),
        )
        raise RuntimeError("自動信件寄送失敗") from exc

    return response.message_id


def send_html_email(
    *,
    recipient_email: str,
    recipient_name: str,
    subject: str,
    html_content: str,
) -> str:
    settings = get_settings()
    api_instance = _create_brevo_client()

    email = sib_api_v3_sdk.SendSmtpEmail(
        sender={
            "name": settings.brevo_sender_name,
            "email": settings.brevo_sender_email,
        },
        to=[
            {
                "name": recipient_name,
                "email": recipient_email,
            }
        ],
        subject=subject,
        html_content=html_content,
        tags=["sroi-system"],
    )

    try:
        response = api_instance.send_transac_email(email)
    except ApiException as exc:
        logger.exception(
            "Brevo 寄信失敗：status=%s body=%s",
            getattr(exc, "status", None),
            getattr(exc, "body", None),
        )
        raise RuntimeError("測試信件寄送失敗") from exc

    return response.message_id


def render_student_verification_email(
    *,
    recipient_name: str,
    verification_url: str,
) -> str:
    parsed_url = urlparse(verification_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("verification_url 必須是完整的 http 或 https 網址")

    template_path = EMAIL_TEMPLATE_DIR / "nccu_student_verification.html"
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.substitute(
        recipient_name=escape(recipient_name),
        verification_url=escape(verification_url, quote=True),
    )


def send_student_verification_email(
    *,
    recipient_email: str,
    recipient_name: str,
    verification_url: str,
) -> str:
    """寄送政大學生身分認證信；是否寄送由呼叫端決定。"""
    html_content = render_student_verification_email(
        recipient_name=recipient_name,
        verification_url=verification_url,
    )
    return send_html_email(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        subject="請完成政大學生身分認證",
        html_content=html_content,
    )
