# Priority 0 fixes and rollout checks

## Balance and payouts (tasks 01–02)

The family profile and payout list now display the same conservative available
balance used to authorize checks and Stripe payouts. When workflow enforcement
is enabled, that balance is the lower of the legacy case calculation and the
operations ledger's available balance. A separate adjustment/hold amount
explains the difference between legacy collections minus disbursements and the
spendable balance. This prevents the YZ-0001 $100 organization expense from
appearing available for a payout on the family profile.

The check and Stripe payout handlers lock the family before calculating
availability. Both reject amounts above that balance. Stripe sends use a
processor idempotency key derived from the payout record ID. Do not infer that
an ambiguous processor response means no money moved: investigate it with the
processor before retrying. A posted operations ledger entry, legacy receipt,
ABCharity net receipt, reserved amount and voided payout should each be
reconciled before the display can be treated as a complete historical ledger.

No schema migration is required for these changes. After deployment, compare
the case ledger, family profile and payout list for YZ-0001 and a second case,
then test insufficient-funds rejection using a controlled non-production case.

## Roles, revocation and approval handoff (tasks 03–05)

Tests cover an office employee's permitted case versus a private case and a
fundraiser's restricted case view. A new test revokes a staff assignment while
the employee is still signed in, then checks family view, edit, messaging,
ledger, coordination, network and expense creation. Deactivation clears the
session on the next request.

The Workflow responsibilities screen now requires an explicit Grant or Revoke
action and lists required roles without an active reviewer. Grants do **not**
assign a family: both the responsibility and a case assignment are needed to
review a family workflow. A test verifies the finance reviewer loses signing
ability when either is removed. An inactive user cannot receive a new grant.

After deployment, an organization administrator must assign the appropriate
active individuals to Finance administrator and other missing responsibilities,
and separately assign their permitted cases. A submitter cannot approve their
own financial work. Review these assignments with the owner; no staff member
was silently given additional access by this change.

## Remaining boundaries

These tests use an isolated database. They do not substitute for a real staff
login and controlled payment/provider exercise. Historical financial entries
and duplicate records have not been rewritten. The broader audit and older
failing screen tests remain tracked in `AUDIT_COVERAGE.md`.
