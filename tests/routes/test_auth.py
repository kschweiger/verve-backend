import re
from datetime import datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlmodel import Session, select

from verve_backend import crud
from verve_backend.api.routes.login import PasswordForgotResponse
from verve_backend.models import PasswordResetToken, User


def test_forgot_password(db: Session, client: TestClient, user1_id: UUID) -> None:
    from verve_backend.core.config import settings

    # Tests assume append mode
    assert settings.RESET_PASSWORD_RESPONSE == "append"

    response = client.post(
        "/login/forgot-password",
        json={"email": "user1@mail.com"},
    )
    assert response.status_code == 200

    _resp = PasswordForgotResponse.model_validate(response.json())
    assert _resp.message == "If this account exists, you will receive an email"
    assert _resp.reset_link is not None
    assert "reset-password?token=" in _resp.reset_link

    tokens = db.exec(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user1_id)
    ).all()

    assert len(tokens) == 1


def test_forgot_password_unknown_email(db: Session, client: TestClient) -> None:
    from verve_backend.core.config import settings

    tokens_pre = db.exec(select(PasswordResetToken)).all()
    # Tests assume append mode
    assert settings.RESET_PASSWORD_RESPONSE == "append"

    response = client.post(
        "/login/forgot-password",
        json={"email": "random@mail.com"},
    )
    assert response.status_code == 200

    _resp = PasswordForgotResponse.model_validate(response.json())
    assert _resp.message == "If this account exists, you will receive an email"
    assert _resp.reset_link is None

    tokens_post = db.exec(select(PasswordResetToken)).all()

    assert len(tokens_pre) == len(tokens_post)


def test_reset_password(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    from verve_backend.core.config import settings

    # Tests assume append mode
    assert settings.RESET_PASSWORD_RESPONSE == "append"

    temp_user = db.get(User, temp_user_id)
    assert temp_user is not None
    orig_pw_hash = temp_user.hashed_password

    now = datetime.now()
    for i in range(5):
        with freeze_time(now - timedelta(minutes=i)):
            crud.add_reset_token(session=db, user_id=temp_user_id)

    response = client.post(
        "/login/forgot-password",
        json={"email": temp_user.email},
    )
    assert response.status_code == 200
    _resp = PasswordForgotResponse.model_validate(response.json())

    assert _resp.reset_link is not None

    m = re.search(r"[?&]token=([^&#]+)", _resp.reset_link)
    reset_token = m.group(1) if m else None

    response = client.post(
        "/login/reset-password",
        json={"token": reset_token, "new_password": "newpassword123"},
    )
    assert response.status_code == 200

    db.reset()

    temp_user = db.get(User, temp_user_id)
    assert temp_user is not None
    assert temp_user.hashed_password != orig_pw_hash
    tokens = db.exec(
        select(PasswordResetToken).where(PasswordResetToken.user_id == temp_user_id)
    ).all()
    for _token in tokens:
        assert _token.used_at is not None


def test_reset_password_token_expired(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    now = datetime.now()
    with freeze_time(now - timedelta(minutes=120)):
        token, _ = crud.add_reset_token(session=db, user_id=temp_user_id)

    response = client.post(
        "/login/reset-password",
        json={"token": token, "new_password": "newpassword123"},
    )
    assert response.status_code == 400
