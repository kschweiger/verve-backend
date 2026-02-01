import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, col, or_, select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_422_UNPROCESSABLE_CONTENT,
)

from verve_backend import crud
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.core.date_utils import (
    get_all_dates_in_month,
    get_week_numbers_between_dates,
)
from verve_backend.enums import GoalType, TemporalType
from verve_backend.goal import update_goal_state
from verve_backend.models import Goal, GoalCreate, GoalPublic, GoalsPublic, ListResponse
from verve_backend.result import Err, ErrorType, Ok

router = APIRouter(prefix="/goal", tags=[Tag.GOAL])


def get_public_goal(goal: Goal) -> GoalPublic:
    progress = goal.current / goal.target
    reached = False
    if progress >= 1.0:
        reached = True

    return GoalPublic.model_validate(
        goal, update={"reached": reached, "progress": progress}
    )


@router.get("/", response_model=GoalsPublic)
def get_goals(
    user_session: UserSession,
    year: Annotated[int, Query(ge=2000, default_factory=lambda: datetime.now().year)],
    month: Annotated[int | None, Query(ge=1, lt=13)] = None,
    week: Annotated[int | None, Query(ge=1, lt=54)] = None,
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    if week is not None and month is not None:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot filter by both month and week simultaneously.",
        )

    stmt = select(Goal).where(Goal.year == year)
    if month:
        stmt = stmt.where(or_(Goal.month == month, col(Goal.month).is_(None)))
    if week:
        stmt = stmt.where(Goal.week == week)

    _data = session.exec(stmt).all()
    data = []
    for goal in _data:
        goal = update_goal_state(session=session, user_id=user_id, goal=goal)

        progress = goal.current / goal.target
        reached = progress >= 1

        data.append(
            GoalPublic.model_validate(
                goal, update={"reached": reached, "progress": progress}
            )
        )
    return GoalsPublic(
        data=data,
        count=len(data),
    )


def _add_single_goal(user_id: str, session: Session, data: GoalCreate) -> GoalPublic:
    result = crud.create_goal(session=session, goal=data, user_id=user_id)
    match result:
        case Ok(goal):
            return get_public_goal(goal)
        case Err((msg, err_type)):
            if err_type == ErrorType.VALIDATION:
                code = HTTP_422_UNPROCESSABLE_CONTENT
            else:
                code = HTTP_400_BAD_REQUEST

            raise HTTPException(
                status_code=code,
                detail=msg,
            )


@router.put("/", response_model=ListResponse[GoalPublic])
def add_goal(user_session: UserSession, data: GoalCreate) -> Any:
    user_id, session = user_session

    if data.temporal_type == TemporalType.MONTHLY and data.month is None:
        _goals = []
        for i in range(1, 13):
            _data = data.model_copy()
            _data.month = i
            _goals.append(_add_single_goal(user_id, session, _data))
        return ListResponse(data=_goals)
    elif data.temporal_type == TemporalType.WEEKLY and data.week is None:
        _goals = []
        if data.month is None:
            week_numbers = list(
                range(1, datetime(data.year, 12, 28).isocalendar()[1] + 1)
            )
        else:
            _dates = get_all_dates_in_month(data.year, data.month)
            week_numbers = get_week_numbers_between_dates(_dates[0], _dates[-1])
        for week_num in week_numbers:
            _data = data.model_copy()
            _data.month = None
            _data.week = week_num
            _goals.append(_add_single_goal(user_id, session, _data))
        return ListResponse(data=_goals)
    else:
        return ListResponse(data=[_add_single_goal(user_id, session, data)])


@router.delete(
    "/",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_goal(
    user_session: UserSession,
    id: uuid.UUID | str,
) -> None:
    _, session = user_session
    goal = session.get(Goal, id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    session.delete(goal)
    session.commit()


@router.get("/{id}/modify_amount", response_model=GoalPublic)
def modify_manual_goal(
    user_session: UserSession, id: uuid.UUID, increase: bool, amount: int
) -> Any:
    _, session = user_session
    goal = session.get(Goal, id)
    if not goal:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Goal not found")
    if goal.type != GoalType.MANUAL:
        raise HTTPException(
            status_code=HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"Route is only allowed for manual goals but {id} is "
            "of type {goal.type}",
        )

    update_amout = goal.current
    if increase:
        update_amout += amount
    else:
        update_amout -= amount

    goal.current = 0 if update_amout < 0 else update_amout
    session.add(goal)
    session.commit()
    session.refresh(goal)

    return get_public_goal(goal)


@router.post("/{id}/update", response_model=GoalPublic)
def update_goal(
    user_session: UserSession,
    id: uuid.UUID,
    attribute: Literal["name", "description", "target"],
    value: str,
) -> Any:
    if attribute not in ["name", "description", "target"]:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Attribute {attribute} is not allowed to be updated",
        )
    if attribute == "target":
        try:
            float(value)
        except ValueError:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="New value must be a number if *target* is passed "
                f"as attribute. Got: {value}",
            )

    _, session = user_session
    goal = session.get(Goal, id)
    if not goal:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Goal not found")

    if attribute == "name":
        goal.name = value
    elif attribute == "description":
        goal.description = value
    else:
        goal.target = float(value)

    session.add(goal)
    session.commit()
    session.refresh(goal)

    return get_public_goal(goal)
