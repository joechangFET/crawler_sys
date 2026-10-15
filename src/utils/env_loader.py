"""Validate process and .env settings for crawler credentials and reporting.

Importing this module loads .env and constructs the shared env instance.
Missing required settings therefore fail validation during import.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv, find_dotenv

# 先載入 .env（或交給 pydantic 自己從環境拿值也行）
load_dotenv(find_dotenv())

class Env(BaseSettings):
    """Validate required crawler settings and optional browser/email preferences."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",               # 未宣告的環境變數忽略
        case_sensitive=False,         # 環境變數不分大小寫
        env_nested_delimiter="__",    # 支援 NESTED__KEY 形式
    )

    LOG_LEVEL: str
    HEADLESS: bool = True
    KKTIX_USER: str
    KKTIX_PASSWORD: str
    CAPSOLVER_API: str
    CHATGPT_API_KEY: str

    # Gmail 報表寄送（選填，未設定則跳過寄信）
    MAIL_SENDER: str | None = None
    MAIL_APP_PASSWORD: str | None = None
    # 逗號分隔多個收件人：a@gmail.com,b@gmail.com
    MAIL_RECEIVERS: list[str] = []

    @field_validator("MAIL_RECEIVERS", mode="before")
    @classmethod
    def parse_receivers(cls, v: str | list | None) -> list[str]:
        """Normalize comma-separated or list-based recipients, stripping empty entries."""
        if not v:
            return []
        if isinstance(v, list):
            return [r.strip() for r in v if r.strip()]
        return [r.strip() for r in v.split(",") if r.strip()]


# Module-level singleton — import `env` directly instead of instantiating Env() each time.
env = Env()
