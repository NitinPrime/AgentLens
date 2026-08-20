# Contributing to AgentLens

Thanks for your interest in contributing.

## Development setup

1. Fork and clone the repository.
2. Copy `.env.example` to `.env` and set `JWT_SECRET_KEY`
   (`.\scripts\generate-secret.ps1` prints one).
3. Start the backing services and the API.

With Docker:

```bash
docker compose up postgres redis api -d
```

Without Docker (Windows or anywhere Postgres and Redis are inconvenient), set
these in `.env` and the API will use a local SQLite file and an in-process token
store:

```
DATABASE_URL=sqlite+aiosqlite:///./agentlens.db
REDIS_URL=memory://
```

```powershell
.\scripts\dev.ps1        # starts the API and the web app together
```

4. Seed a workspace so the dashboard has something to show:

```powershell
.\apps\api\.venv\Scripts\python.exe scripts\seed_demo.py
```

PowerShell does not accept `&&`. Chain with `;` or use separate lines.

## Code style

- **Python**: type hints on public functions, `from __future__ import annotations`
  at the top of new modules, services own the business logic and routers stay thin.
- **TypeScript**: ESLint must pass with no warnings. Server state goes through
  TanStack Query, not `useEffect`.
- **Comments** explain intent, constraints, or a trade-off. Skip anything that just
  restates the code.
- Keep changes focused. Add the migration when you add a model.

## Testing

Run all three before opening a pull request — CI runs exactly these:

```bash
cd apps/api && pytest                              # 72 tests
cd packages/python-sdk && pytest                   # 16 tests, no server needed
cd apps/web && npm run lint && npm run build
```

The backend suite pins its own SQLite database and in-process token store, so it
needs neither Postgres, Redis, nor a `.env`. Keep it that way: if a new test needs
configuration, set it in `apps/api/tests/conftest.py` rather than assuming a local
`.env`.

## Adding a database model

1. Define it in `apps/api/app/models/` and export it from `__init__.py`.
2. Add an Alembic migration in `apps/api/alembic/versions/`, numbered in sequence.
   `tests/test_migrations.py` runs the chain and diffs it against the models, so a
   missing or drifting migration fails the suite. Keep server defaults portable
   (`sa.text("CURRENT_TIMESTAMP")`, `sa.true()`) — PostgreSQL-only spellings such
   as `now()` break the SQLite run.
3. Carry `project_id` on any row that belongs to a project. Every query filters by
   tenant directly instead of joining up the tree, which is what keeps cross-tenant
   leaks structurally hard.
4. Add a test that a second organization gets a `404`, not a `403`.

## Adding an evaluator

Register it in `apps/api/app/core/evaluators.py` with an `EvaluatorSpec` and a
scoring function, and add a case to `apps/api/tests/test_evaluator_engine.py`. If
it can only score subjects that have a reference answer, say so through
`requires_expected_output` (or `needs_expected_output` when it depends on the
config) so runs over raw traces skip it instead of reporting a false failure.

## Pull requests

- Describe what changed and why.
- Include the test plan you actually ran.
- Update the relevant file in `docs/` in the same pull request.
