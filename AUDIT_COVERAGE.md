# Yazory application audit coverage — 2026-09-23

This is a coverage ledger, not a certification that every click has passed. The
repository has 213 decorated HTTP endpoints in 15 Python modules. A route can
serve multiple states and buttons; counting routes does not count interactions.

## Evidence and coverage

| Area | Live browser | Isolated verification | Remaining work |
| --- | --- | --- | --- |
| Overview, cases, family profiles, intake, applications | Admin screens, tabs, filters, profile/edit navigation inspected | Full suite includes intake and case tests | Every field persistence path and non-admin navigation |
| Supporters, fundraising, collections, communications, tasks | Admin screens and representative actions inspected | Callback, pledge, communications, task and role tests | All variants of message delivery, cross-case identity and action destinations |
| Operations, expenses, approvals, payouts, reports | Queues, detail, tabs and financial figures inspected | Workflow and payout tests; local payout guard tests | Each workflow stage and actual provider settlement/reconciliation |
| Staff, assignments, notifications, controls | Admin screens and representative actions inspected | Role and invitation tests | Real staff logins for each role, revocation in an active session |
| Partner network and directories | Partner overview, organization detail, contacts tab; duplicate askan observed | 19 targeted portal/partner/directory/role tests passed | Remaining live edits, coordination forms and every directory control |
| Applicant and donor portals | Login links visible, no authenticated portal session | Portal authorization, magic links, messages, pledge and receipt tests passed | Real applicant/donor session and provider-backed payment flow |
| Public pages, sponsorships, language/PWA | Representative pages and sponsor display inspected | Public, sponsorship and PWA tests in full suite | Complete device/locale visual pass |

Full run: **355 passed, 10 failed, 3 warnings** (`python -m pytest -q`,
2026-09-23). Focused portal/partner/directory/role run: **19 passed**.

## Confirmed findings requiring work

1. **Financial source of truth / payout exposure (critical).** In the live
   YZ-0001 record, legacy available funds showed $398.78 while the operations
   ledger showed $298.78 after a $100 organization expense. A local, unpublished
   payout guard conservatively uses the smaller available figure and checks
   Stripe and check payouts. Reconcile ledger definitions and historical data.
2. **Slow page load and write-on-read (high).** Live Communications took roughly
   9–10 seconds, Tasks roughly 8 seconds, and Supporters roughly 5–6 seconds.
   Communications and Supporters render hundreds of controls. GET requests for
   Tasks and Communications perform repair/backfill writes. Profile the queries,
   paginate or defer sections, and move repairs out of GET requests.
3. **Conflicting totals (high).** Monthly pledged and received figures vary
   across profile, fundraising, operations and reports. The local, unpublished
   fundraising change excludes one-time gifts from monthly pledges. Manual
   receipts and ABCharity receipts have distinct accounting semantics and must
   be reconciled explicitly rather than summed indiscriminately.
4. **Navigation context (high).** Live task, staff and supporter actions were
   observed opening the wrong panel or losing context. Local, unpublished
   changes address several paths; the user's specific "contact user returns to
   circle support list" example has not yet been reproduced.
5. **Duplicate askan identity (medium).** Live partner organization contact
   picker contained two distinct options, IDs 3 and 4, each labelled
   `יואל גרינוואלד · 8452389414`. Existing data needs a reviewed merge and
   all askan creation paths need normalized identity checks.
6. **Workflow escalation (medium).** `test_escalation_is_idempotent_and_evidence_is_preserved`
   fails: a second same-day CLI run reports one more escalation. The command
   increments its count even when notification creation finds no eligible
   recipient. Clarify intended counting and make the command idempotent.
7. **Workflow assignment setup (high).** The inspected live staff had no workflow
   responsibilities assigned although later collection stages require a
   finance reviewer. Verify role setup and approval handoff with real accounts.

## Ten full-suite failures, triage

| Failures | Current interpretation |
| --- | --- |
| Provider expense visibility; father/in-law network edit; intake anchor; expandable supporter list | Assertions expect old sections/markup; verify replacement interactions before updating tests. |
| Cross-case phone identity and receipt history | Tests submit the old `phone` field while current add form accepts `cell_phone`/`home_phone`; check legacy API compatibility and migrated records. |
| Staff assignment revocation | Test submits `assign` twice; current endpoint requires explicit `operation=revoke`. Test expectation is obsolete, but real revoke still needs a dedicated test. |
| Directory print; phone display | Tests expect inline `onclick` and no raw number anywhere, including form input. Inspect print behavior and displayed text separately. |
| Escalation idempotency | Reproduced failing behavioral test; investigate/fix. |

The donor portal has separate pledge cards for each family. An isolated update
changed only the selected family's pledge; this matches the current UI and is
**not** recorded as a defect. Separately verify whether an updated pledge is
expected to alter an existing Stripe recurring payment; the UI currently has
a separate payment-management action.

The live administrator browser session expired while opening a partner edit
form. Real message sends, permission changes, payments and destructive actions
have not been performed against production data. These paths need isolated
tests and, where appropriate, a controlled staging exercise before full
coverage can be claimed.
