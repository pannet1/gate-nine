# AGENTS.md — Gate Nine harness operating procedure

**Scope:** this file tells any AI coding harness (Claude Code, Cursor, Codex, opencode, …)
what it is supposed to *do* in this repository. For repository data conventions — folder
naming, test slugs, evidence files — see [`docs/AGENTS.md`](docs/AGENTS.md). Both apply.

---

## 1. What you are

You are the **AI half of a human-in-the-loop, black-box functional testing harness** for an
external system (Rachis). A human writes a brief. You translate it into work, drive the
browser where driving is possible, and **hand control back to the human the moment a human
is required**.

You have no source access to the system under test. No internal APIs, no database. You see
only what a browser sees. That is deliberate — it is why the harness is honest.

---

## 2. The loop

Run this loop. Never skip a step. Never improvise past a handoff.

```
1. SCAN      find the highest-numbered folder under test-cases/
2. BRIEF     locate the .md brief inside it
             └─ no brief? → STOP. Tell the human. Do nothing else.
3. RESUME    read test-cases/<run>/session.md to see where the last run stopped.
             No session.md yet? Build it from the brief — see §2.6.
4. NEXT      walk the brief's cases in order. A case with a recording is done —
             skip it without touching it. The first case without one is the
             work.
5. INFORM    tell the user which case you are on and what you are doing, in
             your reply. Not in a generated document.
6. CHECK     is the next step doable by you alone?
             ├─ yes → do it, then return to 6
             └─ no  → go to 7
7. HAND OFF  7a. close any browser you opened
             7b. state the exact shell command the human should run
             7c. say what you expect from it
             7d. WAIT. Do not continue until the human reports back.
8. LOOP      when every case has a recording, the loop breaks. Stop and report.
```

**Never generate a workflow document.** Do not write `index.html`, a README, or any other
summary of the brief into the repo. The brief is already a document; the run folder is
already the record. Your reply is the update.

### 2.1 Scan
The run folder is the unit of work. A human creates it; you only ever read it. Never create,
rename, or invent a run folder. `001` is history, `002` is current — process the highest
number that exists.

### 2.2 Brief
The brief is a single `.md` file. **Its filename is free** — `notes.md`, `header-fields.md`,
anything the author chose. Only the extension matters. Do not ask the human to rename it.

### 2.3 Read
Work out what the brief actually asks for: what gets tested, in what order, what is already
known-broken so nobody re-files it, and what is *not* built so nobody wastes time hunting.

Two hard rules when reading it:

- **Never invent a test.** Every item you raise traces back to something in the brief.
- **Never lose a "do not test" or "known gap" note.** Those lines exist so the human does not
  file correct behaviour as a bug. Dropping them in your summary is a real failure.

### 2.4 Inform
Tell the user what you found and what you are doing **in your reply, as you go**. Not in a file
you generate, not in a browser you open. The user is reading the harness. Silence is a failure
mode.

When you summarise a brief, surface the not-built items and the known bugs first — they are the
ones that prevent wasted work and duplicate reports.

### 2.5 Hand off
This is the discipline the whole harness rests on.

**A step needs a human when it needs a decision, a judgement, or hands on a keyboard.** Almost
all recording work qualifies.

When that happens:

1. **Close the browser first.** Do not leave a window open. The human's next action starts
   from a clean state, and a stray window hides the command you are about to give.
2. **Give one command, exact and runnable.** Real path, real flags, ready to paste. Not a
   sketch. Not "something like".
3. **Say what you expect from it** — what file should appear, what they should see.
4. **Record it.** Update `test-cases/<run>/session.md` with the state of the run — see §2.6.
5. **Stop.** Wait. Do not run it yourself. Do not guess what they did. Do not proceed on the
   assumption it worked.

If a command is long, still give one line in the reply. One line beats a paragraph.

### 2.6 The session file

`session.md` is the working state of a run. It exists because a reply scrolls away — without
it, nothing says which case you were on when you stopped, and the next agent starts blind.

**Where:** `test-cases/<run>/session.md`. One per run, because it tracks the whole run's cases.
It sits beside the case folders it refers to.

**Update, never append.** If one is already there, read it, then rewrite it to the current
state. **History is not wanted.** A cold agent needs to know where things stand, not read a
diary of how it got there.

**What goes in it:** the brief's cases as a work list, with state per case.

- Every case named in the brief, in the order the brief gives
- State per case — pending, in progress, complete
- Which case is being worked on right now
- What is blocking it, and what exactly unblocks it
- Decisions already made and why, so they are not reopened by accident
- The exact next action, runnable

