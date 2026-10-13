from decimal import Decimal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.models.model import FinancialProxy
from app.db.session import get_db
from app.core.deps import return_payload

router = APIRouter()




class ProxyCreate(BaseModel):
    name: str = Field(min_length=1)
    value: Decimal
    note: str = ""


class ProxyRead(ProxyCreate):
    proxy_id: str
    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[ProxyRead])
def list_proxies(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
):
    return db.query(FinancialProxy).filter(
        FinancialProxy.created_by == str(payload["user_id"]),
        FinancialProxy.is_delete.is_(False),
    ).order_by(FinancialProxy.create_time.desc()).all()


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