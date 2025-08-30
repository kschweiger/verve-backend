import logging
from collections.abc import Generator
from typing import Annotated

import boto3
import jwt
from botocore.config import Config
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from mypy_boto3_s3.client import S3Client
from pydantic import ValidationError
from sqlmodel import Session, text

from verve_backend.core import security
from verve_backend.core.config import settings
from verve_backend.core.db import get_engine
from verve_backend.models import TokenPayload, User

logger = logging.getLogger("uvicorn.error")
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
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
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_session(user: CurrentUser) -> Generator[tuple[str, Session], None, None]:
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    with Session(get_engine(rls=True, echo=False)) as session:
        session.exec(text(f"SET verve_user.curr_user = '{user.id}'"))  # type: ignore
        session.commit()
        yield str(user.id), session


UserSession = Annotated[tuple[str, Session], Depends(get_user_session)]


# TODO: Maybe we wrap this into a ObjectStore class with some abstract methods
def get_s3_client() -> S3Client:
    client = boto3.client(
        "s3",
        endpoint_url=settings.BOTO3_ENDPOINT,
        aws_access_key_id=settings.BOTO3_ACCESS,
        aws_secret_access_key=settings.BOTO3_SECRET,
        config=Config(signature_version=settings.BOTO3_SIGNATURE),
        region_name=settings.BOTO3_REGION,
    )
    all_buckets = set(
        [b["Name"] for b in client.list_buckets()["Buckets"]]  # type: ignore
    )
    if "verve" not in all_buckets:
        try:
            client.create_bucket(Bucket="verve")
            print("Bucket created successfully")
        except Exception as e:
            logger.error(f"Bucket creation error: {e}")
            raise e
    return client


ObjectStoreClient = Annotated[S3Client, Depends(get_s3_client)]