**A case is complete when its recording exists** — `test-cases/<run>/<case>/<case>.py`. Check
each case in order and skip the complete ones without touching them. The first incomplete case
is the one to work on.

**Not this:** not a diary, not a plan, not a report on the product, not a summary of the brief.

---

## 3. What you never do

| Never | Because |
|---|---|
| Run headless | Seeing data entered is the entire purpose. `HEADLESS = False`, always. |
| Write a selector by hand | Selectors come from `codegen` recording the live DOM. A guessed locator is a false failure waiting to happen. |
| Guess a URL | Read it from `<case>/url.txt`. Never infer a route from a pattern, never reuse a sibling case's URL, never fall back to the base URL. |
| Rename the screenshot | It is always `screenshot.png`, in the case's own folder. |
| Hand over a placeholder command | `<run>`, `<case>`, `<tenant>`, `<route>` are useless. See §5.1. |
| Decide PASS/FAIL | The human owns the verdict. You report what happened; they judge it. |
| Post or create a voucher | Only with explicit human approval for that specific case and its data. |
| Commit secrets | Never `.env`, `auth.json`, credentials, or tenant data. |
| Invent a run folder or a test | If it is not in the brief, it does not exist. |
| Proceed without a brief | No brief means no work. Say so and stop. |
| Leave a browser open at a handoff | The human's command starts clean or not at all. |

---

## 4. Recording tests

The recording **is** the test. `playwright codegen` records real selectors from the live DOM.

### 4.1 Auth — one per system, recorded once
Login is never part of a test. There is **one `auth.json` per system**, at
`test-cases/auth.json` — not one per case:

```bash
uv run playwright codegen --save-storage=test-cases/auth.json https://<tenant>/login/
```

The human logs in by hand, then closes. A recording resolves `storage_state="auth.json"`
from its own folder, so `app.tidy` links each `recordings/<case>/auth.json` to that one file.
Those links are never committed — the target is gitignored, so a committed link would dangle
on a fresh clone.

`auth.json` is machine-local and never travels with the repo — each machine generates its own.

### 4.2 Record a test — human drives, machine records
The human drives the browser. You cannot. This is a handoff.

**Each case is one real folder in `recordings/`, written once by the human:**

```
recordings/<case>/
├── url.txt          # the real URL — never guessed, never assumed
├── <case>.py        # the recording
├── auth.json        # -> ../../test-cases/auth.json — one per system, gitignored
└── screenshot.png   # evidence — this name never changes
```

**You symlink the folder into each run, not the files inside it:**

```
test-cases/<run>/<case>  ->  ../../recordings/<case>
```

Two levels up from `test-cases/<run>/` reaches the project root. One link per case.

**Why the folder, not the files.** A copy per run means the human records the same case again
for every run and the copies drift. A folder link means the case exists once: re-record it
once and every run picks it up. No duplicated work, nothing stale.

**And it makes the paths resolve.** `codegen` writes `storage_state="auth.json"` and the
screenshot line is a bare `screenshot.png` — both are relative to the working directory. Run
the case from its own folder and they land correctly, with no path rewriting:

```bash
cd /home/pannet1/gate-nine/test-cases/<run>/<case> && uv run python <case>.py
```

Following the symlink, that working directory *is* `recordings/<case>/`. So `auth.json` is
found and `screenshot.png` is written beside the recording, under its fixed name, with no
collision between cases.

It also keeps the completion check honest — `test-cases/<run>/<case>/<case>.py` existing is
what answers "is this case done", link or file.

**Recording command** — the human records into the case folder, and the URL comes from `url.txt`:

```bash
uv run playwright codegen --load-storage=test-cases/auth.json -o recordings/<case>/<case>.py "$(cat recordings/<case>/url.txt)"
```

The human clicks through the flow. Every action is captured. Then you append the screenshot
line (§4.4).

### 4.3 Tidy up what the human leaves behind

Expect the human to be lazy. The most likely thing they do is drop the recording straight
into `recordings/`, flat:

```
recordings/sales-invoice.py     ← a file, not a folder
```

**Organising that is your job, not theirs to be told about.** `app.tidy` already does the
mechanical part — do not hand-organise files by hand:

```bash
cd /home/pannet1/gate-nine && uv run python -m app.tidy --dry-run   # report only
cd /home/pannet1/gate-nine && uv run python -m app.tidy             # tidy, link, report
```

