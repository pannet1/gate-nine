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
./install.sh
# Fill RACHIS_USERNAME and RACHIS_PASSWORD in .env locally.
./run.sh
```

After cloning, `./install.sh` performs the complete setup: it installs the
project's Python 3.12 runtime, runs `uv sync`, installs the Chromium browser,
and creates `.env` if it does not already exist. The project is pinned to
Python 3.12; `uv.lock` records the resolved package versions.

`./run.sh` is the single command for starting the FastAPI application. Extra
Uvicorn arguments can be passed through, for example `./run.sh --reload`.

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

