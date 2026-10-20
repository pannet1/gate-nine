# Gate Nine

A human-supervised, black-box testing harness for the remote `rachis.co.in`
application. It drives Playwright against the visible web UI and needs no
access to Rachis source code, internal APIs, or its database.

The design this implements is written down in [`index.html`](index.html).

## What it does

A human writes a brief. A human drives the browser once while Playwright
`codegen` records every selector from the live DOM. From then on, one command
replays those recordings in a visible browser so a person can watch data being
entered and stop it if it looks wrong.

The brief says **what** to test. The recording says **how**.

## Install

```bash
./install.sh
```

Installs Python 3.15 via `uv`, runs `uv sync`, installs Playwright's Chromium,
and creates `.env` from `.env.example` if it does not exist. `uv` must already
be installed: <https://docs.astral.sh/uv/getting-started/installation/>

Then fill in `HEADLESS`, `SLOW_MO_MS`, `EVENTS_URL`, and `EVENTS_PASSWORD` in
`.env`. It is ignored by Git. Leave `EVENTS_URL` empty and events are not
recorded anywhere.

## Run

```bash
uv run python -m app.main          # the highest-numbered run under test-cases/
uv run python -m app.main 001      # a specific run
```

That is the whole interface. It walks the loop and stops the moment a human is
needed:

| Step | What happens |
|---|---|
| Find | the highest-numbered folder under `test-cases/`, or the one you named |
| Require | `cases.yml`. Without it, it exits `2` having touched nothing |
| Tidy | move loose recordings, fix drifted names, link into the run, rewrite `session.md` |
| Hand off | anything missing is the human's: prints the runnable command, exits `1`, runs no case |
| Replay | every case in `cases.yml`, one at a time, in a visible browser |

Exit codes: `0` every case completed, `1` handed off or a case failed, `2`
cannot run.

`STEP_DELAY` (default 3s) holds between cases, and `SLOW_MO_MS` (default 3000)
slows every click and fill so you can watch data entry before the next action
fires.

### Tidy on its own

```bash
uv run python -m app.tidy                # every case into the latest run
uv run python -m app.tidy sales-invoice 001
uv run python -m app.tidy --dry-run      # report without moving anything
```

## Record a case

Recording needs hands on a keyboard, so it is yours to do. First, save the
login once, per system:

```bash
uv run playwright codegen --save-storage=recordings/auth.json https://rachis.co.in/login/
```

Sign in, then close the window. From here every recording loads that state; no
recording ever contains a login of its own.

Then record a case. The URL is read from `url.txt`, never guessed:

```bash
uv run playwright codegen --load-storage=recordings/auth.json \
  -o recordings/sales-invoice/sales-invoice.py \
  "$(cat recordings/sales-invoice/url.txt)"
```

Drive the form yourself — pick a customer, fill the fields, **click submit**.
That last click is what makes it a test rather than an exploration. Then close
the picker so `codegen` writes the file.

The AI appends one line afterwards, immediately before the submit:

```python
page.screenshot(path="screenshot.png")
```

## Workspace layout

```
test-cases/
  002/
    Work Platform — Test Manual.md   the brief, any filename
    cases.yml                   a plain list, one case name per line
    session.md                  the work list
    sales-invoice -> ../../recordings/sales-invoice
  auth.json       -> ../recordings/auth.json
recordings/
  auth.json                      one login for the whole system
  sales-invoice/
    url.txt                      never guessed
    sales-invoice.py             the test
    screenshot.png               evidence
```

Recordings are canonical in `recordings/<case>/` and shared by every run; a
run folder holds one symlink per case. Re-record once and every run picks it
up. Nothing here is committed except the symlink.

`cases.yml` is a plain list:

```yaml
- sales-invoice
- good-receipt-note
```

It wins over anything inferred, and is never overwritten.

## Events

Every case fires its own event to `EVENTS_URL` over HTTP Basic Auth as it
completes, plus `run_start` and `run_result` for the pass. Nothing is written
to a local log. Set `EVENTS_URL` to empty and events are not recorded.

## Tests

```bash
uv run python -m pytest
```

135 tests over a real temporary tree and real symlinks. No browser is opened;
only step 5 of the loop is injected, so nothing reaches the network.

## Safety

- Never commit `.env`, tenant credentials, customer data, or unredacted
  evidence. `.gitignore` covers `.env`, `auth.json` and every image.
- Do not create or post a voucher unless a human has approved the specific
  case and its data.
- A human owns the final PASS/FAIL. The runner reports that a script threw; it
  never declares a product pass or fail.
- The browser stays visible so people can watch and intervene.
- No selector is ever written by the AI. Recordings come from a human driving
  the live DOM.

## Repository layout

- `app/main.py` — the loop
- `app/tidy/` — the workspace: cases, files, links, session, workspace, cli
- `app/config.py`, `app/events.py` — settings and the remote event POST
- `app/planner.py` — run and brief discovery
- `app/driver.py`, `app/diagnose.py` — superseded, see the open items in
  [`index.html`](index.html)
- `test-cases/` — numbered run folders
- `recordings/` — canonical cases
- `app_tests/` — the test suite