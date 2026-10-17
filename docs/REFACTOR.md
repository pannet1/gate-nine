# Refactor Review

This document records the architecture review and the gaps to address one at a
time. It is a backlog and decision aid, not an instruction to implement every
item immediately.

The current shape of the application and its intentional design decisions are
documented in the repository root [`index.html`](../index.html). That document
remains the reference for the current workflow, human-in-the-loop model,
visible-browser requirement, run folders, logging, and safety constraints.

## Current architecture

Gate Nine is a local, human-supervised black-box testing harness for Rachis.
Rachis remains an external system; this repository owns test definitions,
browser actions, evidence, and activity reporting.

The current components are:

- `test-cases/` — numbered run folders containing briefs, generated plans, and
  links to canonical cases.
- `app/vouchers/` — canonical case instructions, currently stored as
  `test-case.html` files.
- `app/driver.py` — the intended Playwright plan executor.
- `app/events.py` — append-only JSONL event logging.
- `app/main.py` — minimal FastAPI health and event API plus a placeholder
  dashboard.
- `app/watch.py` — terminal event-log follower.
- `app/loop.py` — an older/manual browser-opening path.
- `app/runner.py` — a separate login and screenshot helper.

## Intended workflow

The refactor must support this workflow exactly.

### Step A — Human creates the run

1. A human writes the brief.
2. A human creates the next numbered run folder under `test-cases/`.

The main loop must not invent a run folder or run without a human-created run.

### Step B — AI prepares the plan and cases

The AI checks the highest-numbered run folder.

- If `test.html` already exists, preserve it and continue to Step C.
- If `test.html` does not exist, the AI reads the brief and generates it.
- The AI checks whether every voucher referenced by the plan has a canonical
  case document under `app/vouchers/`.
- If a voucher case is missing, the AI enters a human-in-the-loop browser
  training flow to create the new voucher case document before continuing.

The human remains responsible for correcting the brief, trained method, and
test data. The plan carries execution order; the voucher case owns the method.

### Step C — Main loop executes visibly

The main loop then:

1. verifies that `test.html` exists in the highest-numbered run folder;
2. empties or initializes the root JSONL event log before the run;
3. opens a visible browser;
4. executes the plan until all tests succeed or a test fails; and
5. moves the completed root JSONL log into that run folder.

The target root log is a temporary per-run file, for example:

```text
events.jsonl                  # exists only while the run is active
test-cases/001/events.jsonl   # archived after the run ends
```

The browser must remain visible throughout the run. A successful run and a
failed run both archive their log. The archive operation must also happen when
the runner is interrupted or crashes, where the operating environment permits
cleanup.

### Step D — AI diagnoses the completed run

After the run ends, the AI checks the highest-numbered run folder.

- If both `test.html` and the archived JSONL log exist, the AI uses them to
  identify and repair harness errors through a human-in-the-loop Playwright
  session.
- If the evidence indicates a genuine Rachis product bug rather than a harness
  or test-data problem, the AI informs the developer.

The AI must not silently classify a product bug as a harness failure, and it
must not silently classify a harness limitation as a product failure.

## Refactor backlog

### 1. Choose one canonical runner

There are currently three partially overlapping execution paths:

- `app.driver` executes plans.
- `app.loop` opens a browser and waits for manual closure.
- `app.runner` provides a separate login/screenshot helper.

This makes the operational entry point unclear and allows documentation and
implementation to drift apart.

Decision needed: make `app.driver` the sole runner, then retire or clearly
isolate `loop.py` and `runner.py`.

### 2. Decide how unsupported actions affect the run

Only `sign-in` and `open-new` are implemented. These actions currently have no
handlers:

- `add-line`
- line and header discounts
- tax verification
- draft/post/correct
- print

The current design explicitly records these as `no-handler` and continues.
That is useful for exposing all harness gaps in one pass, but it also means a
run can finish while most of its test was never performed.

Decision needed: retain the current continue-and-report behavior, or make an
unsupported action stop the run. Under either choice, a human verdict must not
be available as `passed` when required actions were skipped.

Relevant code: [`app/driver.py`](../app/driver.py), especially `_perform()` and
the run summary.

### 3. Enforce human approval

The design requires explicit human approval, but the application has no
approval record or execution gate. The presence of `test.html` is currently
enough to run a plan.

The approval model should record at least:

- approver identity
- approval timestamp
- approved test data
- approved plan identity or hash
- approval status

