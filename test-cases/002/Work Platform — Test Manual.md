# Work Platform — Test Manual

Oct 16, 2026 · @Iyyasamy Murugesan

## Scope & how to use this manual

This manual covers the **Work Platform module only** — Task Management + Service Helpdesk (one unified `work_items` engine under the hood). No other module.

Every feature below is marked with the same legend the engineering status ledger (`STATUS.md`) uses:

- **▣ Gate-9 verified** — a founder walked it live on a real tenant and it passed. Safe to test and expect to work end-to-end.
- **◐ Partial** — backend and/or UI exist, but either side is incomplete or no founder walk has confirmed it yet. Test it, but expect rough edges, and report anything odd rather than assuming it's your mistake.
- **▢ Not built** — there is nothing to test. Don't file a bug for these; they're listed so you know not to look for them.

Work through the sections in order: environment/login, core concepts, then the two feature lists (Task Management, Service Helpdesk), then SLA, Approvals, Reports, and finally Permissions and Known Gaps — read those last two before you start, since they explain who can see what and what to skip.

## Test environment & login (VPS)

**Auth model.** Rachis uses HttpOnly cookies, not a bearer token you paste anywhere: `at` (access, \~15 min), `rt` (refresh, used only at `/auth/refresh`), and `csrf` (JS-readable, echoed as `X-CSRF-Token` on every POST/PUT/PATCH/DELETE). Logging in through the browser sets all three automatically — you don't need to handle cookies yourself unless you're hitting the API directly with curl for a quick check.

**To test through the UI:** open the VPS app URL, sign in with a test user on the target tenant, and use the sidebar. The Work module's nav group ("My Desk") shows whatever leaves your role's permissions admit — if an item you expect is missing, check Permissions / roles (below) before assuming it's a bug.

**To check something at the API directly (curl):** you need the real `at` cookie value, not a placeholder.

1. Open the app in Chrome, sign in.
2. DevTools (F12) → Application/Storage tab → Cookies → your domain.
3. Copy the value of `at`.
4. `AT_COOKIE="<paste-the-value>" && curl -s -b "at=$AT_COOKIE" https://<vps-host>/api/v1/auth/me`

**Which tenant to test on.** The Zigma Infosoft demo tenant is being provisioned in phases — HR & Payroll first; Task/Helpdesk (this module) is scheduled **last** in that rollout and may not yet have Work entitlement or seed data. For Work module testing, use Fortune Electronics or another tenant already confirmed to have the Work module enabled, not Zigma, until Work is confirmed live there.

## Core concepts: work types, states, workflows

Task Management and Service Helpdesk are **one engine**, not two products bolted together. Every Task, Support Ticket, or other work item is a row in a single `work_items` table, distinguished by its **work type** (e.g. "Task", "Support Ticket") rather than by a separate schema.

- **Work type** — a tenant-configurable definition of a kind of work: which custom fields it carries, which workflow governs its states, and (for Service Helpdesk types) which SLA policy is bound to it. Task Management and Service Helpdesk share the same type mechanism.
- **Workflow / states** — each work type is bound to a workflow made of named states (e.g. "New", "Triaged", "In Progress", "Resolved", "Closed", "Cancelled"/"Void"). States are tenant-configurable, not hardcoded. A state can be flagged as **terminal** (closes the item) or as a **pausing** state (stops the SLA clock — see the SLA section). Transitions currently happen by dragging a card on the Board, or via the item's action buttons; there is no separate "workflow editor" admin screen yet.
- **Participants** — every item carries typed people: owner, assignee, reviewer, approver, watcher. The People panel on an item's detail page shows who's on it right now.
- **Links** — items can block / be-blocked-by other items; a blocked item cannot be approved or closed until its blocker clears.
- **Source linkage** — a work item can be traced back to the record that spawned it (e.g. an invoice, a GRN) via a source type + id.
- **RLS** — every work item is scoped to its company under row-level security; you will only ever see your own tenant's data, by design, regardless of role.

## Feature list: Task Management

