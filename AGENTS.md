# Repository Guidelines

## Project Structure & Module Organization

- `backend/app/`: FastAPI application, including `auth/`, `mail/`, and `db/`; Alembic migrations live in `db/migrations/`.
- `backend/app/engine/`: deterministic financial calculations, independent of other application modules, file I/O, databases, networks, and AI. Callers pass configuration from `backend/app/templates/` YAML files.
- `backend/tests/`: pytest suites organized by subsystem.
- `frontend/src/`: Vue pages, components, layouts, stores, API clients, and styles. Assets live in `frontend/public/`; tests sit beside source files.
- `docs/`: product, calculation, architecture, and visual specifications. `deploy/nginx/` and Compose files define deployment.

## Build, Test, and Development Commands

From the repository root:

- Copy `.env.example` to `.env` and configure credentials.
- `docker compose up -d --build`: build and start PostgreSQL, API, and website at `http://localhost:8080`.
- `docker compose up -d db`: start PostgreSQL for tests.

From `backend/` (Python 3.12, managed with uv):

- `uv sync`: install dependencies.
- `uv run pytest`: run tests.
- `uv run ruff check .` / `uv run ruff format .`: lint / format Python.

From `frontend/`:

- `nvm use && npm ci`: select Node 22 and install locked dependencies.
- `npm run dev`: serve at `http://localhost:5173`; proxies `/api` to the running Docker backend.
- `npm test`: run Vitest.
- `npm run typecheck` / `npm run build`: check types / typecheck and build production assets.
- `npm run gen:api`: regenerate `src/api/schema.d.ts` after API changes; requires the backend.

## Coding Style & Naming Conventions

Use four-space Python indentation, type annotations, and snake_case names; Ruff uses a 100-character line length. Frontend conventions: two-space indentation, single quotes, no semicolons, PascalCase components, `useX` composables, and Vue `<script setup lang="ts">`. No frontend formatter or linter is configured. Regenerate generated declarations instead of editing manually.

## Testing Guidelines

Name tests `test_*.py` (backend) and `*.test.ts` (frontend). Cover changed behavior and edge cases; no coverage threshold is configured. API tests use a separate `_test` database and in-memory mail; they skip without PostgreSQL. `TEST_DATABASE_URL` must reference a disposable database: fixtures rebuild tables.

## Commit & Pull Request Guidelines

History uses Chinese `范围：说明` subjects with bullet bodies. Keep commits focused. PRs should describe changes, link relevant issues, report checks and skipped tests, and include mobile/desktop screenshots for UI changes.

## Configuration & Schema Changes

Keep secrets in ignored `.env`; document new settings in `.env.example`. After model changes, run `uv run alembic revision --autogenerate -m "description"` from `backend/` and review the migration. Containers apply migrations at startup.
