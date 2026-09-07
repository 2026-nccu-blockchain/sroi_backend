# SROI Backend

### Please refer to this api document for more information

## Setup

### 1) Create a virtual environment

```bash
python -m venv .venv
```

### 2) Activate the environment

```bash
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Setup env file

```bash
cp .env.example .env
```

## Before Run

please check env is already rewriten

## Run

```bash
uvicorn app.main:app --reload
```

## Alembic

```bash
alembic revision --autogenerate -m "描述"  # 生成遷移腳本
alembic upgrade head                       # 執行遷移
alembic downgrade -1                       # 回滾一步
alembic current                            # 查看當前版本
alembic history                            # 查看遷移歷史
```

## Cloudinary api
We use [Cloudinary](https://cloudinary.com/) api to upload image and change it to url.  
You need a Cloudinary account to complete .env.

## Docker

```bash
docker compose up --build
```
