from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.jwt import create_access_token, decode_access_token
from app.core.deps import verify_token, return_payload
import re
import pytz

router = APIRouter()