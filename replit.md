# Replit handoff

## Project
Yazory supports households facing illness by coordinating family/community pledges and daily expenses. Preserve the Python/Flask stack and existing structure.

## Start
Pull GitHub `main`. Press Run, which executes `pip install -r requirements.txt && python app.py`. Python 3.11+, port 5000, entry point `app.py`. No frontend build required. Templates are in `templates/`; CSS is in `static/style.css`.

With no staff credentials, the application runs a fictional demo using a local SQLite database. Do not use demo mode for real household information. No credentials have been invented or committed.

## Database / staff setup
For shared PostgreSQL, set `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`, and `SESSION_SECRET` in Secrets; follow README for private hash generation and explicit `flask --app 'app:create_app()' init-db`. Do not paste secrets into Git or chat. If the import generated different port/workflow settings, align them to port 5000 without changing the application stack.

## Verification
Install requirements and `pytest==9.1.1`, then `python -m pytest -q`. `/health` checks database connectivity. Verify desktop and mobile previews. Test intake → Under review → Active, add supporters and an expense, approve it, then record payment with an external reference.

## Publishing
Not yet authorized or performed in this setup. `.replit` includes a Gunicorn publishing command with APP_ENV=production. It refuses anonymous demo mode and local SQLite in production. Complete the README production preparation items before real operational use. No external payment or messaging integrations exist yet.
