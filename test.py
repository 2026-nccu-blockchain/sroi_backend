from sqlalchemy import create_engine, text


# PostgreSQL 連線資訊
DATABASE_URL = "postgresql+psycopg2://admin:MyPassword@localhost:15432/app"


try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=True
    )

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))

        print("PostgreSQL 連線成功！")
        print("測試結果:", result.fetchone())


except Exception as e:
    print("PostgreSQL 連線失敗")
    print(e)