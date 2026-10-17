# Architecture

## Boundary

Rachis is an external black-box system. This repository owns only test
definitions, browser actions, evidence, and activity reporting.

## Components

1. **Test cases** are Markdown files containing intent, preconditions, steps,
   expected results, and explicit approval.
2. **Runner** uses Playwright against the visible web UI. It must use stable
   semantic locators and capture evidence after meaningful state changes.
3. **Event log** is append-only JSONL. Every action should record its test ID,
   action, safe details, and timestamp.
4. **Dashboard API** exposes read-only status and a simple event stream for
   developers and testers.
5. **Artifacts** are stored locally for now. Screenshots must be redacted
   before sharing and only the current reference screenshot belongs in a test
   folder.

## Extension rules

- Add a new canonical voucher under `app/vouchers/`, and link it into a run folder.
- Keep credentials and tenant-specific values in environment variables.
- Do not encode business assumptions in generic browser helpers.
- Do not let an AI model mark a run as passed.
- Prefer small, explicit actions over a large autonomous agent.

## Planned lifecycle

`draft → ai-prepared → human-approved → running → passed|failed`

