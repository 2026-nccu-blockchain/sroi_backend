"""在學證明檔案：只接受 PDF、JPG、PNG，大小上限 5 MB；以檔案內容判斷格式，不看副檔名"""
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile

from app.api.services.interview_files import UPLOAD_ROOT
from app.core.exceptions import APIException


ENROLLMENT_UPLOAD_DIR = UPLOAD_ROOT / "enrollment_proofs"
ENROLLMENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_ENROLLMENT_FILE_SIZE = 5 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024


async def read_enrollment_file(upload: UploadFile) -> bytes:
    data = bytearray()
    while chunk := await upload.read(READ_CHUNK_SIZE):
        data += chunk
        if len(data) > MAX_ENROLLMENT_FILE_SIZE:
            raise APIException(400, "10032", "在學證明檔案不可超過 5 MB")
    if not data:
        raise APIException(400, "10033", "unsupported file type")
    return bytes(data)


def detect_enrollment_type(data: bytes) -> Optional[tuple[str, str]]:
    if data.startswith(b"%PDF-"):
        return ".pdf", "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    return None


def save_enrollment_file(data: bytes, extension: str) -> str:
    stored_name = f"{uuid4().hex}{extension}"
    (ENROLLMENT_UPLOAD_DIR / stored_name).write_bytes(data)
    return stored_name


def enrollment_file_path(stored_name: str) -> Path:
    # stored_name 由系統產生，仍確認沒有跳出資料夾
    path = (ENROLLMENT_UPLOAD_DIR / stored_name).resolve()
    if path.parent != ENROLLMENT_UPLOAD_DIR.resolve():
        raise APIException(404, "10034", "verification not found")
    return path
