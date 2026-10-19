# Repository Guidelines

Working in this repo is mostly a matter of knowing which file answers which
question. `index.html` is the design; `README.md` is how to run it; this file
is how to change it.

## Where things live

- `index.html` — the single point of reference for the design and its
  conventions. Update it in the same change that moves the design.
- `AGENTS.md` — the procedure an AI coding harness follows: the loop, the
  handoff discipline, the stop signal.
- `README.md` — install, the one command, recording, the workspace layout.
- `docs/DESIGN.md` — the stakeholders' original notes. A historical input, not
  a spec. Do not "fix" its wording.

## Project structure

```
app/
  main.py        the loop, and the console script `uv run main`
  tidy/          the workspace, split by job:
                   cases.py      the case list, and the three-way split
                   files.py      move, rename, auth path
                   links.py      symlinks
                   session.py    session.md
                   workspace.py  the interface the loop consumes
                   cli.py        argument parsing only
  config.py      settings from .env
  events.py      the remote POST
  planner.py     run and brief discovery
recordings/      canonical cases, one folder each
test-cases/      numbered run folders, one symlink per case
app_tests/       the test suite
```

## Commands

```bash
uv run main [run_id]                # the loop
uv run python -m pytest             # the tests
uv run python -m app.tidy [case] [run]  # the workspace, on its own
node /home/pannet1/.agents/skills/design-taste-frontend/scripts/lint.mjs index.html
node /home/pannet1/.agents/skills/design-taste-frontend/scripts/inspect.mjs index.html
```

The last two are the design gate for `index.html`. Run both before committing
a change to it.

## Conventions

**Imports come from the package, not the modules.** `from app.tidy import
Workspace`, never `from app.tidy.links import ...`.

**Report shapes are plain dicts.** A main loop branches on
`report["missing_py"]` and hands over `report["commands"]`. Keep them flat, and
keep them boring.

**A case name is a slug.** Lowercase, hyphenated, matching its folder and its
file: `effort-hours/effort-hours.py`.

**`cases.yml` is a plain list**, one name per line. No wrapper key, no
configuration. One format.

**Never guess a URL.** It is read from `url.txt`. No pattern inference, no
sibling-case reuse, no base-URL fallback.

**Never write a selector by hand.** They come from `codegen` recording the live
DOM. A hand-written locator is a false failure waiting to happen.

**Never commit `.env`, `auth.json`, tenant data, or screenshots.** The
gitignore covers all four; do not weaken the patterns to make something commit.

## Testing guidelines

The suite runs over a real temporary tree with real symlinks and real files.
Prefer that over mocks for anything touching the filesystem.

The loop's browser step is injected (`run_cases(..., runner=...)`), so no test
should ever open Chromium or reach the network. If a test needs to know what
happened at step five, pass a fake runner.

## Changing the design

`index.html` is measured, not just written. After editing it:

1. `lint.mjs index.html` — must report `0 FAIL, 0 WARN` for anything fixable.
2. `inspect.mjs index.html` — must report `0 FAIL`. Read the screenshots it
   saves; passing the meter is the floor, not the grade.
3. Look at the render at 1440, 768 and 390. A problem visible in a screenshot
   is real whatever the meter says.

Worth defending rather than fixing: the module tiles are a grid because the
section blueprint is one; there are no photographs or video because this is a
CLI harness with no world to photograph, and its pictures are its own terminal
output.