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
- `app/driver.py` — the sole Playwright plan executor.
- `app/events.py` — append-only JSONL event logging.
- `app/main.py` — minimal FastAPI health and event API plus a placeholder
  dashboard.
- `app/watch.py` — terminal event-log follower.

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

### 1. Canonical runner — complete

`app.driver` is the sole browser-plan executor. The competing `app.loop` and
`app.runner` modules were removed. FastAPI remains a separate service, and
`app.watch` remains a terminal log viewer rather than another runner.

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

### 3. Implement the run-log lifecycle — complete

The target workflow requires a temporary root JSONL log for the active run.
The main loop must:

1. identify the highest-numbered human-created run folder;
2. verify that `test.html` exists;
3. empty or create the root `events.jsonl`;
4. append all run events there;
5. archive it into `test-cases/<run_id>/events.jsonl` after success, failure,
   interruption, or crash cleanup where possible.

The implementation now uses the root `events.jsonl` and archives it into the
completed run folder. The remaining runtime-hardening concerns are tracked
below.

### 4. Bring the dashboard up to the documented boundary

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

### 5. Define remote visibility and access control

The service currently binds to `127.0.0.1`, so remote developers cannot see it
without an external tunnel or proxy. The event API also has no authentication
or authorization.

Before remote exposure, choose and document the deployment boundary:

- SSH tunnel
- private network
- authenticated reverse proxy

The current arbitrary event-write endpoint must not be exposed directly.

### 6. Implement missing-voucher training and evidence capture

When the AI finds a voucher referenced by a plan without a canonical case
document, it must enter a human-in-the-loop browser training flow and create
the case method before the main loop runs. This must remain distinct from
autonomous test execution.

The design requires screenshots after meaningful state changes, redaction before
sharing, and one current reference screenshot per test. The main driver does
not currently implement that workflow; it remains a later run-local evidence
item.

Evidence should be associated with a run, step, and case, with an explicit
replacement policy and a redaction boundary.

### 7. Define a structured action contract

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

### 8. Add post-run AI diagnosis and bug triage — gate complete

`app.diagnose` now inspects the highest-numbered run folder. When both
`test.html` and the archived JSONL log exist, it should use them to repair
harness, plan, or test-data errors through a human-in-the-loop Playwright
session. If the evidence points to a genuine Rachis defect, it must inform the
developer instead of silently changing the test.

The read-only evidence gate is implemented and tested. The actual browser
repair session remains case-specific and must be driven from a concrete
diagnosis; it is not an autonomous mutation step.

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

The pure planner and event tests pass when dependencies are available. Driver
and loop tests require Playwright and a correctly provisioned environment. A
previous `uv` cache failure was environment-specific and should not be treated
as an application design requirement.

The project needs a repeatable verification baseline including:

- dependency and browser preflight checks
- unit tests without requiring a live tenant
- mocked Playwright action tests
- a clearly separated live-tenant smoke test
- CI configuration, if remote execution is expected
- linting and type checking where useful

## Suggested order of work

Work through the backlog in this order:

1. Decide and enforce the unsupported-action policy.
2. Implement missing-voucher browser training.
3. Define the structured case action contract.
4. Implement evidence capture and redaction.
5. Add post-run AI diagnosis and developer bug triage.
6. Reconcile documentation and repository shape.
7. Add the dashboard and event stream.
8. Add remote access controls.
9. Harden logging and concurrency.
10. Expand handler coverage and verification.

Each item should be reviewed and completed independently before moving to the
next one.
