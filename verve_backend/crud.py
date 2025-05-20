from sqlmodel import Session, select

from verve_backend.core.security import get_password_hash, verify_password
from verve_backend.models import (
    Activity,
    ActivityCreate,
    ActivityType,
    ActivityTypeCreate,
    User,
    UserCreate,
    UserPublic,
)


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        return None
    if not verify_password(password, db_user.hashed_password):
        return None
    return db_user


def create_activity(
    *,
    session: Session,
    create: ActivityCreate,
    user: UserPublic,
) -> Activity:
    db_obj = Activity.model_validate(create, update={"user_id": user.id})
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def create_activity_type(
    *, session: Session, create: ActivityTypeCreate
) -> ActivityType:
    db_obj = ActivityType.model_validate(create)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj
