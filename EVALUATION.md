# Competitive Evaluation — `gate-nine`

*Audit date: 2026-11-08. Method: local code review (~4k LOC incl. app tests, 135 tests) compared against live public projects via web research.*

## What it is

Human-supervised, black-box E2E harness for a single remote tenant (rachis.co.in): a human records flows via `playwright codegen` from the live DOM, the harness tidies recordings into run folders, replays them visibly for human judgment, and hangs every blocker as a runnable handoff (exit codes 0/1/2). Impeccable discipline docs and the strongest test suite in the author's Interest-2 set — but tailor-made for one tenant, and it explicitly refuses to infer anything.

## Competitive landscape (as of Nov 2026)

| Competitor | Scale | Idea |
|---|---|---|
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | ~39k★ | Lets any AI agent drive/replay real pages; the default way agents now wrangle selectors |
| [web-infra-dev/midscene](https://github.com/web-infra-dev/midscene) | ~15.5k★ | "E2E testing in natural language" — no selector recording at all |
| [qawolf/qawolf](https://github.com/qawolf/qawolf) | ~3.5k★ | Record (codegen) once, replay as Playwright/CI — closest direct rival |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | ~120k★ | `save_history` → `load_and_rerun(variables=…)` — model-less record-once/replay |
| Playwright built-in `codegen` + trace-viewer | — | The upstream baseline this repo thinly wraps |

## Where we win

- The only tool of its kind enforcing **human-owned selectors AND human-owned PASS/FAIL** — the right contract for a remote tenant running real financial documents (no evidence without approval).
- **One-command loop with handoff discipline** (runnable briefs, exit-code protocol) — better daily UX than qawolf or raw codegen watching.
- Test discipline: 135 tests, tidy run-folder structure, symlinks to recordings instead of copies.

## Where we lose

- The mechanical core (codegen + replay) is upstream Playwright functionality now — every rival does it faster and more robustly.
- No auto-variableization, no selector healing, no drift reporting: drift is discovered only by watching a replay fail.
- Single-tenant: URLs, auth and workflow docs are hardcoded for rachis; reuse requires heavy doc surgery.

## Verdict

**Keep private.** This is a bespoke QA contract for one client, and the publishable mechanical part already exists upstream. The only fragment with a unique claim is the *handoff protocol* (human-supervision gates as runnable exit codes).

## Top improvements

1. **Generalize the tenant**: parameterize `url.txt`/auth via per-environment config and make briefs/`cases.yml` schema-driven — that turns a bespoke project into a portable harness.
2. **Selector-health report per replay**: record which steps are brittle and fire codegen re-record suggestions that mid-test `-only-steps` accepts — today, brittleness surfaces only as a failed watch.
