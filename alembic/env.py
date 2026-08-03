"""
Alembic 環境配置
"""
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# 添加項目根目錄到 Python 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 導入模型
from app.db.base import Base
from app.models import model    # 確保所有模型都被導入
from app.core.config import get_settings

# 獲取 alembic 配置
config = context.config

settings = get_settings()
DATABASE_URL = settings.database_url
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# 設置目標模型
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在離線模式下運行遷移"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在線上模式下運行遷移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
