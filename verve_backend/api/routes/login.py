from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlmodel import col, select

from verve_backend import crud
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser, SessionDep
from verve_backend.core import security
from verve_backend.core.config import settings
from verve_backend.models import (
    PasswordResetToken,
    Token,
    User,
    UserPassword,
    UserPublic,
)

logger = structlog.getLogger(__name__)
router = APIRouter(tags=[Tag.AUTH])


@router.post("/login/access-token")
def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:  # noqa: RET506
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


class PasswordForgotResponse(BaseModel):
    message: str
    reset_link: str | None = None


class PasswordForgotPayload(BaseModel):
    email: EmailStr


@router.post("/login/forgot-password")
def forgot_password(
    session: SessionDep, data: PasswordForgotPayload
) -> PasswordForgotResponse:
    msg = "If this account exists, you will receive an email"

    link = None

    _user = session.exec(select(User).where(User.email == data.email)).first()
    if _user:
        token, _ = crud.add_reset_token(session=session, user_id=_user.id)
        link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"

    if settings.RESET_PASSWORD_RESPONSE == "append":
        return PasswordForgotResponse(message=msg, reset_link=link)

    else:
        raise NotImplementedError("Email sending not implemented yet")


class PasswordResetPayload(BaseModel):
    token: str
    new_password: UserPassword


@router.post("/login/reset-password")
def reset_password(session: SessionDep, data: PasswordResetPayload) -> Any:
    _now = datetime.now()

    valid_reset_token = session.exec(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == security.hash_reset_token(data.token),
            col(PasswordResetToken.used_at).is_(None),
            PasswordResetToken.expires_at > _now,
        )
    ).first()

    if not valid_reset_token:
        raise HTTPException(status_code=400, detail="Token expired")

    user = session.get(User, valid_reset_token.user_id)
    if not user:
        err_uuid = str(uuid4())
        logger.error(
            "User not found for valid password reset token",
            user_id=str(valid_reset_token.user_id),
            token_id=valid_reset_token.id,
            error_id=err_uuid,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal Error. Error code: {err_uuid}",
        )

    user.hashed_password = security.get_password_hash(data.new_password)

    for _token in session.exec(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            col(PasswordResetToken.used_at).is_(None),
            PasswordResetToken.expires_at > _now,
        )
    ).all():
        _token.used_at = _now
    session.commit()

    return JSONResponse(content="Password reset successful")
