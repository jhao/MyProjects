from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
    UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", DATA_DIR / "uploads"))
    DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'mpj.sqlite3'}")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 200 * 1024 * 1024))
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Ad123654")
    MAIL_HOST = os.environ.get("MAIL_HOST", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", MAIL_USERNAME or "noreply@localhost")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"

    @staticmethod
    def ensure_dirs():
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def is_mysql_url(url):
    return url.startswith("mysql://") or url.startswith("mysql+pymysql://")
