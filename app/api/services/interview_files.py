import asyncio
import json
import logging
import shutil
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4


logger = logging.getLogger(__name__)
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
INTERVIEW_UPLOAD_DIR = UPLOAD_ROOT / "interview_guides"
# 上傳後先放這裡，按「儲存專案」才搬到正式資料夾
INTERVIEW_TEMP_DIR = UPLOAD_ROOT / "interview_guides_tmp"
# 儲存專案時被刪除的訪綱移到這裡，定期壓縮成 .tar.gz 保留
INTERVIEW_DELETED_DIR = UPLOAD_ROOT / "interview_guides_deleted"
for directory in (INTERVIEW_UPLOAD_DIR, INTERVIEW_TEMP_DIR, INTERVIEW_DELETED_DIR):
    directory.mkdir(parents=True, exist_ok=True)
MAINTENANCE_INTERVAL_SECONDS = 24 * 60 * 60
# 只清掉放超過一個週期的檔案，避免剛上傳、還沒儲存的檔案被清掉
TEMP_MAX_AGE_SECONDS = MAINTENANCE_INTERVAL_SECONDS
DELETED_PREFIX = "delete_"
# 檔名日期用台灣時間；台灣沒有日光節約，用固定時差就不必依賴系統時區資料
TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")


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


def move_interview_file_to_deleted(stored_name: str) -> Optional[tuple[Path, Path]]:
    """移到刪除資料夾並在檔名前加 delete_YYYYMMDD_；回傳 (原路徑, 新路徑) 讓交易失敗時可以搬回去。"""
    source = INTERVIEW_UPLOAD_DIR / stored_name
    if not source.is_file():
        # 實體檔案已經不在，資料庫照常標記刪除即可
        logger.warning("要刪除的訪綱檔案不存在：%s", source)
        return None
    target = INTERVIEW_DELETED_DIR / f"{DELETED_PREFIX}{datetime.now(TAIPEI):%Y%m%d}_{stored_name}"
    shutil.move(source, target)
    return source, target


def archive_deleted_interview_files() -> int:
    """把還沒壓縮的刪除檔案打包成一個 .tar.gz，寫完才刪掉原檔。"""
    pending = sorted(
        path for path in INTERVIEW_DELETED_DIR.iterdir()
        if path.is_file() and path.name.startswith(DELETED_PREFIX)
    )
    if not pending:
        return 0
    archive = INTERVIEW_DELETED_DIR / f"deleted_{datetime.now(TAIPEI):%Y%m%d_%H%M%S}.tar.gz"
    if archive.exists():
        archive = archive.with_name(f"deleted_{datetime.now(TAIPEI):%Y%m%d_%H%M%S}_{uuid4().hex[:6]}.tar.gz")
    # 先寫成 .part，完整寫完才改名，避免中途失敗留下壞掉的壓縮檔
    partial = archive.with_name(f"{archive.name}.part")
    try:
        with tarfile.open(partial, "w:gz") as tar:
            for path in pending:
                tar.add(path, arcname=path.name)
        partial.replace(archive)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    for path in pending:
        path.unlink(missing_ok=True)
    return len(pending)


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


async def run_interview_file_maintenance() -> None:
    """啟動時先跑一次，之後每 24 小時：清除過期暫存檔、壓縮已刪除的檔案。"""
    while True:
        try:
            removed = await asyncio.to_thread(clear_expired_temp_interview_files)
            if removed:
                logger.info("已清除 %d 個過期的暫存訪綱檔案", removed)
        except Exception:
            logger.exception("清除暫存訪綱檔案失敗")
        try:
            archived = await asyncio.to_thread(archive_deleted_interview_files)
            if archived:
                logger.info("已壓縮 %d 個刪除的訪綱檔案", archived)
        except Exception:
            logger.exception("壓縮刪除的訪綱檔案失敗")
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
