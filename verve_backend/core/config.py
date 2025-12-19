import secrets
import warnings
from typing import Literal

from pydantic import (
    BaseModel,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


class DefautlSettings(BaseModel):
    activity_type: int
    activity_sub_type: int | None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["console", "json"] = "console"

    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    ENVIRONMENT: Literal["local", "staging", "production", "testing"] = "local"

    PROJECT_NAME: str = "Verve Outdoors Backend"
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = "changethis"
    POSTGRES_DB: str = ""
    POSTGRES_SCHEMA_NAME: str = "verve"

    POSTGRES_RLS_USER: str = "verve_user"
    POSTGRES_RLS_PASSWORD: str = "changethis"

    BOTO3_ENDPOINT: str = "localhost:9000"
    BOTO3_ACCESS: str
    BOTO3_SECRET: str
    BOTO3_SIGNATURE: str = "s3v4"
    BOTO3_REGION: str = "us-east-1"
    BOTO3_BUCKET_NAME: str = "verve"

    MAX_FILE_SIZE_MB: int = 10

    DEFAULTSETTINGS: DefautlSettings = DefautlSettings(
        activity_type=1, activity_sub_type=None
    )

    FRONTEND_HOST: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:  # noqa: N802
        return MultiHostUrl.build(  # type: ignore
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_RLS_DATABASE_URI(self) -> PostgresDsn:  # noqa: N802
        return MultiHostUrl.build(  # type: ignore
            scheme="postgresql+psycopg",
            username=self.POSTGRES_RLS_USER,
            password=self.POSTGRES_RLS_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def POSTGRES_SCHEMA(self) -> str:  # noqa: N802
        name = self.POSTGRES_SCHEMA_NAME
        if self.ENVIRONMENT == "testing":
            name = f"{name}_testing"
        return name

    @computed_field  # type: ignore[prop-decorator]
    @property
    def BOTO3_BUCKET(self) -> str:  # noqa: N802
        name = self.BOTO3_BUCKET_NAME
        if self.ENVIRONMENT == "testing":
            name = f"{name}-testing"
        return name

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret("POSTGRES_RLS_PASSWORD", self.POSTGRES_RLS_PASSWORD)
        self._check_default_secret("BOTO3_ACCESS", self.BOTO3_ACCESS)
        self._check_default_secret("BOTO3_SECRET", self.BOTO3_SECRET)
        self._check_default_secret("FRONTEND_HOST", self.FRONTEND_HOST)
        # elf._check_default_secret(
        #     "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        # )

        return self


settings = Settings()  # type: ignore
