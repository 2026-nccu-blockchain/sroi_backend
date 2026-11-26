import json
import logging
import ssl
from calendar import monthrange
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException
from http.client import HTTPException
from threading import Lock
from time import monotonic
from typing import get_args
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

from app.core.exceptions import APIException
from app.schemas.financial_proxy import ProxyCurrency


logger = logging.getLogger(__name__)
_quotes = set(get_args(ProxyCurrency)) - {"TWD"}
_url = "https://api.frankfurter.dev/v2/rates"
_taipei = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ExchangeRate:
    rate_to_twd: Decimal
    date: date | None


TWD_RATE = ExchangeRate(Decimal("1"), None)
_cache: OrderedDict[date, tuple[float, dict[str, ExchangeRate]]] = OrderedDict()
_lock = Lock()


def month_end_date(month: str | None) -> date | None:
    if month is None:
        return None
    year, month_number = map(int, month.split("-"))
    last_day = date(year, month_number, monthrange(year, month_number)[1])
    if last_day > datetime.now(_taipei).date():
        raise APIException(400, "31001", "所選月份尚未到月底，請輸入已到月底的年月。")
    return last_day


def _fetch_rates(rate_date: date) -> dict[str, ExchangeRate]:
    params = urlencode({"base": "TWD", "quotes": ",".join(sorted(_quotes)), "date": rate_date.isoformat()})
    context = ssl.create_default_context()
    context.load_verify_locations(certifi.where())
    with urlopen(f"{_url}?{params}", timeout=5, context=context) as response:
        rows = json.load(response, parse_float=Decimal)
    if not isinstance(rows, list):
        raise ValueError("Expected a list of exchange rates")

    rates = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("base") != "TWD":
            continue
        quote = row.get("quote")
        if not isinstance(quote, str) or quote not in _quotes:
            continue
        try:
            rate = Decimal(row["rate"])
            observed = date.fromisoformat(row["date"])
            if observed == rate_date and rate.is_finite() and rate > 0:
                # Frankfurter quotes foreign units per TWD. Invert to get TWD per foreign unit.
                rates[quote] = ExchangeRate(Decimal("1") / rate, observed)
        except (KeyError, TypeError, ValueError, DecimalException):
            continue
    return rates


def get_exchange_rates(currencies: set[str], rate_date: date | None) -> dict[str, ExchangeRate]:
    if rate_date is None or currencies <= {"TWD"}:
        return {"TWD": TWD_RATE}

    with _lock:
        expiry, rates = _cache.get(rate_date, (0, {}))
        if monotonic() >= expiry:
            try:
                rates = _fetch_rates(rate_date)
            except (OSError, ValueError, HTTPException) as error:
                logger.warning("Frankfurter exchange rates unavailable for %s: %s", rate_date, error)
                rates = {}
            _cache[rate_date] = (monotonic() + (300 if rates else 15), rates)
        _cache.move_to_end(rate_date)
        if len(_cache) > 24:
            _cache.popitem(last=False)
        return {"TWD": TWD_RATE, **rates}
