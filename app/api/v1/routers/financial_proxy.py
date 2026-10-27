
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.models.model import FinancialProxy
from app.db.session import get_db
from app.core.deps import return_payload

router = APIRouter()


class ProxyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    value: Decimal
    note: str = ""


class ProxyUpdate(ProxyCreate):
    pass


class ProxyRead(ProxyCreate):
    proxy_id: str
    model_config = ConfigDict(from_attributes=True)


def get_owned_proxy(db: Session, proxy_id: str, user_id: str):
    item = (
        db.query(FinancialProxy)
        .filter(
            FinancialProxy.proxy_id == proxy_id,
            FinancialProxy.created_by == user_id,
            FinancialProxy.is_delete.is_(False),
        )
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



@router.post("", response_model=ProxyRead, status_code=status.HTTP_201_CREATED)
def create_proxy(
    data: ProxyCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    item = FinancialProxy(
        created_by=str(payload["user_id"]),
        name=data.name,
        value=data.value,
        note=data.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{proxy_id}", response_model=ProxyRead)
def update_proxy(
    proxy_id: str,
    data: ProxyUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    item = get_owned_proxy(db, proxy_id, str(payload["user_id"]))
    item.name = data.name
    item.value = data.value
    item.note = data.note

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
