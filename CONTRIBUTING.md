# Contributing to nw-migrate

Thanks for your interest in contributing! This guide covers how to set up the
project locally and submit changes.

## Development setup

nw-migrate uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
git clone https://github.com/jannik-cas/nw-migrate.git
cd nw-migrate
uv sync
```

This creates a virtualenv in `.venv/` and installs all dependencies including
dev tools (pytest, ruff, pytest-cov).

## Running tests

```bash
uv run pytest tests/ -q
```

With coverage (must stay at 100%):

```bash
uv run pytest tests/ --cov=nw_migrate --cov-report=term-missing --cov-fail-under=100
```

## Linting and formatting

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

CI runs both checks — formatting must match `ruff format` output exactly.

## Adding a new conversion rule

1. Add a `Rule(...)` entry in `src/nw_migrate/rules.py` under the appropriate
   difficulty section (EASY, MEDIUM, or HARD).
2. If the rule needs argument transformations, add `ArgTransform` entries.
3. Add tests in `tests/test_transformer.py` — at minimum a basic conversion test.
4. Run `uv run pytest tests/ --cov=nw_migrate --cov-fail-under=100` to verify
   coverage stays at 100%.

## Submitting changes

1. Fork the repo and create a feature branch from `main`.
2. Make your changes with tests.
3. Ensure `ruff check`, `ruff format --check`, and `pytest --cov-fail-under=100` all pass.
4. Open a pull request against `main`.

## Code style

- Follow existing patterns — the codebase is small, consistency matters.
- All functions and classes need docstrings.
- No print statements in library code.
- Type annotations everywhere.
