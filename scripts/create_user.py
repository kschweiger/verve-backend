from sqlmodel import Session

from verve_backend.core.db import get_engine
from verve_backend.crud import create_user
from verve_backend.models import UserCreate


def run(username: str, password: str, email: str, full_name: str | None) -> None:
    engine = get_engine()
    with Session(engine) as session:
        try:
            create_user(
                session=session,
                user_create=UserCreate(
                    name=username,
                    password=password,
                    email=email,
                    full_name=full_name,
                ),
            )
        except Exception as e:
            print("========= Encountered Error =========")
            print(e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser("Create User")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("email")
    parser.add_argument("-f", "--full-name", default=None)
    args = parser.parse_args()

    run(args.username, args.password, args.email, args.full_name)
