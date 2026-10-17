# Rachis black-box testing harness

This project supports human-supervised functional testing of the remote
`rachis.co.in` application. It does not require access to Rachis source code,
internal APIs, or its database.

## Safety rules

- Never commit `.env`, tenant credentials, customer data, or unredacted evidence.
- The runner may open and inspect the tenant, but must not create or post a
  voucher unless a human has approved the specific test case and test data.
- A human owns the final PASS/FAIL decision.

## Quick start

```bash
uv python install 3.12
uv sync
uv run playwright install chromium
cp .env.example .env
# Fill RACHIS_USERNAME and RACHIS_PASSWORD locally.
uv run uvicorn app.main:app --reload
```

Use `uv run ...` for all project commands. The project is pinned to Python
3.12; `uv.lock` records the resolved package versions.

Open `http://127.0.0.1:8000`. The first version exposes health, test-case,
and append-only event-log endpoints. The browser runner is intentionally
separate so future models can add voucher-specific behaviour without mixing
them into the dashboard.

## Layout

- `app/` — FastAPI service, configuration, event log, and browser runner
- `test-cases/` — one folder per human-approved test case
- `docs/` — architecture and contribution boundaries
- `data/` — local runtime state; ignored by Git
- Run-local evidence — each case keeps its current `screenshot.png`; image and
  PDF evidence remains untracked.

See `docs/ARCHITECTURE.md` before adding new modules.

Run the dependency-free smoke test with:

```bash
uv run --no-sync python -m unittest discover -s app_tests -v
```