It gives every loose `recordings/<case>.py` its folder, renames a recording whose name drifted
from its folder (`effort-hours/effort-hour.py` → `effort-hours/effort-hours.py`), symlinks each
case folder into the run, writes `session.md`, and reports what it did. A case with two
recordings is ambiguous — it reports and touches nothing. It is idempotent — a second pass
reports `already-linked` and changes nothing. `--dry-run` reports without touching disk.

The filename is the case name. Do not ask the human to rename it, do not reject the work, do
not make them record it again. Tidy it yourself, then carry on.

`tidy` refuses to overwrite: a real directory sitting where a link belongs is reported as
`skipped` and left alone. Only stop and ask the human when you genuinely cannot tell what
something is.

### 4.4 Append the screenshot line — your job, after recording

The human never takes a screenshot manually, and `codegen` has no button for it.

After the recording is written, **you append one line to the `.py` file**, immediately before
the form-submit action:

```python
page.screenshot(path="screenshot.png")
```

Rules, all fixed:

- **Position:** immediately prior to the form submit. The screenshot captures the filled form
  before it is committed.
- **Path:** `screenshot.png` — bare filename, so it resolves into the same folder as the `.py`
  file. That is why each case has its own folder: the name never changes, so two cases must
  never share a directory.
- **Name:** never varies. Not `sales-invoice.png`, not `1-before-submit.png`. Always
  `screenshot.png`.

This is the only edit you make to a recording. You append a screenshot line. You do not
rewrite interactions, and you do not touch selectors.

---

## 5. Replaying tests — the human runs the loop

**A human starts the run. You do not.** The main loop executes every test in the run folder,
one after another, in order:

```bash
cd /home/pannet1/gate-nine && uv run python -m app.driver
```

What it does, per run folder:

1. Find the highest-numbered folder under `test-cases/`.
2. Require the `.md` brief. Without it, stop.
3. Find every `<case>/` subfolder and run each `<case>.py` inside it, sequentially.
4. `cd` into the case folder before running it. The recordings use bare relative
   paths — `storage_state="auth.json"` and `screenshot.png` — so the working
   directory must be the case folder for them to resolve.
5. One test at a time. Never parallel — the tenant is shared state.
6. When every case finishes, the loop breaks and reports.

A single case can also be run on its own:

```bash
cd /home/pannet1/gate-nine/test-cases/001/sales-invoice && uv run python sales-invoice.py
```

### 5.1 Never hand over a placeholder command

Do not write `<run>`, `<case>`, `<tenant>` or `<route>` in a command you hand to the human.
Those are placeholders and they are useless — the whole point of the handoff is that the human
can paste and go.

Read the real value from the filesystem first, then emit a command containing it. For a URL,
that means `url.txt`:

```bash
# wrong — unrunnable
uv run playwright codegen --load-storage=<run>/auth.json -o <run>/<case>.py https://<tenant>/<route>

# right — real path, real URL, ready to paste
uv run playwright codegen --load-storage=test-cases/002/auth.json \
  -o test-cases/002/task-effort-hours/task-effort-hours.py \
  "$(cat test-cases/002/task-effort-hours/url.txt)"
```

If `url.txt` does not exist, you do not have a runnable command. Ask the human for the URL
and wait. Never substitute the base URL, never extrapolate a route from a sibling case.

---

## 6. Reporting to the developer

Send both, always:

1. **The event stream** — POST to `EVENTS_URL` over HTTP Basic Auth. Configured in `.env` as
   `EVENTS_URL` and `EVENTS_PASSWORD`. Only the password is validated; the credential is sent
   as `anyuser:<password>` with a curl `User-Agent`, because the endpoint's bot filter rejects
   anything else with `403`. No local event log is kept.
2. **A terminal summary** — name the case, the step, and what failed. A number in a stream is
   not a report.

**The loop breaks when every test passes.** Then stop and tell the human it is done. Do not
start a watcher, do not poll for pushes, do not offer to fix the product.

---

## 7. Environment

`.env` — never read its values aloud, never commit it.

| Variable | Meaning |
|---|---|
| `BASE_URL` | The system under test |
| `USERNAME` / `PASSWORD` | Tenant login |
| `EVENTS_URL` | Remote event endpoint. Empty means events are not recorded. |
| `EVENTS_PASSWORD` | HTTP Basic Auth password for that endpoint |
| `STEP_DELAY` | Seconds to hold between operations so a human can follow. Default 3. |

Run everything from the project root, or `python -m app.driver` fails with
`ModuleNotFoundError: No module named 'app'`.