Execution should refuse to start without a valid approval record.

### 4. Implement the human-owned PASS/FAIL lifecycle

The implementation records technical outcomes such as `ok`, `failed`, and
`no-handler`, but it does not persist the final human verdict described by the
design.

Separate these concepts:

1. execution result
2. harness capability or skipped-action status
3. human PASS/FAIL verdict

Only the human verdict should transition a run to `passed`.

### 5. Bring the dashboard up to the documented boundary

`app/main.py` currently exposes health, a complete event-log snapshot, an
unrestricted event append endpoint, and a placeholder HTML page. It does not
yet expose the documented run status, case documents, plans, run-local
screenshots, or rich interface.

The intended dashboard should remain read-only for execution state and should
provide safe views of:

- current run and lifecycle state
- brief and generated plan
- per-step outcomes
- current evidence
- event stream
- human verdict

### 6. Define remote visibility and access control

The service currently binds to `127.0.0.1`, so remote developers cannot see it
without an external tunnel or proxy. The event API also has no authentication
or authorization.

Before remote exposure, choose and document the deployment boundary:

- SSH tunnel
- private network
- authenticated reverse proxy

The current arbitrary event-write endpoint must not be exposed directly.

### 7. Implement evidence capture and redaction

The design requires screenshots after meaningful state changes, redaction before
sharing, and one current reference screenshot per test. The main driver does
not currently implement that workflow. Screenshot behavior exists only in the
separate `runner.py` helper.

Evidence should be associated with a run, step, and case, with an explicit
replacement policy and a redaction boundary.

### 8. Define a structured action contract

The plan is intentionally order-only: it carries action names and case folders,
while the detailed instructions remain in the canonical case document. The
driver does not currently parse structured inputs, expected values, assertions,
or evidence requirements from that case document.

Before adding many handlers, define a versioned machine-readable action schema
inside each case document or in a linked case-local manifest. Do not duplicate
the method in `test.html`; preserve the rule that the plan carries order and
the case owns the method. For example:

```json
{
  "action": "add-line",
  "inputs": {"product": "Hamam", "quantity": 2},
  "assertions": ["line total equals ..."],
  "evidence": "after-action"
}
```

The schema should preserve the human-readable case document as the source of
meaning while giving the runner an explicit, testable contract.

### 9. Reconcile repository and documentation drift

Known inconsistencies include:

- documentation using “Markdown cases” imprecisely; Markdown is the format for
  run briefs, while canonical case methods are HTML;
- `debit-note` referenced by the plan and design but absent from
  `app/vouchers/`;
- README claims for test-case endpoints that do not exist;
- `docs/AGENTS.md` describing a documentation-only repository;
- `index.html`, `docs/ARCHITECTURE.md`, and implementation describing
  different maturity levels.

Resolve these as a documentation pass before adding more architecture.

### 10. Harden runtime operations

The event log currently has no locking, rotation, pagination, or malformed-line
recovery. Concurrent writers may interleave, and one corrupt JSONL line can
break reads.

The runner also has no lock preventing two processes from executing the same
latest run simultaneously.

Add these safeguards only after the canonical runner and lifecycle model are
settled.

### 11. Protect sensitive data in logs and run-local evidence

Credentials are loaded from environment variables, but there is no systematic
redaction policy for logs, URLs, screenshots, result data, or dashboard views.
User identifiers already appear in some event details.

Define what is safe to log, redact sensitive values centrally, and ensure
run-local evidence cannot be served accidentally through a public endpoint.

### 12. Establish a reliable verification baseline

The pure planner and event tests pass in the current environment. Driver and
loop tests cannot import when Playwright is unavailable, and the documented
`uv` test command could not acquire its cache in the reviewed environment.

The project needs a repeatable verification baseline including:

- dependency and browser preflight checks
- unit tests without requiring a live tenant
- mocked Playwright action tests
- a clearly separated live-tenant smoke test
- CI configuration, if remote execution is expected
- linting and type checking where useful

## Suggested order of work

Work through the backlog in this order:

1. Choose one canonical runner.
2. Define run state, approval, and human verdicts.
3. Decide and enforce the unsupported-action policy.
4. Define the structured action contract.
5. Implement evidence capture and redaction.
6. Reconcile documentation and repository shape.
7. Add the dashboard and event stream.
8. Add remote access controls.
9. Harden logging and concurrency.
10. Expand handler coverage and verification.

Each item should be reviewed and completed independently before moving to the
next one.
