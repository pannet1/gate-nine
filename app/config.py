from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    rachis_base_url: str = "https://rachis.co.in"
    rachis_username: str = ""
    rachis_password: str = ""
    headless: bool = False
    artifacts_dir: Path = Path("artifacts")
    event_log_path: Path = Path("data/events.jsonl")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

