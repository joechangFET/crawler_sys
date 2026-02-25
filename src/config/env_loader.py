from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv, find_dotenv

# 先載入 .env（或交給 pydantic 自己從環境拿值也行）
load_dotenv(find_dotenv())

class Env(BaseSettings):
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


# Module-level singleton — import `env` directly instead of instantiating Env() each time.
env = Env()

