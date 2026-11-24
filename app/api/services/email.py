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


# 驗證碼信件依用途換文字；模板相同
VERIFICATION_EMAIL_TEXTS = {
    "register": {
        "subject": "社會影響力評估平台註冊驗證碼",
        "heading": "註冊驗證碼",
        "instruction": "請複製下方驗證碼，回到註冊頁面填入以完成 Email 驗證。",
        "ignore_text": "如果你沒有申請註冊社會影響力評估平台，可以忽略此信件。",
    },
    "reset_password": {
        "subject": "社會影響力評估平台重設密碼驗證碼",
        "heading": "重設密碼驗證碼",
        "instruction": "請複製下方驗證碼，回到忘記密碼頁面填入，即可設定新密碼。",
        "ignore_text": "如果你沒有申請重設密碼，可以忽略此信件，你的密碼不會改變。",
    },
}


def send_verification_code_email(
    *, recipient_email: str, code: str, expire_minutes: int, purpose: str = "register"
) -> str:
    """寄送驗證碼（註冊或忘記密碼）；信中只有驗證碼，沒有任何連結"""
    texts = VERIFICATION_EMAIL_TEXTS[purpose]
    template = Template((EMAIL_TEMPLATE_DIR / "verification_code.html").read_text(encoding="utf-8"))
    html_content = template.substitute(
        code=escape(code),
        expire_minutes=expire_minutes,
        **{key: escape(value) for key, value in texts.items()},
    )
    return send_html_email(
        recipient_email=recipient_email,
        recipient_name="使用者",
        subject=texts["subject"],
        html_content=html_content,
    )
