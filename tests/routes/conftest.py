import pytest
from sqlmodel import Session, col, select

from verve_backend.models import Exercise


@pytest.fixture
def active_exercise_id(db: Session) -> str:
    query = select(Exercise.id).where(col(Exercise.is_active).is_(True)).limit(1)
    return str(db.exec(query).one())
