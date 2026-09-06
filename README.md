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
- Overview, unified expense approval queue, family search, and actor/timestamp activity history.

Pledges are commitments, not collected revenue. Payment recording does not transfer money. Monthly overview totals use expense budget month; they are not bank reconciliation or cash-basis accounting reports.

## Production preparation

Deployment intentionally refuses to start without all of these Replit Secrets:

| Secret | Purpose |
| --- | --- |
| `DATABASE_URL` | Persistent PostgreSQL connection, separate from demo |
| `ADMIN_EMAIL` | Initial staff sign-in identity |
| `ADMIN_PASSWORD_HASH` | Werkzeug password hash, never the plaintext password |
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

This is an initial application, not a completed production launch. Before real operational use, complete individual staff accounts and roles (including separation of requesters and approvers), password recovery and durable login rate limiting, database backup/restore verification, deployment validation, and the organization's data retention/access policies. Current authentication is a single bootstrap staff account. The activity log is application history, not a tamper-proof financial ledger. New children and donor contact identity details currently cannot be edited or deleted; family profiles and pledge status/amount can be edited.

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
