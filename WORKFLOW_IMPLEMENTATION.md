# Yazory operating workflows

The supplied `WORKFLOW_SPEC.md` is the organizational specification. This release
replaces the prototype's one-person case and expense status changes with recorded
workflows. It provides working staff-operated stages for all 35 areas. External
payment execution, message delivery and unattended scheduling require runtime
services; a workflow stage does not claim those external actions happened automatically.

## Deploy and initialize

All changes are additive. No existing family, child, contact, expense, document,
pledge, staff account or audit entry is deleted or automatically declared approved.
Use the same production database and secrets as the current deployment.

1. Back up the production database using the hosting provider.
2. Pull the reviewed Git revision in the Replit shell; install requirements.
3. Run `APP_ENV=production python -m flask --app app init-db` before restarting
   web workers. This creates the new workflow, signature, evidence, role, access,
   notice, document-control, ledger, reconciliation and ABCharity tables.
4. Restart/publish that same revision. Verify `/health` and staff sign-in.
5. In **Staff & assignments**, establish the actual individual staff accounts and
   explicit family assignments. In **Operations → Workflow responsibilities**, give
   each person the responsibilities the organization approved.
6. Complete **Organization setup and governance** with banking references, written
   policies, financial limits, and a future policy review date. Finance, board and
   rabbinical reviewers sign independently of the submitter. Before this initial
   policy approval, the owner can establish the initial staff team. After approval,
   newly created accounts stay inactive until their onboarding workflow completes;
   base role changes enter the reviewed access-change workflow.
7. Review existing active cases through the new intake, verification, assessment,
   case approval and support-plan stages. Existing status labels do not fabricate
   historical approvals. New expense approvals require an approved support plan,
   available reviewed collections, and current policies.
8. Link real campaign secrets using **ABCharity donations → Campaign connection**.
   The secret name is stored; the campaign key stays in the runtime environment.
   No campaign key is committed, and no live campaign was imported in development.

For unattended work, configure a single hosting scheduler with the production
environment, outside the autoscaling web workers:

```sh
APP_ENV=production python -m flask --app app sync-abcharity
APP_ENV=production python -m flask --app app workflow-escalate
```

Run imports at the desired interval and escalation at least daily. The code does
not install a Replit scheduler. Overdue queues work immediately; the escalation
command emits idempotent daily in-app notices to the owner, eligible reviewers and
explicit escalation recipient. No email or text is sent by these commands.

## Controls enforced

- Every workflow has a case (or explicit organization scope), owner, due date,
  priority, draft data, stage, revision, independent decisions, evidence and events.
  Submitted content is frozen. A reviewer can return it for a new revision;
  earlier decisions and data changes remain visible. Optimistic versions reject
  stale forms; PostgreSQL row locks serialize case spending.
- Organization administrators manage access but do not inherit financial,
  verification or rabbinical signatures. Reviewers need explicit responsibilities
  and family access. The creator and actual submitter cannot approve their own
  record. Financial workflows and case approval prohibit the same account signing
  different responsibilities. Two case-administrator approvals require two accounts.
  Conflicted users are blocked from the affected case's decisions.
- Referral and consent precede intake review. Verification records statuses for
  income, housing, tuition, utilities, outside assistance, household composition,
  community reference and vendor balances. Changes to household information
  invalidate verification and needs-assessment handoffs.
- The assessment snapshots the household shortfall, income, assistance, approved
  monthly assistance limit, additional family contribution, case administration,
  processing costs, reserve, period and review date. Assistance cannot exceed the
  remaining need after the additional family contribution. The fundraising goal
  uses the approved assistance limit plus organization costs, fees and reserve.
- Only approved support plans activate a case. Monthly review drafts are scheduled
  no later than 30 days out. An overdue review blocks routine new approvals and
  payments. Review decisions can pause assistance/fundraising or create closure,
  verification and document-request follow-ups.
- Pledges remain separate from collections. Only confirmed active monthly pledges
  within their dates enter monthly pledge totals. Legacy contact amounts remain
  preserved but are not automatically treated as confirmed projections.
- Fundraisers see only individually assigned contacts, their outreach/pledge/service
  records and the approved public story. Household accounts, financial workflows,
  medical documents and case ledgers are excluded. Office staff cannot see donor
  collections or case ledgers. Medical, finance and restricted document labels have
  separate access checks; downgrading existing document privacy requires approval.
- Expenses reference an approved plan and verified vendor. The system checks the
  month, plan period, budget already used, collected funds, protected reserve,
  duplicate vendor/invoice pairs and compliance holds. Organization expenses need
  an approved allocation. Above-budget, related-party, direct-family, cash and
  large payments need the additional exception workflow.
