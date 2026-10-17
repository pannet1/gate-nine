# Repository Guidelines

## Project Structure & Module Organization

This repository is a documentation workspace for functional testing of `rachis.co.in`:

- `DESIGN.md` describes the testing process, roles, naming expectations, live logging, and remote-test infrastructure.
- `Voucher Testing Manual — Accounting & Inventory.md` is the current tester-facing checklist for voucher functionality.
- `.agents/`, `.aws/`, and `.codex/` contain local agent or environment configuration; do not modify them unless the task explicitly requires it.

Each test should live in a uniquely named folder, such as `YYYY-MM-DD-voucher-type-short-slug/`. Keep the input brief, AI-prepared test case, execution log, and current reference screenshot together.

## Build, Test, and Development Commands

There is no application source, build system, or automated test command. Validate manually against the Rachis tenant using the voucher checklist. Confirm tenant data and credentials first, then record operations using entries such as `input product:hamam voucher` or `save screenshot voucher`.

## Coding Style & Naming Conventions

No programming language is present. Write documentation in concise Markdown with descriptive headings, checklist items, and exact product field or voucher names. Use ISO dates (`YYYY-MM-DD`) in folders and logs, lowercase hyphenated test slugs, and preserve one current screenshot per test document.

## Testing Guidelines

Testing is human-in-the-loop: AI prepares or revises cases, and the tester executes them in Rachis. Follow the manual in order, classify results as pass or fail, and capture a screenshot for the final state or failure. Report voucher type, test number, steps, expected behavior, actual behavior, and voucher number. Do not report known gaps or frozen behavior listed in the manual.

## Commit & Pull Request Guidelines

No Git commit history or repository-specific PR convention is available. For future changes, use short imperative commit subjects (for example, `Add payment voucher test cases`) and keep commits focused. Pull requests should explain the documentation or design change, identify affected test folders or manuals, and include screenshots or sample logs when the change affects test evidence or presentation.

## Security & Configuration Tips

Never commit tenant credentials, customer data, access tokens, or sensitive screenshots. Obtain test URLs and credentials through the project owners, and redact sensitive values from logs and evidence before sharing them remotely.
