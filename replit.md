# Replit handoff

## Project
Yazory supports households facing illness by coordinating family/community pledges and daily expenses. Preserve the Python/Flask stack and existing structure.

## Permanent language and brand requirement
Every future screen, feature, system message, letter, and receipt must ship together in English, Hebrew, and the current heimish Yiddish, using the approved Yazory helping-hands logo and the shared navy, gold, and cream design system. English must remain left-to-right; Hebrew and Yiddish must remain right-to-left. Keep the current Yiddish wording unless the user explicitly approves revisions. Never present a receipt template or generated receipt as proof that payment occurred; it is documentation only and must be clearly labeled accordingly.

## Start
Pull GitHub `main`. Press Run, which executes `pip install -r requirements.txt && python app.py`. Python 3.11+, port 5000, entry point `app.py`. No frontend build required. Templates are in `templates/`; CSS is in `static/style.css`.

With no staff credentials, the application runs a fictional demo using a local SQLite database. Do not use demo mode for real household information. No credentials have been invented or committed.

## Database / staff setup
For shared PostgreSQL, set `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`, and `SESSION_SECRET` in Secrets; follow README for private hash generation and explicit `flask --app 'app:create_app()' init-db`. The configured credentials bootstrap the owner organization administrator idempotently; additional individual staff accounts and family assignments are administered in-app by organization administrators. Do not paste secrets into Git or chat. If the import generated different port/workflow settings, align them to port 5000 without changing the application stack.

## Permanent role requirement
Preserve four roles: `organization_admin` (all records, financial approvals/payments, case transitions, staff and assignments), `family_admin` (assigned families' household, children, documents, supporters/pledges, and expense requests), `office_employee` (assigned household intake/profile/children/documents and expense requests; intake is atomically self-assigned), and `fundraiser` (assigned families only in the dedicated fundraising workspace, limited to supporter contacts, outreach, pledges, family name/reference, and aggregate pledge). Fundraisers must never receive household address/phone, children, circumstances/medical notes, documents, expenses, general family pages, organization dashboard/activity/settings/staff. Organization-admin-only routes must prevent self-escalation and self-assignment; retain bootstrap owner and last-admin protections. Enforce capabilities server-side on direct ID routes, scoped by explicit `FamilyAssignment` for every non-admin role.

## Verification
Install requirements and `pytest==9.1.1`, then `python -m pytest -q`. `/health` checks database connectivity. Verify desktop and mobile previews. Test intake → Under review → Active, add supporters and an expense, approve it, then record payment with an external reference.

## Publishing
Not yet authorized or performed in this setup. `.replit` includes a Gunicorn publishing command with APP_ENV=production. It refuses anonymous demo mode and local SQLite in production. Complete the README production preparation items before real operational use. No external payment or messaging integrations exist yet.
