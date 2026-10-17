from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    rachis_base_url: str = "https://rachis.co.in"
    rachis_username: str = ""
    rachis_password: str = ""
    headless: bool = False
    event_log_path: Path = Path("data/events.jsonl")
    # Seconds the visible browser holds after each step, so eyes can keep up
    # with what was just entered. The run is unattended; this is its only pause.
    step_delay: float = 3.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

