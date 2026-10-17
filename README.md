# Gate Nine

Gate Nine is a human-supervised black-box testing harness for the remote
`rachis.co.in` application. It uses Playwright against the visible web UI and
does not require access to Rachis source code, internal APIs, or its database.

The current workflow and design decisions are maintained in the repository
root [`index.html`](index.html). The refactor backlog is in
[`docs/REFACTOR.md`](docs/REFACTOR.md).

## Safety rules

- Never commit `.env`, tenant credentials, customer data, or unredacted
  evidence.
- Do not create or post a voucher unless a human has approved the specific
  case and test data.
- A human owns the final PASS/FAIL decision.
- The browser remains visible so people can watch operations and intervene.

## Install after cloning

Run one command from the repository root:

```bash
./install.sh
```

The installer installs Python 3.12 through `uv`, runs `uv sync`, installs the
Playwright Chromium browser, and creates `.env` from `.env.example` if `.env`
does not exist. `uv` must already be installed; see
<https://docs.astral.sh/uv/getting-started/installation/> if needed.

After installation, fill in `RACHIS_USERNAME` and `RACHIS_PASSWORD` in the
local `.env` file. It is ignored by Git.

## Start the application

Run the FastAPI service with one command:

```bash
./run.sh
```

It starts the service at <http://127.0.0.1:8000>. Additional Uvicorn
arguments are passed through, for example `./run.sh --reload`.

The current API is intentionally small:

- `GET /health` — service health check;
- `GET /api/events` — current JSONL events as a JSON array;
- `POST /api/events` — append an event; and
- `GET /` — placeholder dashboard.

The rich dashboard, evidence browser, and live web event stream are not yet
implemented.

## Run a browser plan

The FastAPI service and browser runner are separate processes. After the
service is running, execute a plan with:

```bash
uv run python -m app.driver
```

The target main loop reads the highest-numbered run under `test-cases/`, parses
its `test.html` plan, opens a visible Chromium window, and appends activity to
the root `events.jsonl` while the run is active, then archives it inside the
completed run folder. The current implementation is being brought into this
workflow; the details are tracked in [`docs/REFACTOR.md`](docs/REFACTOR.md).

To follow events in a second terminal:

```bash
uv run python -m app.watch
```

After a run has archived its log, inspect the highest-numbered run for Step D:

```bash
uv run python -m app.diagnose
```

This is a read-only diagnosis gate. It reports missing plans, missing archived
logs, unhandled actions, and failed steps. It does not decide that a product
bug exists; failures require human-in-loop browser review before escalation.

`app.driver` is the sole browser-plan executor. The FastAPI service remains a
separate process so it can expose the event log while the visible browser run
is active.

## Repository layout

- `app/` — FastAPI service, configuration, event logging, browser runner, and
  canonical voucher cases;
- `app/vouchers/` — case-local `test-case.html` instructions;
- `test-cases/` — numbered run folders containing briefs, plans, and links to
  the cases under test;
- `events.jsonl` — temporary root event log, archived into the completed run;
- `docs/` — architecture, design, repository guidance, and refactor notes;
- `install.sh` — one-step local setup; and
- `run.sh` — one-step FastAPI startup.

Run-local evidence belongs inside the relevant case folder as `screenshot.png`.
There is no `artifacts/` output directory.

## Tests

After installation, run the test suite with:

```bash
uv run python -m unittest discover -s app_tests -v
```

The tests cover plan parsing, run discovery, route mapping, and event logging.
Live tenant behavior requires credentials and a visible
browser, so it is not part of the local unit-test suite.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before adding modules or
changing the run lifecycle.

