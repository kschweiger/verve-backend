# AGENTS.md

## Purpose

This repository is a FastAPI backend for Verve Outdoors. Keep this file short: it is a map of the repository and its working rules, not a full manual.

## Start Here

1. Read `README.md` for services, database setup, and environment variables.
2. Read `pyproject.toml` for dependencies, Ruff rules, and Python version.
3. Inspect the relevant module under `verve_backend/` and its tests under `tests/`.
4. For schema changes, read the existing revisions in `alembic/` before creating a new one.

## Navigation Map

- API routes: `verve_backend/api/routes/`
- Core configuration, database, and security: `verve_backend/core/`
- Models, schemas, transformations, and SQL: `verve_backend/models.py`, `schema/`, `queries/`
- Tests and fixtures: `tests/`, `tests/routes/`, `tests/resources/`
- Operational scripts and CLI commands: `scripts/`, `verve_backend/cli/`

## Route Conventions

- Use underscores in route paths, not hyphens (e.g., `track/get_track`).

## Working Preferences

- For Python test work, always read and follow the `python-test-design` skill before editing or reviewing tests.
- When a query becomes large or complicated to express with SQLModel, put it in a .sql file under `verve_backend/queries/` and load it from the application.

## Backend Invariants

- Use Python 3.14 and the locked `uv.lock` dependencies.
- Keep route-specific behavior in the relevant route/module; put shared behavior in `core/` or common utilities.
- Add database changes as new Alembic revisions; preserve row-level security policies.
- Never commit secrets, local `.env` values, generated coverage output, or temporary data.
- Follow the existing Conventional Commit style, such as `feat(equipment): add patch and delete routes`.

## Test Conventions

- The test suite requires the configured PostgreSQL/PostGIS database, Redis, and S3-compatible object store to be available. Database-related tests can use the test database directly; mocking is usually unnecessary.

## Validation Loop

- Install dependencies with `uv sync --locked --group test --no-dev`.
- For changed Python files, run `uv run ruff check <files>`, `uv run ruff format --check <files>`, and `uv run ty check --output-format concise <files>`.
- Run `uv run pytest`.
- Use `make test-cov` when coverage output is needed.
- Add or update focused tests for behavior changes, especially API and RLS changes.
