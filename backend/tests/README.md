# Backend Tests

Test suite is organized by scope:

- `tools/`: tool-focused tests.
- `unit/`: fast tests for the Agent, services, hooks, models, and endpoint helpers.
- `integration/`: API + persistence behavior using an isolated sqlite test DB.
- `evals/`: deterministic answer-quality and grounding checks.
- `factories/`: lightweight DB object factories used by tests.

## Running

From `backend/`:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run pytest tests/evals -q
uv run pytest tests -q
```
