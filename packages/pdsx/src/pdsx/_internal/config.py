"""configuration management for pdsx."""

from __future__ import annotations

import warnings
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# suppress pydantic warning about Field defaults
warnings.filterwarnings(
    "ignore", category=UserWarning, module="pydantic._internal._generate_schema"
)


class Settings(BaseSettings):
    """settings for atproto cli."""

    model_config = SettingsConfigDict(
        env_file=str(Path.cwd() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    atproto_pds_url: str = Field(
        default="https://bsky.social",
        description="PDS URL (only used for unauthenticated reads with -r flag)",
    )
    atproto_handle: str = Field(default="", description="Your atproto handle")
    atproto_password: str = Field(default="", description="Your atproto app password")


settings = Settings()
