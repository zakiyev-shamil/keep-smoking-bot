from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import EventType


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: SecretStr = SecretStr("")
    bot_username: str = ""
    webhook_secret: SecretStr = SecretStr("")
    database_url: str = "postgresql+asyncpg://office_party:office_party@postgres:5432/office_party"
    log_level: str = "INFO"
    default_timezone: str = "Asia/Almaty"

    smoke_event_ttl_minutes: int = Field(default=15, ge=1)
    coffee_event_ttl_minutes: int = Field(default=20, ge=1)
    lunch_event_ttl_minutes: int = Field(default=30, ge=1)
    after_work_event_ttl_minutes: int = Field(default=180, ge=1)
    custom_event_ttl_minutes: int = Field(default=30, ge=1)

    smoke_cooldown_minutes: int = Field(default=5, ge=0)
    coffee_cooldown_minutes: int = Field(default=0, ge=0)
    lunch_cooldown_minutes: int = Field(default=0, ge=0)
    after_work_cooldown_minutes: int = Field(default=0, ge=0)
    custom_cooldown_minutes: int = Field(default=0, ge=0)

    notification_concurrency: int = Field(default=10, ge=1, le=50)
    notification_rate_per_second: int = Field(default=25, ge=1, le=30)
    notify_on_event_started: bool = True
    notify_on_event_cancelled: bool = True
    event_expiration_interval_seconds: int = Field(default=30, ge=5)

    @field_validator("bot_username")
    @classmethod
    def validate_bot_username(cls, value: str) -> str:
        username = value.strip().removeprefix("@")
        if username and re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) is None:
            raise ValueError("BOT_USERNAME must be a Telegram username without spaces")
        return username

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        database_url = value.strip()
        if database_url.startswith("postgres://"):
            database_url = "postgresql+asyncpg://" + database_url.removeprefix("postgres://")
        elif database_url.startswith("postgresql://"):
            database_url = "postgresql+asyncpg://" + database_url.removeprefix("postgresql://")
        if not database_url.startswith("postgresql+asyncpg://"):
            return database_url

        parsed = urlsplit(database_url)
        query: list[tuple[str, str]] = []
        for key, item in parse_qsl(parsed.query, keep_blank_values=True):
            if key == "channel_binding":
                continue
            if key == "sslmode":
                key = "ssl"
            query.append((key, item))
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )

    def event_ttl_minutes(self, event_type: EventType) -> int:
        return {
            EventType.SMOKE: self.smoke_event_ttl_minutes,
            EventType.COFFEE: self.coffee_event_ttl_minutes,
            EventType.LUNCH: self.lunch_event_ttl_minutes,
            EventType.AFTER_WORK: self.after_work_event_ttl_minutes,
            EventType.CUSTOM: self.custom_event_ttl_minutes,
        }[event_type]

    def event_cooldown_minutes(self, event_type: EventType) -> int:
        return {
            EventType.SMOKE: self.smoke_cooldown_minutes,
            EventType.COFFEE: self.coffee_cooldown_minutes,
            EventType.LUNCH: self.lunch_cooldown_minutes,
            EventType.AFTER_WORK: self.after_work_cooldown_minutes,
            EventType.CUSTOM: self.custom_cooldown_minutes,
        }[event_type]


@lru_cache
def get_settings() -> Settings:
    return Settings()