| Feature | Status | Test notes |
| --- | --- | --- |
| Title, description, priority, status, type | ◐ | Core fields work; `category`/`tags` fields don't exist yet — don't look for them |
| Estimated / actual effort hours | ▣ Gate-9 2026-10-15 | Enter on create, confirm it persists after reload |
| Quick-create + full-create page | ◐ | Full create page works; there is no one-click "quick create" shortcut yet |
| Subtasks (parent→child) | ▣ Gate-9 2026-10-05 | Subtasks tab on an item's detail page |
| Checklist items | ▣ Gate-9 2026-10-15 | Add/check items in the Checklist panel |
| Clone / duplicate | ▢ Not built | — |
| Recurring tasks (RRULE) | ▢ Not built | — |
| Templates | ▢ Not built | — |
| Source-entity link (e.g. from an Invoice/GRN) + registry | ▣ Gate-9 2026-10-05 | Shows on Create/Edit forms when relevant |
| Programmatic create via other modules (producer integrations) | ▢ Not built for Work | Older producers (Invoice, Bundle, GRN, etc.) still create legacy records, not real work items — don't test this path expecting a Work item to appear |
| Roles: owner / assignee / reviewer / approver / watcher / team | ◐ → approver ▣ Gate-9 2026-07-14 | Visible on the People panel; "team" is a participant kind, not a separate team concept |
| Tenant-configurable status set | ▣ Gate-9 2026-07-13 (backend+board) | No settings screen to edit the workflow yet — states are pre-seeded |
| N-step approval chain | ▣ Gate-9 2026-10-04 | See the Approvals section |
| SLA: response, resolution, breach, auto-escalation | ◐ | Clocks run; no SLA badge/chip shown on the item yet (test via Reports instead) |
| Threaded comments, @mentions, reactions | ◐ | Comments work (Conversation tab); @mentions and reactions are not built |
| Activity feed | ▣ Gate-9 2026-10-05 | History tab on the detail page |
| Attachments: upload, preview, download | ▣ Gate-9 2026-10-06 | Includes soft delete, scan status field, per-role permissions |
| Notifications (assigned, mentioned, SLA breach/escalation, approval, due/overdue) | ◐, several sub-items ▣ Gate-9 2026-10-15 | Header bell; some notification text now human-readable (dates/states). Mobile push notifications are blocked — see Known Gaps |
| Dependencies (blocking / blocked-by) | ▣ Gate-9 2026-10-05 | Blocked items can't be approved/closed until the blocker clears — try this directly |
| Dashboard tiles (Open / SLA / Due / KPIs) | ◐ Gate-9 2026-09-29 | No Overdue or Awaiting-approval tile yet |
| List view + Board (kanban) | ▣ Gate-9 2026-07-13 | Drag-and-drop on the board; list has sort/filter/search |
| RBAC (view/edit/approve/delete/assign), audit trail, RLS | ◐ | Approve+delete permission keys exist; delete via UI not fully confirmed — flag if the delete button is missing or misbehaves |

Also not yet built, if you're looking for them: a **Calendar view** (stub only), tenant-admin screens for **Work Types / Field Registry / Workflow editor / Automations** (all API-only today — curl or ask an engineer, no settings UI), and an **SLA indicator** on the item itself.

## Feature list: Service Helpdesk

| Feature | Status | Test notes |
| --- | --- | --- |
| Email intake + intake channel admin | ▣ Gate-9 2026-08-14 | Settings → Service Desk → Intake Channels |
| Business-hours calendars | ▣ Gate-9 2026-09-29 | Settings → Service Desk → Calendars |
| SLA engine (clocks, escalation, breach sweep) | ▣ Gate-9 2026-08-14 | See SLA section |
| Contracts + SLA binding | ◐ | API-complete; no staff UI to create/edit a contract (curl/admin-only) |
| Customer portal (auth, tickets, reply, KB search, CSAT survey) | ▣ Gate-9 2026-08-19 / 2026-09-29 | Test as a customer at `/portal/` — request link, sign in, view/reply to tickets, search KB, answer a satisfaction survey |
| Knowledge base — staff authoring | ▣ Gate-9 2026-09-29 | Settings → Service Desk → Knowledge Base: create, draft, publish, revise, archive |
| Knowledge base — portal search | ◐ | Works at the API/portal; no dedicated founder walk recorded for search specifically |
| CMDB: customer assets / config items | ◐ | Asset detail pages exist; no founder walk yet |
| Dispatch board + technicians | ▣ Gate-9 2026-09-29 | Service → Dispatch; Settings → Zones & Skills. Technician picker is a searchable Autocomplete |
| Scheduling: appointments, conflicts, portal booking | ▣ Gate-9 2026-09-29 | Service → Dispatch → Schedule tab |
| CSAT satisfaction (staff view) | ▣ Gate-9 2026-09-29 | Settings → Service Desk → Satisfaction |
| Per-user notification preferences | ▣ Gate-9 2026-09-29 | Settings → Profile & preferences → My notifications |
| Merge / split tickets | ◐ | UI works (drawer footer actions); merged/void items hidden by default behind a "Show merged/void" toggle |
| Workflow seed at provisioning | ◐ | New tenants get a default workflow automatically; no founder walk confirming every provisioning path yet |

