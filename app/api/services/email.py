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


def send_verification_code_email(*, recipient_email: str, code: str, expire_minutes: int) -> str:
    """寄送註冊驗證碼；信中只有驗證碼，沒有任何連結"""
    template = Template((EMAIL_TEMPLATE_DIR / "verification_code.html").read_text(encoding="utf-8"))
    html_content = template.substitute(code=escape(code), expire_minutes=expire_minutes)
    return send_html_email(
        recipient_email=recipient_email,
        recipient_name="使用者", 
        subject="社會影響力評估平台註冊驗證碼",
        html_content=html_content,
    )
