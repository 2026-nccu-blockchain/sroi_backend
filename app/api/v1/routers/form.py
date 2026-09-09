from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.exceptions import APIException
from app.core.deps import return_payload
from app.db.session import get_db
from app.models.model import Account, Form


router = APIRouter()


@router.delete("/{form_id}")
def delete_form(
    form_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    payload = return_payload(request)

    # TODO: confirm auth.py should store Account.user_id in payload["id"]
    user_id = payload.get("id")

    if not user_id:
        raise APIException(
            401,
            "10005",
            "invalid token payload"
        )

    # 確認登入使用者存在
    account = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.is_delete == False
        )
        .first()
    )

    if not account:
        raise APIException(
            404,
            "30001",
            "account not found"
        )

    # 確認表單存在，而且尚未被刪除
    form = (
        db.query(Form)
        .filter(
            Form.form_id == form_id,
            Form.is_delete == False
        )
        .first()
    )

    if not form:
        raise APIException(
            404,
            "30002",
            "form not found"
        )

    # 目前先允許表單建立者刪除自己的表單
    # TODO: confirm whether admin/super admin can delete other users' forms
    if form.author_id != account.user_id:
        raise APIException(
            403,
            "30007",
            "permission denied"
        )

    try:
        # Soft delete：保留資料，只標記為已刪除
        form.is_delete = True
        db.commit()

    except Exception:
        db.rollback()
        raise APIException(
            500,
            "50002",
            "failed to delete form"
        )

    return {
        "status_code": "20000",
        "message": "form deleted successfully",
        "response_datetime": datetime.now(),
        "form_id": form_id
    }