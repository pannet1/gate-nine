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

# The supplied local file uses the legacy form `username: value` rather than
# dotenv's `RACHIS_USERNAME=value`. Support it locally without copying the
# secret into source code; `.env` remains ignored by Git.
if not settings.rachis_username or not settings.rachis_password:
    legacy_env = Path(".env")
    if legacy_env.exists():
        legacy: dict[str, str] = {}
        for line in legacy_env.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator:
                legacy[key.strip().lower()] = value.strip()
        settings.rachis_username = settings.rachis_username or legacy.get("username", "")
        settings.rachis_password = settings.rachis_password or legacy.get("password", "")

