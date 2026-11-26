from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.services.exchange_rates import get_exchange_rates, month_end_date
from app.models.model import FinancialProxy
from app.db.session import get_db
from app.core.deps import return_payload
from app.core.permissions import can_review_database
from app.schemas.financial_proxy import ExchangeRateMonth, FinancialProxyCreate

router = APIRouter()


class ProxyRead(FinancialProxyCreate):
    proxy_id: str
    review_status: Literal["pending", "approved", "rejected"]
    model_config = ConfigDict(from_attributes=True)


class ProxyOptionRead(ProxyRead):
    value_twd: Decimal | None
    exchange_rate: Decimal | None
    exchange_rate_date: date | None


class ProxyReviewDecision(BaseModel):
    approved: bool


def require_reviewer(db: Session, user_id: str) -> None:
    if not can_review_database(db, user_id):
        raise HTTPException(status_code=403, detail="只有資料庫編輯者或管理員能審核財務代理變數")


def get_owned_proxy(db: Session, proxy_id: str, user_id: str):
    item = (
        db.query(FinancialProxy)
        .filter(
            FinancialProxy.proxy_id == proxy_id,
            FinancialProxy.created_by == user_id,
            FinancialProxy.is_delete.is_(False),
        )
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Financial proxy not found")
    return item


@router.get("", response_model=list[ProxyRead])
def list_proxies(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):

    return (
        db.query(FinancialProxy)
        .filter(
            FinancialProxy.created_by == str(payload["user_id"]),
            FinancialProxy.is_delete.is_(False),
        )
        .order_by(FinancialProxy.create_time.desc())
        .all()
    )


def _approved_proxies(db: Session) -> list[FinancialProxy]:
    return (
        db.query(FinancialProxy)
        .filter(FinancialProxy.is_delete.is_(False), FinancialProxy.review_status == "approved")
        .order_by(FinancialProxy.name, FinancialProxy.create_time.desc())
        .all()
    )


@router.get("/catalog", response_model=list[ProxyRead])
def list_proxy_catalog(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[FinancialProxy]:
    return _approved_proxies(db)


@router.get("/options", response_model=list[ProxyOptionRead])
def list_proxy_options(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
    exchange_rate_month: ExchangeRateMonth | None = None,
):
    """提供已通過審核的代理變數及 SROI 所需的台幣換算。"""
    rate_date = month_end_date(exchange_rate_month)
    proxies = _approved_proxies(db)
    rates = get_exchange_rates({proxy.currency for proxy in proxies}, rate_date)
    options = []
    for proxy in proxies:
        exchange = rates.get(proxy.currency)
        options.append(ProxyOptionRead(
            **ProxyRead.model_validate(proxy).model_dump(),
            value_twd=proxy.value * exchange.rate_to_twd if exchange else None,
            exchange_rate=exchange.rate_to_twd if exchange else None,
            exchange_rate_date=exchange.date if exchange else None,
        ))
    return options


@router.get("/reviewing", response_model=list[ProxyRead])
def list_pending_proxies(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    require_reviewer(db, str(payload["user_id"]))
    return db.query(FinancialProxy).filter(
        FinancialProxy.is_delete.is_(False),
        FinancialProxy.review_status == "pending",
    ).order_by(FinancialProxy.create_time, FinancialProxy.proxy_id).all()


@router.post("/{proxy_id}/review", response_model=ProxyRead)
def review_proxy(
    proxy_id: str,
    data: ProxyReviewDecision,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    reviewer_id = str(payload["user_id"])
    require_reviewer(db, reviewer_id)
    item = db.query(FinancialProxy).filter(
        FinancialProxy.proxy_id == proxy_id,
        FinancialProxy.is_delete.is_(False),
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="找不到這筆申請")
    if item.review_status != "pending":
        raise HTTPException(status_code=409, detail="這筆申請已經處理")
    item.review_status = "approved" if data.approved else "rejected"
    item.reviewed_by = reviewer_id
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.post("", response_model=ProxyRead, status_code=status.HTTP_201_CREATED)
def create_proxy(
    data: FinancialProxyCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    item = FinancialProxy(
        created_by=str(payload["user_id"]),
        name=data.name,
        value=data.value,
        currency=data.currency,
        note=data.note,
        review_status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{proxy_id}", response_model=ProxyRead)
def update_proxy(
    proxy_id: str,
    data: FinancialProxyCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    item = get_owned_proxy(db, proxy_id, str(payload["user_id"]))
    if item.review_status != "rejected":
        raise HTTPException(status_code=409, detail="只有退回的申請可以修改後重新送審")
    item.name = data.name
    item.value = data.value
    if "currency" in data.model_fields_set:
        item.currency = data.currency
    item.note = data.note
    item.review_status = "pending"
    item.reviewed_by = None
    item.reviewed_at = None

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proxy(
    proxy_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    item = get_owned_proxy(db, proxy_id, str(payload["user_id"]))
    item.is_delete = True
    db.commit()
