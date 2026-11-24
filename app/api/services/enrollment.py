"""學生在學驗證。

規則：
- email 前綴是 9 碼數字才是學生，學號就是前綴，前三碼是入學年（民國）
- 大學四年：入學年 + 4 的那年 9/1 起需要驗證（上傳在學證明），10/1 截止
- 管理員審核通過就延長一年（下次驗證年 + 1）
- 截止後沒有審核中或通過的證明，帳號軟刪除；已上傳還沒審的保留，等審核結果
時間一律用台灣時間。
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.model import Account, EnrollmentStatus, EnrollmentVerification, GroupAccount, GroupRole


logger = logging.getLogger(__name__)

# 台灣沒有日光節約，用固定時差就不必依賴系統時區資料
TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")
STUDENT_ID_PATTERN = re.compile(r"^\d{9}$")
STUDY_YEARS = 4
VERIFY_MONTH = 9
ROC_OFFSET = 1911
DELETE_REASON_ENROLLMENT = "enrollment_expired"
DELETE_REASON_ADMIN = "admin"
MAINTENANCE_INTERVAL_SECONDS = 60 * 60

# 狀態
NOT_STUDENT = "not_student"
ACTIVE = "active"        # 還沒到驗證期
REQUIRED = "required"    # 驗證期間，還沒上傳
PENDING = "pending"      # 已上傳，等審核；可以照常使用
REJECTED = "rejected"    # 被退回，要重新上傳
EXPIRED = "expired"      # 過了截止日還沒通過，會被刪除
# 這些狀態只能使用驗證頁
BLOCKING_STATES = {REQUIRED, REJECTED, EXPIRED}
UPLOADABLE_STATES = {REQUIRED, REJECTED, PENDING}


def now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def student_id_of(email_prefix: str) -> Optional[str]:
    """email 前綴是 9 碼數字就是學號，否則不是學生"""
    prefix = email_prefix.split("@")[0]
    return prefix if STUDENT_ID_PATTERN.fullmatch(prefix) else None


def window_start(due_year: int) -> datetime:
    """驗證期開始：該民國年的 9/1 00:00"""
    return datetime(due_year + ROC_OFFSET, VERIFY_MONTH, 1, tzinfo=TAIPEI)


def window_end(due_year: int) -> datetime:
    """驗證截止：該民國年的 10/1 00:00（9 月整個月都可以上傳）"""
    return datetime(due_year + ROC_OFFSET, VERIFY_MONTH + 1, 1, tzinfo=TAIPEI)


def initial_due_year(campus_id: str, now: Optional[datetime] = None) -> int:
    """註冊時的第一次驗證年：入學年 + 4；那年的驗證期已經結束才註冊（很少見），排到下一個還沒結束的 9 月"""
    now = now or now_taipei()
    due = int(campus_id[:3]) + STUDY_YEARS
    while now >= window_end(due):
        due += 1
    return due


def latest_submission(db: Session, account: Account) -> Optional[EnrollmentVerification]:
    """這一期（目前的驗證年）最新的一份證明"""
    if account.verify_due_year is None:
        return None
    return db.query(EnrollmentVerification).filter(
        EnrollmentVerification.user_id == account.user_id,
        EnrollmentVerification.due_year == account.verify_due_year,
        EnrollmentVerification.is_delete.is_(False),
    ).order_by(EnrollmentVerification.create_time.desc()).first()


def enrollment_state(
    db: Session, account: Account, now: Optional[datetime] = None
) -> tuple[str, Optional[EnrollmentVerification]]:
    now = now or now_taipei()
    due = account.verify_due_year
    if due is None:
        return NOT_STUDENT, None
    if now < window_start(due):
        return ACTIVE, None
    latest = latest_submission(db, account)
    # 截止前上傳、還沒審的不刪，等審核結果
    if latest is not None and latest.status == EnrollmentStatus.PENDING:
        return PENDING, latest
    if now >= window_end(due):
        return EXPIRED, latest
    if latest is not None and latest.status == EnrollmentStatus.REJECTED:
        return REJECTED, latest
    return REQUIRED, latest


def serialize_submission(item: Optional[EnrollmentVerification]) -> Optional[dict]:
    if item is None:
        return None
    return {
        "verification_id": item.verification_id,
        "status": item.status,
        "reason": item.reason,
        "original_name": item.original_name,
        "size_bytes": item.size_bytes,
        "create_time": item.create_time,
        "reviewed_at": item.reviewed_at,
    }


def serialize_enrollment(db: Session, account: Account, now: Optional[datetime] = None) -> dict:
    state, latest = enrollment_state(db, account, now)
    due = account.verify_due_year
    return {
        "is_student": due is not None,
        "campus_id": account.campus_id,
        "state": state,
        "due_year": due,
        "window_start": window_start(due) if due is not None else None,
        # 截止時間是 10/1 00:00，畫面上顯示成 9/30
        "deadline": window_end(due) if due is not None else None,
        "latest": serialize_submission(latest),
    }


def ensure_group_leader(db: Session, group_id: str) -> None:
    """群組沒有組長時，依加入順序遞補：最早加入的編輯者，沒有就最早加入的檢視者"""
    members = db.query(GroupAccount).join(Account, Account.user_id == GroupAccount.user_id).filter(
        GroupAccount.group_id == group_id,
        GroupAccount.is_delete.is_(False),
        Account.is_delete.is_(False),
    ).order_by(GroupAccount.create_time).all()
    if any(member.group_role == GroupRole.LEADER for member in members):
        return
    for role in (GroupRole.EDITOR, GroupRole.VIEWER):
        candidate = next((member for member in members if member.group_role == role), None)
        if candidate is not None:
            candidate.group_role = GroupRole.LEADER
            logger.info("群組 %s 沒有組長，已遞補 %s 為組長", group_id, candidate.user_id)
            return
    # 沒有成員了就保留群組，由管理員在所有群組決定是否刪除


def soft_delete_account(db: Session, account: Account, reason: str) -> None:
    """軟刪除帳號：一併退出所有群組，失去組長的群組自動遞補。不 commit，由呼叫端決定"""
    account.is_delete = True
    account.delete_reason = reason
    memberships = db.query(GroupAccount).filter(
        GroupAccount.user_id == account.user_id,
        GroupAccount.is_delete.is_(False),
    ).all()
    for membership in memberships:
        membership.is_delete = True
    db.flush()
    for group_id in {membership.group_id for membership in memberships}:
        ensure_group_leader(db, group_id)


def expire_overdue_students(db: Session, now: Optional[datetime] = None) -> int:
    """刪除過了截止日還沒通過驗證的學生帳號，回傳刪除數量。不 commit"""
    now = now or now_taipei()
    # 只有驗證年 <= 今年的帳號可能過期，先縮小範圍
    candidates = db.query(Account).filter(
        Account.is_delete.is_(False),
        Account.verify_due_year.isnot(None),
        Account.verify_due_year <= now.year - ROC_OFFSET,
    ).all()
    removed = 0
    for account in candidates:
        state, _ = enrollment_state(db, account, now)
        if state == EXPIRED:
            soft_delete_account(db, account, DELETE_REASON_ENROLLMENT)
            removed += 1
    return removed


def _run_expiry_once() -> int:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        removed = expire_overdue_students(db)
        db.commit()
        return removed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def run_enrollment_maintenance() -> None:
    """啟動時先跑一次，之後每小時：刪除逾期未完成在學驗證的學生帳號"""
    while True:
        try:
            removed = await asyncio.to_thread(_run_expiry_once)
            if removed:
                logger.info("已刪除 %d 個逾期未完成在學驗證的帳號", removed)
        except Exception:
            logger.exception("檢查在學驗證到期失敗")
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
