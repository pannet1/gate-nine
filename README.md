# Gate Nine

Gate Nine is a human-supervised black-box testing harness for the remote
`rachis.co.in` application. It uses Playwright against the visible web UI and
does not require access to Rachis source code, internal APIs, or its database.

The current workflow and design decisions are maintained in the repository
root [`index.html`](index.html).

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

## Run a browser plan

Gate Nine is a pure CLI tool driven by Playwright and local JSONL logging with no background web server required.

Execute a plan with:

```bash
uv run python -m app.driver
```

The target main loop reads the highest-numbered run under `test-cases/`, parses
its `test.html` plan, opens a visible Chromium window, and POSTs every operation
as an event to the remote FastAPI endpoint configured in `events_url` over HTTP
Basic Auth. Nothing is written to a local event log. The workflow is maintained
in [`index.html`](index.html).

Configure the remote endpoint in `.env`:

```
EVENTS_URL=https://events.example/ingest
EVENTS_USERNAME=alice
EVENTS_PASSWORD=secret
```

When `EVENTS_URL` is empty, events are not recorded anywhere.

To follow events in a second terminal, poll the remote endpoint (or your
httpd-protected log viewer) while the run is active.

After a run completes, inspect the highest-numbered run for Step D:

```bash
uv run python -m app.diagnose
```

This is a read-only diagnosis gate. It reports missing plans and unhandled or
failed steps. It does not decide that a product bug exists; failures require
human-in-loop browser review before escalation. During a run, Playwright console
errors, uncaught page errors, failed network requests, and page crashes are also
sent as events with the active step context when available. Request query strings
and fragments are omitted.

## Repository layout

- `app/` — configuration, event logging, browser runner, diagnosis, and
  canonical voucher cases;
- `app/vouchers/` — case-local `test-case.html` instructions;
- `test-cases/` — numbered run folders containing briefs, plans, and links to
  the cases under test;
- `docs/` — design and repository guidance; and
- `install.sh` — one-step local setup.

Run-local evidence belongs inside the relevant case folder as `screenshot.png`.
There is no `artifacts/` output directory and no local `events.jsonl`.

## Tests

After installation, run the test suite with:

```bash
uv run python -m unittest discover -s app_tests -v
```

The tests cover plan parsing, run discovery, route mapping, and event logging.
Live tenant behavior requires credentials and a visible
browser, so it is not part of the local unit-test suite.

See [`index.html`](index.html) before adding modules or
changing the run lifecycle.