- Payment release requires a separate authorized account, an external reference,
  a confirmed external result, and payment-proof evidence attached at release.
  An invoice alone is not payment proof. Cash payments also require a signed
  receipt. Batches contain approved unpaid expenses and enforce the same limits
  and independent release controls across their component expenses.
- The operating ledger is append-only through the application. Posted money cannot
  be canceled by changing a status. Refunds and transfers have separate approvals;
  refunds cannot exceed the original receipt. Transfers post equal opposite entries
  and require documented donor authorization. Bank references are unique and matched
  amounts must agree. Gross ABCharity receipts and processing fees remain separate;
  a net settlement can reconcile the receipt and associated fee together.
- Imported receipts are reviewed before posting. Changed imports do not rewrite
  posted ledger history. They hold further spending until an unusual-activity
  workflow records a finance/compliance/executive-reviewed correction with explicit
  before/after amounts. Correction entries then require bank reconciliation.
- Closing a case requires zero remaining case balance, bank reconciliation,
  resolved expenses, stopped recurring pledges, finance, two case administrators
  and rabbinical approval. Closed household records reject edits. Reopening follows
  verification, reassessment and rabbinical review, returning to review for a new
  support plan; the previous approval period stays intact.

## Scope and external-service boundaries

The staff application records external calls, notifications, receipts, payment
results, supporting files, and decisions. It does not pretend that recording a
stage performs a bank transfer, sends an email/SMS, creates an ABCharity campaign,
or changes a donor's subscription. ABCharity supplies read-only receipt imports;
its documented API does not expose charge attempts, retry/cancel controls, campaign
creation, or authoritative refund/deletion states. Such actions are performed in
those services and recorded with evidence here. Donor service is staff-operated;
there is no donor self-service login in this release.

The ledger is a USD case operating ledger, not a replacement for a double-entry
general ledger or the organization's bank accounts. It does not infer an opening
cash balance from historic expenses or pledges. General unrestricted overhead and
non-USD bank accounting still belong in the accounting system. Reports distinguish
live operational totals from immutable reviewed monthly snapshots; the latter use
posting dates for monthly activity and retain the balances at submission.

Approval thresholds are conservative: the exception workflow includes finance,
two case administrators, rabbinical and executive review. It does not silently
waive required reviewers for smaller exceptions. Account grants and bootstrap
setup are administrator-controlled; external identity checks and training evidence
are attested by staff. Documents and application events are retained, but this is
not a database-administrator-proof archival service.

## Verification

Automated Flask/SQLite tests exercise the full referral-to-closure path, all 35
workflow forms in English/Hebrew/Yiddish, independent signatures, version conflicts,
financial limits, batches, refunds, transfers, evidence, imported-receipt corrections,
role and family isolation, staff onboarding/deactivation, and overdue notices.
ABCharity HTTP behavior is tested with fixtures. Live provider credentials,
PostgreSQL concurrency and the deployed runtime have not been exercised here.
The cloud browser could not reach the local preview; browser visual QA is pending.

## Workflow map

The stage owner named below acts on the current stage to advance it. Draft work
belongs to its assigned owner; named review stages require explicit responsibilities.

