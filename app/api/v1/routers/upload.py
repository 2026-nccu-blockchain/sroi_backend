import io
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, UploadFile, Request, Depends, File
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from PIL import Image
from pillow_heif import register_heif_opener
from app.db.session import get_db
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from app.models.model import Account
from app.core.deps import verify_token, return_payload

router = APIRouter()

register_heif_opener()
# 防止解壓縮炸彈：檔案很小但解開後像素數量極大
Image.MAX_IMAGE_PIXELS = 50_000_000

# HEIC / HEIF 共用同一種容器格式，看 ftyp 後面的 brand
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}

# 副檔名 -> magic bytes 檢查
# 只看檔案內容，不看 content_type：Chrome / Windows 上傳 HEIC 時 content_type 常是空的
ALLOWED_FILE_TYPES = {
    ".jpg": lambda h: h.startswith(b"\xff\xd8\xff"),
    ".png": lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"),
    ".webp": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP",
    ".heif": lambda h: h[4:8] == b"ftyp" and h[8:12] in HEIF_BRANDS,
    ".pdf": lambda h: h.startswith(b"%PDF-"),
}
# 實際存檔的格式（HEIF 會轉成 JPG），管理員讀取時用來設定 Content-Type
MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
CHUNK_SIZE = 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "images"  # app/uploads/images
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def detect_ext(header: bytes) -> str | None:
    return next((ext for ext, check in ALLOWED_FILE_TYPES.items() if check(header)), None)


async def read_limited(image: UploadFile) -> bytes | None:
    """讀完整個檔案，超過 MAX_FILE_SIZE 就回傳 None"""
    data = bytearray()
    while chunk := await image.read(CHUNK_SIZE):
        data += chunk
        if len(data) > MAX_FILE_SIZE:
            return None
    return bytes(data)


def heif_to_jpeg(data: bytes) -> bytes:
    # libheif 解碼時已經依照拍攝方向轉正；另存 JPG 時不帶 EXIF，GPS 位置會一起移除
    with Image.open(io.BytesIO(data)) as img:
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=90)
        return out.getvalue()


@router.post("/image", response_model=APIResponse, response_model_exclude_none=True)
async def upload(request: Request, image: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")

    data = await read_limited(image)
    if data is None:
        raise APIException(400, "10019", "upload file too large")

    ext = detect_ext(data[:16])
    if ext is None:
        raise APIException(400, "10018", "unsupported file type")

    if ext == ".heif":
        try:
            # 解碼比較吃 CPU，丟到 thread pool 才不會卡住其他請求
            data = await run_in_threadpool(heif_to_jpeg, data)
        except Exception:
            # 檔頭像 HEIF 但內容壞掉
            raise APIException(400, "10018", "unsupported file type")
        ext = ".jpg"

    filename = f"{user_id}_{uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        id_card_link=filename,
    )
