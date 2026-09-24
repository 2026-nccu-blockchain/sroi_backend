from pathlib import Path
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, UploadFile, Request, Depends, File
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from app.models.model import Account
from app.core.deps import verify_token, return_payload

router = APIRouter()

# content_type -> (副檔名, magic bytes 檢查)
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", lambda h: h.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda h: h.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": (".webp", lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP"),
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
CHUNK_SIZE = 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "images"  # app/uploads/images
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/image", response_model=APIResponse, response_model_exclude_none=True)
async def upload(request: Request, image: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")

    allowed = ALLOWED_IMAGE_TYPES.get(image.content_type)
    if allowed is None:
        raise APIException(400, "10018", "upload not an image")
    ext, check_magic = allowed

    header = await image.read(16)
    if not check_magic(header):
        raise APIException(400, "10018", "upload not an image")

    filename = f"{user_id}_{uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / filename

    too_large = False
    total_size = len(header)
    with file_path.open("wb") as buffer:
        buffer.write(header)
        while chunk := await image.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                too_large = True
                break
            buffer.write(chunk)

    if too_large:
        file_path.unlink(missing_ok=True)
        raise APIException(400, "10019", "upload file too large")

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        id_card_link=filename,
    )