| # | Workflow | Stages |
| --- | --- | --- |
| 1 | Organization setup and governance (`governance`) | Draft → Finance review (Finance administrator) → Board approval (Board member) → Rabbinical review (Rabbinical supervisor) → Approved |
| 2 | Referral (`referral`) | Draft → Contact attempted → Consent received → Intake scheduled → Completed |
| 3 | Intake review (`intake`) | Draft → Family review → Submitted for verification (Intake administrator) → Completed |
| 4 | Information verification (`verification`) | Draft → Verification (Verifier) → Case review (Case administrator) → Completed |
| 5 | Needs assessment (`assessment`) | Draft → Finance review (Finance administrator) → Rabbinical review (Rabbinical supervisor) → Approved |
| 6 | Case approval (`case_approval`) | Draft → Verification (Verifier) → Finance review (Finance administrator) → Two case administrators (Case administrator, 2 people) → Rabbinical review (Rabbinical supervisor) → Executive review (Executive leadership) → Approved |
| 7 | Family-support plan (`support_plan`) | Draft → Family confirmation → Case review (Case administrator) → Finance review (Finance administrator) → Active |
| 8 | Case review and renewal (`review`) | Draft → Finance review (Finance administrator) → Case review (Case administrator) → Rabbinical review (Rabbinical supervisor) → Completed |
| 9 | Supporter-tree review (`supporter`) | Draft → Relationship verified (Case administrator) → Contact permitted (Case administrator) → Assigned to fundraiser (Fundraising administrator) → Ready for outreach |
| 10 | Fundraising-plan approval (`fundraising_plan`) | Draft → Privacy review (Compliance administrator) → Case review (Case administrator) → Active |
| 11 | Supporter outreach (`outreach`) | Draft → Contact attempted → Reached → Follow-up → Completed |
| 12 | Pledge (`pledge`) | Draft → Confirmed → Payment setup pending → Active |
| 13 | Donation collection (`collection`) | Draft → Payment scheduled → Processing (Finance administrator) → Collected (Finance administrator) → Posted (Finance administrator) → Receipt issued (Finance administrator) → Reconciled (Finance administrator) |
| 14 | Donor service (`donor_service`) | Draft → Assigned → Resolved → Donor notified → Completed |
| 15 | Expense request (`expense`) | Draft → Submitted → Case review (Case administrator) → Finance review (Finance administrator) → Approved → Scheduled (Payment batch approver) → Payment release (Payment releaser) → Paid (Finance administrator) → Reconciled |
| 16 | Expense exception approval (`exception_approval`) | Draft → Finance review (Finance administrator) → Two case administrators (Case administrator, 2 people) → Rabbinical review (Rabbinical supervisor) → Executive review (Executive leadership) → Approved |
| 17 | Organization-expense allocation (`allocation`) | Draft → Case review (Case administrator) → Finance review (Finance administrator) → Approved |
| 18 | Vendor approval (`vendor`) | Draft → Verification (Verifier) → Payment details verified (Finance administrator) → Approved |
| 19 | Payment batch (`payment_batch`) | Draft → Finance review (Finance administrator) → Batch approved (Payment batch approver) → Release recorded (Payment releaser) → Completed |
| 20 | Bank reconciliation (`reconciliation`) | Draft → Finance review (Finance administrator) → Matched (Finance administrator) → Reconciled |
| 21 | Refund or chargeback (`refund`) | Draft → Finance review (Finance administrator) → Two case administrators (Case administrator, 2 people) → Release recorded (Payment releaser) → Completed |
| 22 | Inter-case transfer (`transfer`) | Draft → Finance review (Finance administrator) → Rabbinical review (Rabbinical supervisor) → Transfer posted (Payment releaser) → Completed |
| 23 | Emergency assistance (`emergency`) | Draft → Verification (Verifier) → Rabbinical review (Rabbinical supervisor) → Case review (Case administrator) → Immediate payment (Payment releaser) → Documentation review (Compliance administrator) → Completed |
| 24 | Complaint and safeguarding (`complaint`) | Draft → Risk classified (Compliance administrator) → Investigation (Compliance administrator) → Decision (Executive leadership) → Corrective action (Compliance administrator) → Completed |
| 25 | Conflict of interest (`conflict`) | Draft → Privacy review (Compliance administrator) → Recusal recorded (Compliance administrator) → Completed |
| 26 | Unusual activity (`unusual`) | Draft → Payment held (Compliance administrator) → Finance review (Finance administrator) → Privacy review (Compliance administrator) → Decision (Executive leadership) → Completed |
| 27 | User onboarding (`onboarding`) | Draft → Verification (Verifier) → Training completed (Compliance administrator) → Access approved (Executive leadership) → Completed |
| 28 | Staff departure or role change (`access_change`) | Draft → Manager approval (Executive leadership) → Access reviewed (Compliance administrator) → Assignments transferred (Executive leadership) → Completed |
| 29 | Task and escalation (`task`) | Draft → In progress → Waiting on third party → Completed |
| 30 | Document review (`document`) | Draft → Classified → Privacy review (Compliance administrator) → Reviewed (Case administrator) → Approved |
| 31 | Per-case transparency report (`case_report`) | Draft → Finance review (Finance administrator) → Two case administrators (Case administrator, 2 people) → Rabbinical review (Rabbinical supervisor) → Completed |
| 32 | Organization-wide report (`org_report`) | Draft → Finance review (Finance administrator) → Executive review (Executive leadership) → Completed |
| 33 | Audit (`audit`) | Draft → Period locked (Read-only auditor) → Transactions reviewed (Read-only auditor) → Management response (Executive leadership) → Corrective action (Compliance administrator) → Audit closed (Read-only auditor) → Completed |
| 34 | Case closure (`closure`) | Draft → Collections stopping (Fundraising administrator) → Financial reconciliation (Finance administrator) → Finance review (Finance administrator) → Two case administrators (Case administrator, 2 people) → Rabbinical review (Rabbinical supervisor) → Closed |
| 35 | Reopening a case (`reopening`) | Draft → Verification (Verifier) → Finance review (Finance administrator) → Rabbinical review (Rabbinical supervisor) → Reopened |
