"""校外人士帳號：管理員邀請 → 寄出 7 天有效的連結 → 對方設定姓名與密碼才建立帳號。

- 校外帳號的 email 存完整地址（小寫），政大帳號只存前綴，兩者不會混用
- 使用年限 1～4 年，從完成註冊那天開始算；到期後不能登入，管理員可延長
"""
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.exceptions import APIException
from app.models.model import ACCOUNT_EXTERNAL, EMAIL_DOMAIN, Account, ExternalInvitation


INVITE_LINK_DAYS = 7
MIN_VALID_YEARS = 1
MAX_VALID_YEARS = 4
EMAIL_PATTERN = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_external_email(email: str) -> str:
    """校外 email：轉小寫、去空白；格式不對或是政大信箱都擋下"""
    value = (email or "").strip().lower()
    if not EMAIL_PATTERN.fullmatch(value):
        raise APIException(400, "10007", "invalid email format")
    # 政大師生請用政大信箱自行註冊，不走校外邀請
    if value.endswith(EMAIL_DOMAIN):
        raise APIException(400, "10040", "nccu email must self-register")
    return value


def add_years(value: datetime, years: int) -> datetime:
    """加上年數；2/29 遇到非閏年改成 2/28"""
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def is_external(account: Account) -> bool:
    return account.account_type == ACCOUNT_EXTERNAL


def is_external_expired(account: Account, now: Optional[datetime] = None) -> bool:
    """校外帳號已過使用期限"""
    if not is_external(account) or account.valid_until is None:
        return False
    return (now or now_utc()) >= account.valid_until


def extend_valid_until(account: Account, years: int, now: Optional[datetime] = None) -> None:
    """延長使用期限：還沒到期從原到期日往後加，已到期從今天起算"""
    now = now or now_utc()
    base = account.valid_until if account.valid_until and account.valid_until > now else now
    account.valid_until = add_years(base, years)


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def invitation_status(invitation: ExternalInvitation, now: Optional[datetime] = None) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.is_delete:
        return "cancelled"
    if (now or now_utc()) >= invitation.expires_at:
        return "link_expired"
    return "pending"


def serialize_invitation(invitation: ExternalInvitation, now: Optional[datetime] = None) -> dict:
    return {
        "invitation_id": invitation.invitation_id,
        "email": invitation.email,
        "organization": invitation.organization,
        "valid_years": invitation.valid_years,
        "expires_at": invitation.expires_at,
        "create_time": invitation.create_time,
        # pending 連結有效；link_expired 連結過期，可以重寄
        "status": invitation_status(invitation, now),
    }


def account_extra(account: Account) -> dict:
    """管理員清單與詳細頁要顯示的帳號類型、所屬單位、到期日"""
    return {
        "account_type": account.account_type,
        "organization": account.organization,
        "valid_until": account.valid_until,
    }
