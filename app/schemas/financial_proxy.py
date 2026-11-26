from decimal import Decimal
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ConfigDict


ProxyCurrency = Literal[
    "TWD", "USD", "JPY", "EUR", "GBP", "HKD", "CNY", "AUD", "KRW", "SGD",
    "CAD", "CHF", "THB", "VND", "MYR", "IDR", "PHP", "NZD", "INR",
]
ExchangeRateMonth = Annotated[str, Field(pattern=r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$")]


class FinancialProxyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    value: Decimal = Field(max_digits=18, decimal_places=4)
    currency: ProxyCurrency = "TWD"
    unit: str = Field(default="元", min_length=1, max_length=50)
    note: str = ""


class FinancialProxyResponse(FinancialProxyCreate):
    proxy_id: str
    created_by: str
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)
