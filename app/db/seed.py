from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.model import Account, Role


def seed_admin() -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        print("[seed] 未設定 ADMIN_EMAIL / ADMIN_PASSWORD")
        return

    db = SessionLocal()
    try:
        # DB 只存前綴；舊資料可能存的是完整 email，兩種都算已存在
        prefix = settings.admin_email.split("@")[0].strip().lower()
        exists = db.query(Account).filter(Account.email.in_([settings.admin_email, prefix])).first()
        if exists:
            print(f"[seed] 管理員 {settings.admin_email} 已存在")
            return

        admin = Account(
            email=prefix,
            name=settings.admin_name,
            role=Role.ADMIN,
        )
        admin.set_password(settings.admin_password)
        db.add(admin)
        db.commit()
        print(f"[seed] 已建立管理員 {settings.admin_email}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()