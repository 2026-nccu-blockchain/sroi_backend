# SROI Backend

SROI 系統後端，使用 FastAPI、SQLAlchemy、Alembic 與 PostgreSQL。

## 本機開發

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # 填入 SECRET_KEY、DATABASE_URL 等設定
```

接著執行 migration 並啟動：

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

API 文件：http://localhost:8000/docs

## 環境變數

主要設定如下，完整清單請見 `.env.example`。

| 變數 | 說明 |
|---|---|
| `DATABASE_URL` | PostgreSQL 連線字串 |
| `SECRET_KEY` | JWT 簽章金鑰 |
| `JWT_EXPIRATION_MINUTES` | Token 有效時間（分鐘） |
| `MAX_REQUESTS` / `WINDOW_SECONDS` | Rate limit 設定 |

## Alembic

```bash
alembic revision --autogenerate -m "描述"   # 產生 migration
alembic upgrade head                        # 套用到最新版本
alembic downgrade -1                        # 回復一個版本
alembic current                             # 查看目前版本
alembic history                             # 查看 migration 歷史
```

## 測試

```bash
pytest
```

## 上傳檔案

上傳的檔案會存放在 `app/uploads/`，這個資料夾不納入 git。
在 Docker 環境中，這個資料夾會掛載到 volume，重建容器也不會遺失。

## Docker

容器啟動時會自動執行 `alembic upgrade head`，再啟動 uvicorn。
一般請從上層的 `docker-compose.yml` 啟動。