# Multi Approvals

A configurable, **generic** multi-level approval engine for any Frappe DocType — Purchase Invoice, Purchase Order, Journal Entry, Expense Claim, Sales Order, or any custom DocType you register. There is no DocType-specific approval logic anywhere in this app; every decision the engine makes is driven by a single admin-facing settings screen plus the approvers added on the actual document.

## Architecture

```
                    Multi Approval Settings
                           |
                           | defines HOW
                           v
                  Actual Business Document
                           |
              +------------+------------+
              |                         |
              v                         v
       Approvers Table          Information Requests
       (who approves?)          (who needs info?)
              |                         |
              +------------+------------+
                           v
                   Generic Approval Engine
```

- **Multi Approval Settings** (Single doctype) — one admin screen, one child table (`Approval Configuration`), one row per registered DocType. This is the *only* place approval mode, allowed actions, auto-submit, and approver source are configured.
- **User Approval Table** and **Approval Information Request** — internal child DocTypes, never opened as standalone forms. They are attached to any registered DocType automatically via idempotently-synced Custom Fields.
- **`multi_approvals/multi_approvals/utils/`** — the engine itself. Every function takes `doc` and looks up its configuration through `get_approval_config(doc.doctype)`; if none is found, the engine does nothing. Sequential/Parallel branching is the only "mode" logic in the codebase — there is never a `if doc.doctype == "..."` anywhere.

## Installation

```bash
bench get-app multi_approvals /path/to/multi_approvals
bench --site <site> install-app multi_approvals
bench --site <site> migrate
```

`after_install` / `after_migrate` both call `sync_custom_fields()`, so on a fresh install with an empty Multi Approval Settings there is nothing to sync yet — fields appear as soon as you register a DocType (see below).

## Configuration

1. Open **Multi Approval Settings**.
2. Add a row to the **Approval Configuration** table.
3. Select the **Document Type** (e.g. `Purchase Invoice`).
4. Choose **Approval Mode**: `Sequential` or `Parallel`.
5. Choose which actions approvers are allowed to take: **Allow Approve**, **Allow Reject**, **Allow Need More Information**.
6. Set **Auto Submit on Final Approval**.
7. Set **Approver Source** to `Manual` (the only fully implemented source in this version — see *Role Based* below).
8. Check **Enabled**.
9. Save.

Saving triggers `sync_custom_fields()` automatically (also exposed as an **"Sync Custom Fields"** button on the settings form), which creates these fields on the target DocType — grouped under their own **"User Approvals" tab** — if they don't already exist:

| Fieldname | Purpose |
|---|---|
| `custom_approval_tab` | Tab Break. Everything below lives in its own "User Approvals" tab, appended after the DocType's existing tabs, so it's never mixed into an unrelated section. |
| `custom_add_approvers` | Table → User Approval Table. The approval chain. |
| `custom_approval_information_requests` | Table → Approval Information Request. All info requests over the document's lifetime. |
| `custom_approval_pending_with` | Link → User. Who the ball is currently in front of. |
| `custom_todo_created` | Hidden check. Prevents duplicate initial ToDo creation. |
| `custom_approval_status` | Select. `Not Started / Pending / Information Requested / Approved / Rejected`. |

Field creation is idempotent (`create_custom_fields(..., update=False)`), and disabling a configuration **never** deletes its fields.

You can register as many DocTypes as you like from the same single settings screen — each is just another row.

> **Upgrading from an earlier version?** Fields used to be grouped under a collapsible Section Break instead of a dedicated tab. A one-time patch (`v0_2_relocate_approval_fields_to_tab`) runs automatically on `bench migrate` and relocates existing fields — it's non-destructive (child table data and existing column values are preserved; only the field *definitions* are recreated).

## Adding Approvers

Approvers are **not** configured in Multi Approval Settings — they're added directly on the business document, in its new **Approvers** grid:

```
Purchase Invoice
      |
      v
Approvers
   +-- John
   +-- Sarah
   +-- Mike
   +-- David
   +-- Raj
   +-- Tom
   +-- Alex
```

Row order determines approval order in **Sequential** mode. Duplicate users in the same chain are rejected with a clear validation message, and once the process has started (`custom_todo_created = 1`) the approver list itself becomes locked to prevent tampering mid-flight.

