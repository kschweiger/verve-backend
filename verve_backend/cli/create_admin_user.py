import argparse

from sqlmodel import Session, select

from verve_backend.core.db import get_engine
from verve_backend.models import (
    User,
    UserCreate,
)
from verve_backend.result import Err, Ok


def create_admin_user(session: Session, email: str, password: str) -> None:
    from verve_backend.crud import create_user

    if session.exec(select(User).where(User.email == email)).first():
        print("Admin user already exists.")
        return

    user = UserCreate(
        name="verve_admin",
        email=email,
        password=password,
    )
    match create_user(
        session=session,
        user_create=user,
        is_admin=True,
    ):
        case Ok(user):
            print("Admin user created")
        case Err(_id):
            print("Creating admin user failed")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description=("Create the admin user"))
    parser.add_argument(
        "--schema",
        type=str,
        default="api",
        help="Database schema name (default: verve)",
    )
    parser.add_argument(
        "--email",
        type=str,
        help="Admin email address",
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Password for the admin user",
    )
    args = parser.parse_args()

    engine = get_engine()

    with Session(engine) as session:
        create_admin_user(session, args.email, args.password)


if __name__ == "__main__":
    main()
