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
        exists = db.query(Account).filter(Account.email == settings.admin_email).first()
        if exists:
            print(f"[seed] 管理員 {settings.admin_email} 已存在")
            return

        admin = Account(
            email=settings.admin_email,
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