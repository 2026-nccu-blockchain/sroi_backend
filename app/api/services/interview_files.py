import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4


logger = logging.getLogger(__name__)
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
INTERVIEW_UPLOAD_DIR = UPLOAD_ROOT / "interview_guides"
# 上傳後先放這裡，按「儲存專案」才搬到正式資料夾
INTERVIEW_TEMP_DIR = UPLOAD_ROOT / "interview_guides_tmp"
INTERVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INTERVIEW_TEMP_DIR.mkdir(parents=True, exist_ok=True)
TEMP_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
# 只清掉放超過一個週期的檔案，避免剛上傳、還沒儲存的檔案被清掉
TEMP_MAX_AGE_SECONDS = TEMP_CLEANUP_INTERVAL_SECONDS


def save_temp_interview_file(
    project_id: str,
    data: bytes,
    original_name: str,
    extension: str,
    content_type: str,
) -> dict:
    temp_file_id = uuid4().hex
    meta = {
        "temp_file_id": temp_file_id,
        "project_id": project_id,
        "original_name": original_name,
        "extension": extension,
        "content_type": content_type,
        "size_bytes": len(data),
    }
    (INTERVIEW_TEMP_DIR / f"{temp_file_id}{extension}").write_bytes(data)
    # 原始檔名等資料存在旁邊的 json，暫存期間不寫資料庫
    (INTERVIEW_TEMP_DIR / f"{temp_file_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def load_temp_interview_file(project_id: str, temp_file_id: str) -> Optional[dict]:
    """找不到、已被清掉或不是這個專案上傳的都回 None。temp_file_id 已由 schema 限制為 32 碼 hex。"""
    meta_path = INTERVIEW_TEMP_DIR / f"{temp_file_id}.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if meta.get("project_id") != project_id:
        return None
    path = INTERVIEW_TEMP_DIR / f"{temp_file_id}{meta['extension']}"
    if not path.is_file():
        return None
    return {**meta, "path": path}


def discard_temp_interview_file(meta: dict) -> None:
    meta["path"].unlink(missing_ok=True)
    (INTERVIEW_TEMP_DIR / f"{meta['temp_file_id']}.json").unlink(missing_ok=True)


def promote_temp_interview_file(meta: dict, stored_name: str) -> Path:
    """複製到正式資料夾；交易失敗時呼叫端刪掉回傳的路徑即可，暫存檔仍在。"""
    target = INTERVIEW_UPLOAD_DIR / stored_name
    shutil.copyfile(meta["path"], target)
    return target


def clear_expired_temp_interview_files() -> int:
    deadline = time.time() - TEMP_MAX_AGE_SECONDS
    removed = 0
    for path in INTERVIEW_TEMP_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < deadline:
                path.unlink()
                removed += 1
        except OSError:
            logger.warning("無法刪除暫存訪綱檔案 %s", path, exc_info=True)
    return removed


async def run_temp_interview_cleanup() -> None:
    """啟動時先清一次，之後每 24 小時清一次。"""
    while True:
        try:
            removed = await asyncio.to_thread(clear_expired_temp_interview_files)
            if removed:
                logger.info("已清除 %d 個過期的暫存訪綱檔案", removed)
        except Exception:
            logger.exception("清除暫存訪綱檔案失敗")
        await asyncio.sleep(TEMP_CLEANUP_INTERVAL_SECONDS)