**Known UI bugs fixed and re-walked 2026-10-11** on Fortune (Service → Dispatch): Esc closes the dispatch drawer, Schedule/Assign buttons no longer truncate, the technician field is a proper searchable picker, the schedule footer hint stays visible while scrolling, and the Requests tab loads without a manual reload.

## Feature list: SLA engine

**▣ Gate-9 2026-08-14** for the core engine (clocks, escalation, breach sweep), on top of **business-hours calendars** and **contract→SLA binding**.

What to test:

- **Policy versions.** SLA policies are versioned; publishing a new version archives the old one. Only a draft can be edited; published/archived versions are read-only. Try creating a new version and confirm the old one locks.
- **Escalation ladder.** Each policy has a ladder of steps with time-based targets (assignee → owner → role → named user). Editable only on a draft. Try firing an escalation by letting a short test policy's target lapse.
- **Pause on wait states.** When an item moves into a workflow state flagged as "pausing" (e.g. "Waiting on customer"), its SLA clock should stop accumulating and resume correctly when it leaves that state. (◐ — code shipped, but no confirmed founder walk yet; a good thing to test deliberately.)
- **Breach behaviour.** Once a clock breaches, it should stay marked breached even if later events make a resolution look on-time — it never resets. Confirm this doesn't silently clear itself.
- **What's missing:** there is **no SLA badge/indicator on the item itself** yet (list, board, or detail page) — the only way to see where a ticket's SLA stands today is through the Reports (next section) or the Dashboard's at-risk panel. Don't look for a countdown chip on the ticket card.

## Feature list: Approvals

**▣ Gate-9 2026-10-04**, walked live on Fortune Electronics: N-step approval chains on a work item. What was confirmed working:

- A banner reading "Step N of M" on the item while an approval is in progress.
- Approve / Reject actions, each requiring the real approver (no impersonation).
- Submit-for-approval action.
- The item's state is gated — it cannot move to Done while an approval is pending.
- An approval History showing real names, not IDs.
- The list of eligible approvers is access-controlled (only people allowed to approve can see/act on that step).
- A **blocked item** (per the Dependencies feature) is checked and refused at the final approval step, not just silently allowed through.

**What to try, and a known open issue:** after an approval step is decided, the item's People panel is known to go stale until the page is reloaded (the requester briefly shows 0 people right after submitting; a rejecting approver can stay listed after rejection). This is a recorded, unfixed UI bug — reproduce it and don't file it as new, but do confirm whether it's still present.

**To test the notification side** of approvals you need a work item **type that has an approval chain configured** — not every work type does. Check with whoever set up the test tenant's work types if you don't see an approval option on an item.

## Feature list: Reports & Dashboard

**▣ Gate-9 2026-09-29** on Fortune Electronics. `Work → Dashboard` is the real, dedicated dashboard for this module — it is not the general company dashboard, and it is reachable from the sidebar under the Work group as **Dashboard** (not to be confused with the older "Service Reports" nav item, which now simply redirects into this same page).

Five KPI reports, all reachable from the Dashboard and from the Reports catalogue:

| Report | What it measures |
| --- | --- |
| SLA Compliance | First-response and resolution SLA outcomes per period |
| Mean Time to Resolution (MTTR) | Time from creation to first resolution per period |
| First-Time Resolution (FTR) | Share of resolved work not reopened since |
| CSAT Summary | Satisfaction requests sent, response rate, average rating per period |
| Technician Performance | Open load, resolved count, resolution time per technician |

The Dashboard itself shows tiles (Open / SLA / Due / KPIs) and an **At-risk panel** — items approaching an SLA breach light up here in real time; this is currently the only place to see SLA risk in the UI (there's no per-item badge yet, see the SLA section). There's no Overdue or Awaiting-approval tile yet — don't expect those.

**If a report or the dashboard appears empty or missing from your sidebar:** check first whether your role holds `work:work_item:read` (Dashboard) or the matching `reports:work_*:read` permission (each report has its own key) — see Permissions below — before assuming it's broken.

## Permissions / roles needed to test

Permission keys follow `module:resource:action`. The ones that gate what you'll see in this module:

| Key | Gates |
| --- | --- |
| `work:work_item:read` | My Work, Inbox, **Dashboard** nav leaves; viewing work items |
| `work:work_item:approve` / `:delete` / `:assign` | Approve / delete / assign actions on a work item |
| `work:sla_policy:read` | SLA Policies settings screen — also auto-grants all five KPI report keys below (managerial carry-over) |
| `work:csat:read` | Individual satisfaction answers — also auto-grants the CSAT Summary report key |
| `reports:work_sla_compliance:read` / `work_mttr` / `work_ftr` / `work_csat_summary` / `work_technician_performance` | Each of the five KPI reports individually |
| `service:ticket:read` | Legacy "Service Reports" leaf (now redirects to the Work dashboard) |

**Roles.** The `owner` role gets every Work/Service key automatically. For a realistic test pass, use at least two accounts: one with a broad role (owner or a role holding `work:sla_policy:read`) to see admin/reporting surfaces, and one with a narrow operational role (e.g. a technician or agent) to confirm they correctly *don't* see admin-only screens.

**If a nav item you expect is missing:** it's almost always one of (a) your role lacking the permission key above, (b) the tenant not yet migrated to the latest schema, or (c) a 60-second-old cached manifest (wait a minute and retry) — rarely a missing feature, since the Dashboard/My Work/Inbox seed data has been verified correct in the backend migrations.

## Known gaps / not yet testable

Don't spend testing time chasing these — they're confirmed not built or confirmed blocked:

- **Mobile app (`rachis-works`).** Has not started. Anything requiring a registered mobile device — push-notification delivery confirmation, device-bound approval decisions — cannot be tested yet.
- **Clone/duplicate, recurring tasks, templates, calendar view, automations engine.** None built.
- **Work Types / Field Registry / Workflow editor / Automations admin screens.** Backend APIs exist; no settings UI. Tenant configuration of these today requires direct API calls, not a test-manual activity.
- **SLA indicator on the item itself.** Not built — use the Dashboard's At-risk panel or the KPI reports instead.
- **@mentions and reactions on comments.** Not built.
- **Quick-create shortcut.** Not built (full-create form works).
- **Programmatic work-item creation from other modules** (invoices, GRNs, bundles, etc.) still lands in a legacy table, not in real Work items — expect this path to look broken; it's tracked, not a new bug.
- **Legacy endpoints still live in parallel:** `/api/v1/tasks` and `/api/v1/service/tickets` are old engines kept for compatibility; testing against them will show stale/empty data (e.g. the legacy Service → Tickets screen may show "0 tickets" while the real Work ∙ Support Ticket type holds everything). Always test through the **Work** module pages, not these legacy ones.
- **People panel going stale after approval decisions.** Recorded bug, reproduce but don't re-file (see Approvals section).
- **The sidebar "Dashboard not showing" question some testers may hit:** the backend seed data is confirmed correct for all accounts with `work:work_item:read`. If it's missing for you, it is a tenant-migration, permission, or cache issue — not a missing feature. Report which tenant and role you're on rather than assuming the feature doesn't exist.

This manual reflects the engineering status ledger as of **2026-10-16**. If something you test disagrees with a status mark here, that's valuable — report it rather than silently trusting either source.
