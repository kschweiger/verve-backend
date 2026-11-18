"""Read and validate the bundled exercise catalog without database access."""

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from verve_backend.models import ExerciseMuscleRole

Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")]
Nonempty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class CatalogInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UpstreamInput(CatalogInputModel):
    source: Nonempty
    repository: AnyUrl
    revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    license: Nonempty


class ExerciseInput(CatalogInputModel):
    code: Code
    is_active: bool = True
    primary_muscles: list[Code]
    secondary_muscles: list[Code]
    upstream_id: Nonempty | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_upstream_id(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and "upstream_id" in value
            and value["upstream_id"] is None
        ):
            raise ValueError("upstream_id must be a string when supplied")
        return value


class GroupInput(CatalogInputModel):
    code: Code
    muscles: list[Code]


class CatalogInput(CatalogInputModel):
    schema_hint: str | None = Field(default=None, alias="$schema")
    schema_version: Literal[1]
    source: Code
    upstream: UpstreamInput | None = None
    muscles: list[Code]
    muscle_groups: list[GroupInput]
    exercises: list[ExerciseInput]

    @field_validator("schema_version", mode="before")
    @classmethod
    def reject_boolean_version(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("schema_version must be 1")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_metadata(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("$schema", "upstream"):
                if key in value and value[key] is None:
                    raise ValueError(f"{key} cannot be null")
        return value


@dataclass(frozen=True)
class CatalogExercise:
    code: str
    is_active: bool
    muscles: dict[str, ExerciseMuscleRole]


@dataclass(frozen=True)
class CatalogGroup:
    code: str
    muscles: tuple[str, ...]


@dataclass(frozen=True)
class CatalogSnapshot:
    catalog_code: str
    content_hash: str
    muscles: tuple[str, ...]
    groups: tuple[CatalogGroup, ...]
    exercises: tuple[CatalogExercise, ...]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def catalog_revision(document: dict[str, Any]) -> str:
    data = {key: value for key, value in document.items() if key != "$schema"}
    canonical = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_catalog(input_path: Path | None = None) -> CatalogSnapshot:
    resources = files("verve_backend").joinpath("data")
    raw = (
        input_path.read_text(encoding="utf-8")
        if input_path is not None
        else resources.joinpath("exercise_catalog.json").read_text(encoding="utf-8")
    )
    document = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )
    parsed = CatalogInput.model_validate(document)
    if any(item.upstream_id for item in parsed.exercises) and parsed.upstream is None:
        raise ValueError("upstream is required when an exercise has upstream_id")
    # Use the validated shape below, but hash the original input without defaults.
    validated = parsed.model_dump(by_alias=True, exclude_none=True)
    muscles_list = validated["muscles"]
    if len(muscles_list) != len(set(muscles_list)):
        raise ValueError("Duplicate muscle codes")
    muscles = set(muscles_list)
    for section in ("exercises", "muscle_groups"):
        codes = set()
        for item in validated[section]:
            code = item["code"]
            if code in codes:
                raise ValueError(f"Duplicate {section} code: {code}")
            codes.add(code)
            if section == "exercises":
                primary, secondary = item["primary_muscles"], item["secondary_muscles"]
                if len(primary) != len(set(primary)) or len(secondary) != len(
                    set(secondary)
                ):
                    raise ValueError(f"Duplicate muscle assignment: {code}")
                if set(primary) & set(secondary):
                    raise ValueError(f"Muscle has both roles: {code}")
                references = set(primary) | set(secondary)
            else:
                references = set(item["muscles"])
                if len(references) != len(item["muscles"]):
                    raise ValueError(f"Duplicate group member: {code}")
            if unknown := references - muscles:
                raise ValueError(f"Unknown muscles for {code}: {sorted(unknown)}")
    return CatalogSnapshot(
        catalog_code=parsed.source,
        content_hash=catalog_revision(document),
        muscles=tuple(parsed.muscles),
        groups=tuple(
            CatalogGroup(item["code"], tuple(item["muscles"]))
            for item in validated["muscle_groups"]
        ),
        exercises=tuple(
            CatalogExercise(
                code=item["code"],
                is_active=item.get("is_active", True),
                muscles={
                    **dict.fromkeys(
                        item["primary_muscles"], ExerciseMuscleRole.PRIMARY
                    ),
                    **dict.fromkeys(
                        item["secondary_muscles"], ExerciseMuscleRole.SECONDARY
                    ),
                },
            )
            for item in validated["exercises"]
        ),
    )
