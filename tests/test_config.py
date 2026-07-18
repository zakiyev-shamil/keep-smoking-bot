import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_bot_username_is_normalized():
    settings = Settings(bot_username="@KeepSmokingBot")

    assert settings.bot_username == "KeepSmokingBot"


def test_bot_username_with_spaces_is_rejected():
    with pytest.raises(ValidationError):
        Settings(bot_username="Keep Smoking")


def test_neon_database_url_is_normalized_for_asyncpg():
    settings = Settings(
        database_url=(
            "postgresql://user:password@example-pooler.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        )
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:password@example-pooler.neon.tech/neondb?ssl=require"
    )
