# FastAPI Starter

一個可直接開發與部署的 Python FastAPI 專案範本（Python 3.10+）。

## Features

- FastAPI 專案結構（`app/`）
- 環境設定管理（`pydantic-settings`）
- 健康檢查路由（`/api/v1/health`）
- `pytest` 測試範例
- `ruff` 格式化與靜態檢查設定
- Docker / Docker Compose 啟動支援

## 專案結構

```text
.
├── app
│   ├── api
│   │   └── v1
│   │       └── health.py
│   ├── core
│   │   └── config.py
│   └── main.py
├── tests
│   └── test_health.py
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## Quick Start (Poetry)

1. 安裝相依套件：

   ```bash
   poetry install
   ```

2. 建立環境變數檔：

   ```bash
   cp .env.example .env
   ```

3. 啟動 API：

   ```bash
   poetry run uvicorn app.main:app --reload
   ```

4. 開啟文件：
   - Swagger UI: <http://127.0.0.1:8000/docs>
   - ReDoc: <http://127.0.0.1:8000/redoc>

## 測試與品質

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format .
```

## Docker

```bash
docker compose up --build
```
