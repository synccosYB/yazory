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
- Connected workspace pages: Overview, `/cases` (with `/families` compatibility), supporters, fundraising, collections, expenses, approvals, reports, people/access, and controls. Organization controls persist editable permitted expense categories and child age-band estimates.
- Collections use manual `Receipt` records linked to the supporter and case. A pledge is never a receipt; receipt and expense-payment entries document external activity only and never move money. ABCharity is intentionally not connected and the fundraising page truthfully exposes no external action.

Pledges are commitments, not collected revenue. Payment recording does not transfer money. Monthly overview totals use saved records and expense budget month; they are not bank reconciliation or cash-basis accounting reports. Profile shortfall separates saved income, entered household bills, configured child estimates, and actual child amounts so estimates are never double counted.

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

For an existing deployment, back up first and run the additive migration before
starting the new application version:

```sh
APP_ENV=production flask --app 'app:create_app()' migrate-db
```

`migrate-db` only calls SQLAlchemy's idempotent `create_all()` to add missing
tables (including receipts and organization settings); it never drops or
rewrites existing records. Use versioned migrations for future column changes.

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
