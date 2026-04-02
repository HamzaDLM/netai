# Backend Test Scaffold

This folder is the starting point for backend tests.

## Layout

- `tools/`: unit tests focused on tool behavior (input filtering, normalization, output schema, error paths).

## Conventions

- Keep tests deterministic and local-first.
- Prefer fake/static tool modules for unit tests.
- Add integration tests separately when external APIs are required.
