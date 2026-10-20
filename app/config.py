from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    base_url: str = "https://rachis.co.in"
    username: str = ""
    password: str = ""
    headless: bool = False
    # Remote event ingestion endpoint over HTTP Basic Auth.
    # When empty, events are not recorded anywhere — no local log is kept.
    # Only the password is validated by the remote (no username needed).
    events_url: str = ""
    events_password: str = ""
    # Seconds the visible browser holds after each step, so eyes can keep up
    # with what was just entered. The run is unattended; this is its only pause.
    step_delay: float = 3.0
    slow_mo_ms: int = 3000

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()

