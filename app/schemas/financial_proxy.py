from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class FinancialProxyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    value: Decimal = Field(max_digits=18, decimal_places=4)
    note: str = ""


class FinancialProxyResponse(FinancialProxyCreate):
    proxy_id: str
    created_by: str
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)