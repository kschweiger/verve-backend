from collections.abc import Generator
from typing import Annotated, AsyncGenerator
from uuid import UUID

import boto3
import jwt
import structlog
from botocore.config import Config
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from mypy_boto3_s3.client import S3Client
from pydantic import ValidationError
from sqlmodel import Session, text
from starlette.concurrency import run_in_threadpool
from structlog.contextvars import bind_contextvars

from verve_backend.core import security
from verve_backend.core.config import settings
from verve_backend.core.db import get_engine
from verve_backend.models import SupportedLocale, TokenPayload, User

logger = structlog.getLogger(__name__)
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    bind_contextvars(user_id=str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _create_rls_session(user_id: UUID) -> Session:
    # Assuming get_engine is synchronous
    engine = get_engine(rls=True, echo=False)
    session = Session(engine)
    session.exec(text(f"SET verve_user.curr_user = '{user_id}'"))  # type: ignore
    session.commit()
    return session


async def get_user_session(
    user: CurrentUser,
) -> AsyncGenerator[tuple[str, Session], None]:
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. Run the blocking setup in a threadpool
    #    This ensures we don't freeze the main asyncio loop while connecting/setting RLS
    session = await run_in_threadpool(_create_rls_session, user.id)

    try:
        # 2. Yield to the path operation
        yield str(user.id), session
    finally:
        # 3. Ensure we close the session safely in a threadpool when done
        await run_in_threadpool(session.close)


UserSession = Annotated[tuple[str, Session], Depends(get_user_session)]


async def get_s3_client() -> S3Client:
    client = boto3.client(
        "s3",
        endpoint_url=settings.BOTO3_ENDPOINT,
        aws_access_key_id=settings.BOTO3_ACCESS,
        aws_secret_access_key=settings.BOTO3_SECRET,
        config=Config(signature_version=settings.BOTO3_SIGNATURE),
        region_name=settings.BOTO3_REGION,
    )
    return client


async def ensure_bucket_exists(client: S3Client, bucket_name: str = "verve") -> None:
    all_buckets = set(
        [b["Name"] for b in client.list_buckets()["Buckets"]]  # type: ignore
    )
    if bucket_name not in all_buckets:
        try:
            client.create_bucket(Bucket=bucket_name)
            print("Bucket created successfully")
        except Exception as e:
            logger.error(f"Bucket creation error: {e}")
            raise e


async def get_and_init_s3_client() -> S3Client:
    client = await get_s3_client()
    await ensure_bucket_exists(client, bucket_name=settings.BOTO3_BUCKET)
    return client


ObjectStoreClient = Annotated[S3Client, Depends(get_and_init_s3_client)]


LocaleQuery = Annotated[
    SupportedLocale,
    Query(
        description="Language code (ISO 639-1)",
    ),
]