**A registered DocType (with `Approver Source = Manual`) cannot be saved at all — not just submitted — without at least one row in the Approvers table.** This is enforced in `validate()`, so it applies on every save (draft or otherwise), through the UI, the API, or a script.

- **Sequential**: only the first row gets an Open ToDo. As each approver approves, their ToDo closes and the next row's ToDo opens, `custom_approval_pending_with` advances, until the last approver — then `custom_approval_status = Approved` and (if configured) the document auto-submits.
- **Parallel**: every row gets an Open ToDo immediately. The document is only fully approved once *every* row has `action = Approve`.

## Information Requests ("Need More Information")

This is deliberately **not** a reset button. If the current approver needs more information before deciding, they:

1. Click **Need More Information** (only shown if the config allows it).
2. Enter what's needed.
3. Select one or more users from the approver list to ask.
4. Send the request — this creates one `Approval Information Request` row *per selected user*, each with its own ToDo.
5. Wait. The approver's own row stays blank/pending — it is **not** overloaded with an "asked for info" state — and the document's overall `custom_approval_status` flips to `Information Requested`.
6. Once every request they raised is `Responded`, they're notified and `custom_approval_status` returns to `Pending`.
7. They review the responses (visible in the Information Requests grid) and then choose **Approve**, **Reject**, or **Need More Information** again.

Crucially: earlier approvers' decisions are untouched, and the chain does not restart from the beginning. Multiple concurrent and historical information requests are all preserved as separate rows — nothing is overwritten.

## Security

All authorization is enforced server-side, independent of the UI:

- An approver can only act on a row where `frappe.session.user == row.user`.
- A user can only respond to an information request where `frappe.session.user == request.requested_from`.
- A row that already has an `action` cannot be acted on again.
- Sequential mode rejects any action from someone who isn't the current `custom_approval_pending_with`.
- `before_submit` blocks submission — via UI, API, or script — unless every approver row has `action = Approve` (exact message: *"You cannot submit until all approvers have approved."*), and separately blocks submission if approvers are required but none exist, or if any row was rejected.
- Once `docstatus != 0`, no further approval or information-request actions are accepted, regardless of entry point.

The client script (`public/js/multi_approval.js`) only decides what buttons to *show*; it enforces nothing.

## Important Assumptions / Design Decisions

- **`allowed_actions`** is implemented as three explicit checkboxes (`allow_approve`, `allow_reject`, `allow_need_more_information`) on `Approval Configuration` rather than a free-text/multi-select field, to avoid fragile string parsing while remaining fully admin-configurable per DocType.
- The `action` field on `User Approval Table` keeps the schema-defined `Need More Information` option for completeness, but the engine deliberately never persists it as a row's terminal state — per the explicit "don't overload the action field with information-request states" requirement, a requesting approver's row simply stays blank until they make a final Approve/Reject decision.
- Once `custom_todo_created` is set, the approver list is locked (validated against `doc.get_doc_before_save()`) to prevent the chain from being altered mid-process.
- **Role Based** approver source is scaffolded (the Select option exists, and `get_approval_config`/the engine recognize it) but intentionally raises a clear validation error rather than silently doing nothing, so it can be implemented later without touching the core engine's call sites.
- Notifications use Frappe's built-in `Notification Log` doctype (best-effort, wrapped so a notification failure never blocks the workflow) rather than email, to keep the app dependency-free.
- The app only depends on the Frappe framework (`required_apps = []`) — no ERPNext dependency — so it works against any Frappe DocType, custom or core.

## Testing Considerations

This app ships as source only; validate it on a real bench:

1. `bench --site <site> install-app multi_approvals && bench --site <site> migrate`
2. Register a lightweight custom DocType first (fewer side effects than a full ERPNext transaction) to sanity-check the Sequential and Parallel flows end-to-end, including the Need More Information dialog and response flow.
3. Confirm idempotency: re-run `bench --site <site> migrate` and re-save Multi Approval Settings — no duplicate Custom Fields or ToDos should ever appear.
4. Exercise the security boundary from the API/console directly (not just the UI) — e.g. call `multi_approvals.api.take_approval_action` as a non-approver user and confirm it's rejected — to confirm the server-side checks can't be bypassed by skipping the browser.
5. Test concurrent submission attempts (`doc.submit()` via console/API while approvers are still pending) to confirm `before_submit` blocks them with the exact required message.
