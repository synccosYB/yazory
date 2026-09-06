# Yazory

An initial family-support case management application. Built with Python, Flask, SQLAlchemy, server-rendered HTML, and responsive CSS. GitHub stores the code; Replit is the intended runtime.

## Run in Replit

Pull `main` into the imported project, then press **Run**. The `.replit` configuration installs requirements and starts `python app.py` on `0.0.0.0:5000`. Without staff credentials, it opens a clearly labeled demo with fictional sample records and a local SQLite database. No external services or secrets are needed for the demo. Do not enter real household information into demo mode.

If Replit has already provisioned a `DATABASE_URL`, configure staff credentials and initialize that database before running; anonymous demo mode intentionally refuses shared databases.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000. Local demo data is stored in `instance/yazory-demo.db` and excluded from Git.

## Included workflows

- Family intake and profile editing: individual, spouse, father, in-laws, address, phone, rabbi, weekday and Shabbos shul, household circumstances.
- Children: name, age, grade, school, tuition department contact.
- Donor network: siblings, spouse’s siblings, cousins, school/yeshivah friends, and other supporters; outreach status and monthly pledges.
- Case workflow: Intake → Under review → Active or Declined. Active cases can be paused or closed; closed/declined cases can return to review.
- Expense requests: category, payee, budget month, amount, and notes. Organization expenses can be assigned to a case.
- Expense workflow: Requested → Approved or Declined; Approved → Paid or Voided. Only active cases can be approved/paid. A payment reference is mandatory to mark Paid. Terminal expense states cannot be changed.
- Individual staff accounts use `organization_admin`, `family_admin`, `office_employee`, or `fundraiser`. Organization administrators have organization-wide case, financial workflow, account, and assignment authority. Family administrators manage assigned household profiles, children, documents, supporter contacts/pledges, and expense requests. Office employees manage assigned household intake/profiles, children, documents, and expense requests only; each intake they create is assigned to them atomically. Fundraisers use the dedicated assigned-family fundraising workspace for supporter contacts, outreach, and pledges only; it intentionally excludes confidential household details, documents, expenses, and general family pages. All non-admin family access is an explicit `FamilyAssignment`; only organization administrators manage assignments.
- Overview, unified expense approval queue, family search, and actor/timestamp activity history.

Pledges are commitments, not collected revenue. Payment recording does not transfer money. Monthly overview totals use expense budget month; they are not bank reconciliation or cash-basis accounting reports.

## Production preparation

Deployment intentionally refuses to start without all of these Replit Secrets:

| Secret | Purpose |
| --- | --- |
| `DATABASE_URL` | Persistent PostgreSQL connection, separate from demo |
| `ADMIN_EMAIL` | Bootstrap owner organization-administrator identity |
| `ADMIN_PASSWORD_HASH` | Bootstrap owner Werkzeug password hash, never the plaintext password |
| `SESSION_SECRET` | Stable random secret, at least 32 characters |

Generate a session secret privately with `python -c "import secrets; print(secrets.token_hex(32))"`.
Generate a password hash privately with:

```sh
python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Staff password: ')))"
```

Initialize the configured database once:

```sh
APP_ENV=production flask --app 'app:create_app()' init-db
```

The publishing command in `.replit` sets `APP_ENV=production` and runs Gunicorn on port 5000. Production enforces secure cookies, staff authentication, CSRF protection, and PostgreSQL. Demo records are never seeded into PostgreSQL. Schema creation is explicit and nondestructive; future schema changes will require versioned migrations.

The configured bootstrap identity is created idempotently as the owner organization administrator and its existing password hash is never overwritten. Organization administrators create additional individual staff accounts and manage explicit family assignments. Table creation is idempotent and preserves existing records; use versioned migrations for future column changes. This is an initial application, not a completed production launch. Before real operational use, complete password recovery and durable login rate limiting, database backup/restore verification, deployment validation, and the organization's data retention/access policies. The activity log is application history, not a tamper-proof financial ledger. New children and donor contact identity details currently cannot be edited or deleted; family profiles and pledge status/amount can be edited.

Not yet implemented: automated donation collection, receipts, bank reconciliation, document uploads, invitations, email/SMS delivery, full bookkeeping, recurring expense generation, or automated backups. No production publishing or external financial actions are performed by this repository setup.

## Tests

```sh
pip install pytest==9.1.1
python -m pytest -q
```

Tests cover page rendering, intake-to-payment transitions, cent-accurate money validation, CSRF, escaping, staff login/logout, and production configuration guards.

## Shared language and brand system

English, Hebrew, and heimish Yiddish use the same Jinja templates, CSS components, and approved helping-hands logo (`static/yazory-logo.png`). A language switcher appears on every page and remembers the choice in the session, including sign-in/sign-out. Hebrew and Yiddish use RTL via logical CSS properties; amounts and contact fields retain readable LTR formatting. Switching preserves the current page and filters. Stored names, notes, audit records, amounts, and internal status values are never machine-translated or rewritten.

`translations.py` owns interface translations. Add new labels there in both languages and render them with `_()`; do not create language-specific page copies or stylesheets. Navy, gold, and cream theme values are shared across all languages. The supplied logo is copied unchanged from the approved brand asset. Existing activity descriptions and staff-entered content retain their original language.

## Sequential intake and compact pages

New and edited family intake uses seven short steps in English, Hebrew and
Yiddish. New forms do not prefill providers, account numbers, income, benefits or
household amounts. Account numbers remain text to preserve leading zeros.
Budget amounts are monthly USD, stored as integer cents; unknown and zero are
separate values. Utility, grocery, mosdos and other accounts are added one at a
time. Assistance supports food stamps and additional named monthly sources.
Authorized staff revisit the same steps through Edit profile. Fundraisers cannot
access this confidential intake or budget information.

Before running this version against an existing PostgreSQL database, run:

```bash
APP_ENV=production python -m flask --app app init-db
```

This uses the existing additive initialization command to create the new
`household_intake` table and preserves existing tables and records. Back up the
database using the hosting provider before schema changes. Do not copy demo data
into the operational database.

Desktop pages use compact spacing, profile tabs and viewport-sized table pages.
Small screens and zoom retain content access rather than clipping fields. Future
features must use short steps, tabs or pagination instead of growing a desktop
page vertically. All development belongs in GitHub; Replit is for shell-based
synchronization, running and deployment only. Never use Replit Agent to develop.

## ABCharity campaign donations

Each family can link one ABCharity campaign. Organization administrators configure
connections; assigned family administrators and fundraisers can read and sync
receipts and link imported donors to existing circle-of-support contacts. Office
employees and unassigned users cannot open donation pages. Fundraisers never see
expense comparisons. Pledges and expense approvals remain unchanged.

Deployment (additive schema; existing records preserved):

1. Install `requirements.txt`, then run `APP_ENV=production python -m flask --app app:create_app init-db`
   against the existing production database before restarting the app.
2. Create the family campaign in ABCharity. Copy that campaign's API key into a
   server secret such as `ABCHARITY_KEY_FAMILY_1`. Never commit a key or put it in a
   client-side setting. Raw keys and percent-encoded keys are both accepted.
3. From the family profile, open **ABCharity donations → Campaign connection**.
   Enter the campaign's numeric ID, label, actual currency and the secret's NAME.
   Currency is declared by the administrator: the supplied API documentation does
   not specify the campaign-info response schema, so it cannot be inferred safely.
   Save to validate the donation response and import. An empty valid response
   confirms the key works but cannot establish campaign ID membership until the
   first receipt arrives. Every receipt must match the configured campaign ID.
4. Use **Sync donations** anytime. For unattended imports, configure the hosting
   scheduler to run `APP_ENV=production python -m flask --app app:create_app sync-abcharity`
   every 15 minutes with the same database and secrets. Do not run a scheduler
   inside each autoscaling web worker. No schedule is installed by this code.

Imports use unique campaign/donation IDs and refresh changed receipt values in a
single transaction. An invalid receipt, mismatched campaign ID, duplicate ID in a
response, incomplete response or 100,000-result cap rejects the entire import.
The last successful sync stays visible alongside a safe error; failures never
include credential URLs. Concurrent collisions roll back and can be retried.
Full reconciliation retains receipts absent from a later API response because
the documentation supplies no deletion/refund status. Investigate such changes
with ABCharity; do not treat this ledger as a bank balance. Large campaigns may
need a longer web-worker timeout or the scheduled CLI command.

Donors match by normalized email within a campaign; without email, each receipt
has a distinct donor record. Staff can link to a same-family supporter without
changing pledges or inventing relationship data. Anonymous donor identity and
notes are hidden on donation screens. Subscription means only that the API
marks the receipt as a subscription; no active mandate, next charge, failed
payment, subscription management, campaign creation or write API is provided.
Amounts are stored as integer cents and displayed in the configured currency;
only USD campaigns show net receipts less the family's recorded paid expenses.
API behavior is covered by mocked fixtures based on the documentation; live
family campaign credentials must be verified during setup. The Yomim Noraim key
supplied during planning is deliberately not embedded or linked to a family.
