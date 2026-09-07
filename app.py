import os
import secrets
import hmac
import re
import hashlib
from html import escape
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, func, UniqueConstraint, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from translations import LANGUAGES, translate, translate_audit

from intake import validate_intake, intake_for_form
from budget_report import household_report
import child_budget
from email_service import deliver

db = SQLAlchemy()

class Family(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    spouse = db.Column(db.String(160), default='')
    phone = db.Column(db.String(80), default='')
    address = db.Column(db.String(300), default='')
    city = db.Column(db.String(120), default='')
    state = db.Column(db.String(80), default='')
    zip_code = db.Column(db.String(20), default='')
    father = db.Column(db.String(160), default='')
    inlaws = db.Column(db.String(160), default='')
    inlaws_maiden_name = db.Column(db.String(160), default='')
    inlaws_family = db.Column(db.Text, default='')
    rabbi = db.Column(db.String(160), default='')
    rabbi_phone = db.Column(db.String(80), default='')
    weekday_shul = db.Column(db.String(160), default='')
    shabbos_shul = db.Column(db.String(160), default='')
    shul_gabbai = db.Column(db.String(160), default='')
    shul_gabbai_phone = db.Column(db.String(80), default='')
    circumstances = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='Intake', nullable=False)
    gabbais = db.relationship('ShulGabbai', backref='family', lazy=True,
                              cascade='all, delete-orphan', order_by='ShulGabbai.id')
    children = db.relationship('Child', backref='family', lazy=True)
    contacts = db.relationship('Contact', backref='family', lazy=True)
    expenses = db.relationship('Expense', backref='family', lazy=True)
    documents = db.relationship('Document', backref='family', lazy=True, cascade='all, delete-orphan')
    assignments = db.relationship('FamilyAssignment', backref='family', lazy=True, cascade='all, delete-orphan')

    @property
    def full_address(self):
        locality = ', '.join(part for part in (self.city, self.state) if part)
        if self.zip_code:
            locality = f'{locality} {self.zip_code}'.strip()
        return ', '.join(part for part in (self.address, locality) if part)

class HouseholdIntake(db.Model):
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), primary_key=True)
    data = db.Column(db.JSON, nullable=False, default=dict)
    family = db.relationship('Family', backref=db.backref('intake_record', uselist=False))

class ShulGabbai(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(80), default='')

class OrganizationSetting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.JSON, nullable=False)


class HouseholdBudget(db.Model):
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), primary_key=True)
    data = db.Column(db.JSON, nullable=False, default=dict)


class StaffUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='family_admin')
    name = db.Column(db.String(160), nullable=False, default='')
    status = db.Column(db.String(20), nullable=False, default='active', index=True)
    invited_at = db.Column(db.DateTime, nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    assignments = db.relationship('FamilyAssignment', backref='staff_user', lazy=True, cascade='all, delete-orphan')

class FamilyAssignment(db.Model):
    __table_args__ = (UniqueConstraint('staff_user_id', 'family_id', name='uq_family_assignment'),)
    id = db.Column(db.Integer, primary_key=True)
    staff_user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)


class AccountToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False, index=True)
    purpose = db.Column(db.String(20), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True)
    staff_user = db.relationship('StaffUser', foreign_keys=[staff_user_id])


class EmailMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False, index=True)
    recipient = db.Column(db.String(254), nullable=False, index=True)
    subject = db.Column(db.String(300), nullable=False)
    text_body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    provider_id = db.Column(db.String(200), default='')
    error = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    staff_user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=True, index=True)

class Child(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    grade = db.Column(db.String(80), default='')
    school = db.Column(db.String(160), nullable=False)
    tuition_contact = db.Column(db.String(300), default='')
    married = db.Column(db.Boolean, default=False, nullable=False)
    spouse_name = db.Column(db.String(160), default='')

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    relationship = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(80), default='')
    # The same real person may support several cases.  This stable key keeps the
    # case-specific relationship rows linked to one billing identity.
    supporter_key = db.Column(db.String(200), nullable=False, default='', index=True)
    parent_contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=True, index=True)
    parent_connection = db.Column(db.String(20), nullable=False, default='')
    parent_supporter = db.relationship('Contact', remote_side=[id],
                                     backref=db.backref('nested_supporters', lazy=True))
    monthly_cents = db.Column(db.Integer, default=0, nullable=False)
    pledge_frequency = db.Column(db.String(20), nullable=False, default='Monthly')
    status = db.Column(db.String(30), default='To contact', nullable=False)
    receipts = db.relationship('Receipt', backref='contact', lazy=True)
    children = db.relationship('ContactChild', backref='contact', lazy=True,
                               cascade='all, delete-orphan', order_by='ContactChild.id')

    @property
    def monthly_equivalent_cents(self):
        if self.pledge_frequency == 'Weekly':
            return round(self.monthly_cents * 52 / 12)
        if self.pledge_frequency == 'One time':
            return 0
        return self.monthly_cents

class ContactChild(db.Model):
    """A supporter's child, shown in the case network as a niece or nephew."""
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    spouse_name = db.Column(db.String(160), default='')
    phone = db.Column(db.String(80), default='')

class Receipt(db.Model):
    """A manual record of money reported received; it never collects money."""
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=False, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    received_on = db.Column(db.Date, nullable=False,
                            default=lambda: datetime.now(timezone.utc).date())
    reference = db.Column(db.String(200), default='')
    note = db.Column(db.Text, default='')
    recorded_by = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True)
    recorder = db.relationship('StaffUser', foreign_keys=[recorded_by])

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    payee = db.Column(db.String(160), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    month = db.Column(db.String(7), nullable=False)
    note = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='Requested', nullable=False)
    payment_reference = db.Column(db.String(200), default='')

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    actor = db.Column(db.String(160), nullable=False)
    action = db.Column(db.String(300), nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'))

FAMILY_TRANSITIONS = {'Intake': ['Under review'], 'Under review': ['Intake', 'Active', 'Declined'], 'Active': ['Paused', 'Closed'], 'Paused': ['Active', 'Closed'], 'Closed': ['Under review'], 'Declined': ['Under review']}
EXPENSE_TRANSITIONS = {'Requested': ['Approved', 'Declined'], 'Approved': ['Paid', 'Voided'], 'Paid': [], 'Declined': [], 'Voided': []}
DEFAULT_CATEGORIES = ['Tuition', 'Groceries', 'Butcher', 'Rent / mortgage', 'Utilities', 'Transportation', 'Organization expense', 'Other']
DEFAULT_CHILD_BANDS = [{'min_age': 0, 'max_age': 5, 'amount_cents': 0},
                       {'min_age': 6, 'max_age': 12, 'amount_cents': 0},
                       {'min_age': 13, 'max_age': 30, 'amount_cents': 0}]
CATEGORIES = DEFAULT_CATEGORIES
RELATIONSHIPS = ['Sibling', 'Nephew', 'Spouse’s sibling', 'Child’s in-law family', 'First cousin', 'Second cousin', 'Yeshivah / school friend', 'Friend', 'Other']
LEGACY_RELATIONSHIPS = {'In-law’s maiden family'}
CONTACT_STATUSES = ['To contact', 'Contacted', 'Pledged', 'Paused', 'Declined']
PLEDGE_FREQUENCIES = ['Monthly', 'Weekly', 'One time']

def valid_werkzeug_password_hash(value):
    if not value or any(character.isspace() for character in value):
        return False
    return bool(
        re.fullmatch(r'scrypt:\d+:\d+:\d+\$[^$]+\$[^$]+', value)
        or re.fullmatch(r'pbkdf2:[^:$]+:\d+\$[^$]+\$[^$]+', value)
    )

def create_app(test_config=None):
    app = Flask(__name__)
    production = os.getenv('APP_ENV') == 'production'
    database = os.getenv('DATABASE_URL', 'sqlite:///yazory-demo.db')
    if database.startswith('postgres://'):
        database = database.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database.startswith('postgresql://'):
        database = database.replace('postgresql://', 'postgresql+psycopg://', 1)
    secret = os.getenv('SESSION_SECRET', '')
    password_hash = os.getenv('ADMIN_PASSWORD_HASH', '')
    admin_email = os.getenv('ADMIN_EMAIL', '')
    demo = not password_hash
    if production and (demo or len(secret) < 32 or not admin_email or not database.startswith('postgresql+psycopg://') or not valid_werkzeug_password_hash(password_hash)):
        raise RuntimeError('Production requires PostgreSQL DATABASE_URL, ADMIN_EMAIL, a valid Werkzeug ADMIN_PASSWORD_HASH and SESSION_SECRET (32+ characters).')
    app.config.update(SECRET_KEY=secret or secrets.token_hex(32), SQLALCHEMY_DATABASE_URI=database,
                      SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      # Replit may restart its managed Postgres service while a
                      # deployment is still serving. Validate pooled connections
                      # before reuse and periodically replace long-lived ones.
                      SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True, 'pool_recycle': 300},
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=production,
                      PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
                      MAX_CONTENT_LENGTH=10*1024*1024, DEMO=demo,
                      ADMIN_EMAIL=admin_email, ADMIN_PASSWORD_HASH=password_hash,
                      RESEND_API_KEY=os.getenv('RESEND_API_KEY', ''),
                      EMAIL_FROM=os.getenv('EMAIL_FROM', ''),
                      APP_BASE_URL=os.getenv('APP_BASE_URL', '').rstrip('/'))
    if test_config:
        app.config.update(test_config)
    if app.config['DEMO'] and not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        raise RuntimeError('Demo mode must use a local SQLite database, never a shared production database.')
    db.init_app(app)
    app.jinja_env.globals['_'] = translate
    app.jinja_env.globals['_audit'] = translate_audit

    @app.template_filter('money')
    def money(cents):
        return f'${(cents or 0)/100:,.2f}'

    def supporter_key(name, phone):
        """Identify one supporter across cases, preferring a normalized phone."""
        digits = re.sub(r'\D', '', phone or '')
        if len(digits) >= 7:
            return 'phone:' + digits[-10:]
        normalized_name = re.sub(r'[^\w]+', '', (name or '').casefold())
        return 'name:' + normalized_name

    def utcnow():
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def account_token(user, purpose, hours, created_by=None):
        raw = secrets.token_urlsafe(32)
        # Only a digest is retained, so a database disclosure cannot expose a live link.
        db.session.add(AccountToken(staff_user_id=user.id, purpose=purpose,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=utcnow() + timedelta(hours=hours),
            created_by=created_by.id if created_by else None))
        return raw

    def token_record(raw, purpose):
        if not raw:
            return None
        return db.session.scalar(select(AccountToken).where(
            AccountToken.token_hash == hashlib.sha256(raw.encode()).hexdigest(),
            AccountToken.purpose == purpose, AccountToken.used_at.is_(None),
            AccountToken.expires_at > utcnow()))

    def absolute_url(endpoint, **values):
        base = app.config.get('APP_BASE_URL')
        return (base + url_for(endpoint, **values)) if base else url_for(endpoint, _external=True, **values)

    def send_email(kind, recipient, subject, body, staff_user_id=None, family_id=None):
        message = EmailMessage(kind=kind, recipient=recipient, subject=subject, text_body=body,
                               staff_user_id=staff_user_id, family_id=family_id)
        db.session.add(message)
        db.session.flush()
        safe_body = escape(body)
        safe_body = re.sub(r'(https?://[^\s<]+)', r'<a href="\1">\1</a>', safe_body)
        html = ('<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto">'
                '<h2 style="color:#173e66">Yazory</h2>'
                f'<div style="white-space:pre-line;line-height:1.6">{safe_body}</div></div>')
        if app.config['TESTING'] or app.config['DEMO']:
            message.status = 'preview'
            return message
        provider_id, error = deliver(app.config['RESEND_API_KEY'], app.config['EMAIL_FROM'],
                                     recipient, subject, html, body)
        message.provider_id = provider_id or ''
        message.error = error or ''
        message.status = 'failed' if error else 'sent'
        message.sent_at = None if error else utcnow()
        return message

    def notify_users(users, kind, subject, body, family_id=None):
        for user in users:
            if user.status == 'active':
                send_email(kind, user.email, subject, body, staff_user_id=user.id, family_id=family_id)

    def assigned_users(family_id, roles=None):
        statement = select(StaffUser).join(FamilyAssignment).where(
            FamilyAssignment.family_id == family_id, StaffUser.status == 'active')
        if roles:
            statement = statement.where(StaffUser.role.in_(roles))
        return db.session.scalars(statement).all()

    def organization_admins():
        return db.session.scalars(select(StaffUser).where(
            StaffUser.role == 'organization_admin', StaffUser.status == 'active')).all()

    def linked_contact_count(contact):
        if not contact.supporter_key:
            return 1
        return db.session.scalar(select(func.count(func.distinct(Contact.family_id))).where(
            Contact.supporter_key == contact.supporter_key)) or 1

    def unique_pledged_total(family_ids=None):
        statement = select(Contact).where(Contact.status == 'Pledged')
        if family_ids is not None:
            statement = statement.where(Contact.family_id.in_(family_ids))
        contacts = db.session.scalars(statement.order_by(Contact.id)).all()
        unique = {}
        for contact in contacts:
            identity = contact.supporter_key or f'legacy:{contact.id}'
            unique.setdefault(identity, contact)
        return sum(contact.monthly_equivalent_cents for contact in unique.values())

    def ensure_bootstrap_owner():
        """Create the configured owner once; never replace an existing password."""
        if app.config['DEMO']:
            return
        email = app.config.get('ADMIN_EMAIL', '').strip().lower()
        password_hash = app.config.get('ADMIN_PASSWORD_HASH', '')
        if not email or not valid_werkzeug_password_hash(password_hash):
            return
        owner = db.session.scalar(select(StaffUser).where(StaffUser.email == email))
        if owner is None:
            db.session.add(StaffUser(email=email, password_hash=password_hash, role='organization_admin'))
            db.session.commit()
        elif owner.role != 'organization_admin' or not hmac.compare_digest(owner.password_hash, password_hash):
            # The configured bootstrap identity is always the organization owner;
            # updating the secure hash also supports deliberate owner password rotation.
            owner.role = 'organization_admin'
            owner.password_hash = password_hash
            db.session.commit()

    def ensure_schema():
        """Create missing tables and apply the additive legacy-schema upgrades."""
        db.create_all()
        staff_columns = {column['name'] for column in inspect(db.engine).get_columns('staff_user')}
        for column, definition in {
            'name': "VARCHAR(160) NOT NULL DEFAULT ''",
            'status': "VARCHAR(20) NOT NULL DEFAULT 'active'",
            'invited_at': 'TIMESTAMP', 'activated_at': 'TIMESTAMP', 'last_login_at': 'TIMESTAMP',
        }.items():
            if column not in staff_columns:
                db.session.execute(text(f'ALTER TABLE staff_user ADD COLUMN {column} {definition}'))
        family_columns = {column['name'] for column in inspect(db.engine).get_columns('family')}
        for column, definition in {
            'city': 'VARCHAR(120)',
            'state': 'VARCHAR(80)',
            'zip_code': 'VARCHAR(20)',
            'inlaws_maiden_name': 'VARCHAR(160)',
            'inlaws_family': 'TEXT',
            'rabbi_phone': 'VARCHAR(80)',
            'shul_gabbai': 'VARCHAR(160)',
            'shul_gabbai_phone': 'VARCHAR(80)',
        }.items():
            if column not in family_columns:
                db.session.execute(text(
                    f"ALTER TABLE family ADD COLUMN {column} {definition} DEFAULT ''"
                ))
        # Move the original single gabbai fields into the repeatable list once.
        for family in db.session.scalars(select(Family)).all():
            if not family.gabbais and (family.shul_gabbai or family.shul_gabbai_phone):
                db.session.add(ShulGabbai(
                    family_id=family.id,
                    name=family.shul_gabbai or 'Gabbai',
                    phone=family.shul_gabbai_phone or '',
                ))
        child_columns = {column['name'] for column in inspect(db.engine).get_columns('child')}
        for column, definition in {
            # FALSE is valid for PostgreSQL and SQLite. PostgreSQL rejects the
            # integer DEFAULT 0 that was previously used here, which aborted
            # the whole startup migration and left profile pages unusable.
            'married': 'BOOLEAN NOT NULL DEFAULT FALSE',
            'spouse_name': "VARCHAR(160) DEFAULT ''",
        }.items():
            if column not in child_columns:
                db.session.execute(text(f'ALTER TABLE child ADD COLUMN {column} {definition}'))
        contact_columns = {column['name'] for column in inspect(db.engine).get_columns('contact')}
        if 'supporter_key' not in contact_columns:
            db.session.execute(text(
                "ALTER TABLE contact ADD COLUMN supporter_key VARCHAR(200) DEFAULT '' NOT NULL"
            ))
        if 'pledge_frequency' not in contact_columns:
            db.session.execute(text(
                "ALTER TABLE contact ADD COLUMN pledge_frequency VARCHAR(20) NOT NULL DEFAULT 'Monthly'"
            ))
        if 'parent_contact_id' not in contact_columns:
            db.session.execute(text(
                'ALTER TABLE contact ADD COLUMN parent_contact_id INTEGER REFERENCES contact(id)'
            ))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS ix_contact_parent_contact_id ON contact (parent_contact_id)'
            ))
        if 'parent_connection' not in contact_columns:
            db.session.execute(text(
                "ALTER TABLE contact ADD COLUMN parent_connection VARCHAR(20) NOT NULL DEFAULT ''"
            ))
            # Nested supporters previously displayed as sons-in-law, so retain
            # that meaning for existing records while making it explicit.
        db.session.commit()

    def current_user():
        if app.config['DEMO']:
            return None
        user_id = session.get('user_id')
        return db.session.get(StaffUser, user_id) if user_id else None

    def organization_admin():
        return app.config['DEMO'] or (current_user() and current_user().role == 'organization_admin')

    STAFF_ROLES = ('organization_admin', 'family_admin', 'office_employee', 'fundraiser')

    def has_role(*roles):
        return organization_admin() or bool(current_user() and current_user().role in roles)

    def can_manage_household():
        return has_role('family_admin', 'office_employee')

    def can_manage_supporters():
        return has_role('family_admin', 'fundraiser')

    def setting(key, default):
        row = db.session.get(OrganizationSetting, key)
        return row.value if row and isinstance(row.value, type(default)) else default

    def expense_categories():
        values = setting('expense_categories', DEFAULT_CATEGORIES)
        return values if values and all(isinstance(x, str) and x in DEFAULT_CATEGORIES for x in values) else DEFAULT_CATEGORIES

    def child_bands():
        values = setting('child_estimate_bands', DEFAULT_CHILD_BANDS)
        try:
            valid = valid_child_bands(values)
        except (KeyError, TypeError, ValueError):
            valid = False
        return values if valid else DEFAULT_CHILD_BANDS

    def valid_child_bands(values):
        if not isinstance(values, list) or not values:
            return False
        spans = []
        for item in values:
            if not isinstance(item, dict):
                return False
            low, high, cents = int(item['min_age']), int(item['max_age']), int(item['amount_cents'])
            if not 0 <= low <= high <= 30 or not 0 <= cents <= 100000000:
                return False
            spans.append((low, high))
        spans.sort()
        return all(previous[1] < following[0] for previous, following in zip(spans, spans[1:]))

    def budget_totals(family):
        """One authoritative calculation shared by every budget-facing screen."""
        intake = family.intake_record.data if family.intake_record else {}
        record = db.session.get(HouseholdBudget, family.id)
        report = child_budget.calculate(record.data if record else {}, intake, family.children, child_bands())
        return {'income': report['earnings'] + report['usable_help'],
                'bills': report['household_bills'],
                'child_estimates': report['child_estimates'],
                'actual_children': report['actual_child_amounts'],
                'shortfall': report['gap'], 'costs': report['costs'], 'report': report}

    def require_capability(allowed, message='You do not have permission for this action.'):
        if not has_role(*allowed):
            abort(403, message)

    def require_organization_admin():
        if not organization_admin():
            abort(403, 'Organization administrator access is required.')

    def can_access_family(family_id):
        if organization_admin():
            return True
        user = current_user()
        return bool(user and db.session.scalar(select(FamilyAssignment.id).where(
            FamilyAssignment.staff_user_id == user.id, FamilyAssignment.family_id == family_id)))

    def accessible_family_or_404(family_id):
        # Check assignment before loading household data for non-administrators.
        if not can_access_family(family_id):
            abort(403, 'You are not assigned to this family.')
        return db.get_or_404(Family, family_id)

    @app.context_processor
    def common():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        user = current_user()
        return dict(language=session.get('language', 'en'), languages=LANGUAGES, direction='rtl' if session.get('language') in ('he','yi') else 'ltr', csrf=session['csrf'], demo=app.config['DEMO'], categories=expense_categories(), relationships=RELATIONSHIPS, contact_statuses=CONTACT_STATUSES, pledge_frequencies=PLEDGE_FREQUENCIES, family_transitions=FAMILY_TRANSITIONS, expense_transitions=EXPENSE_TRANSITIONS, current_month=datetime.now().strftime('%Y-%m'), current_staff=user, is_org_admin=organization_admin(), can_manage_household=can_manage_household(), can_manage_supporters=can_manage_supporters(), is_fundraiser=bool(user and user.role == 'fundraiser'))

    @app.before_request
    def security():
        public_endpoints = ('static', 'health', 'set_language', 'login', 'forgot_password',
                            'reset_password', 'accept_invitation')
        if request.endpoint in ('static', 'health', 'set_language'):
            return
        if request.method == 'POST' and not hmac.compare_digest(session.get('csrf', ''), request.form.get('csrf', '')):
            abort(400, 'Your form expired. Reload the page and try again.')
        if request.method == 'POST' and not session.get('csrf'):
            abort(400)
        if not app.config['DEMO'] and request.endpoint not in public_endpoints:
            if not session.get('user_id'):
                return redirect(url_for('login'))
            if current_user() is None or current_user().status != 'active':
                language = session.get('language', 'en')
                session.clear()
                session['language'] = language
                return redirect(url_for('login'))

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def audit(action, family_id=None):
        user = current_user()
        db.session.add(Audit(actor=user.email if user else 'Demo user', action=action, family_id=family_id))

    def field(name, required=False, limit=160):
        value = request.form.get(name, '').strip()
        if (required and not value) or len(value) > limit:
            abort(400, f'{name.replace("_", " ").title()} is required or exceeds {limit} characters.')
        return value

    def email_field(name='email'):
        value = field(name, True, 254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            abort(400, 'Enter a valid email address.')
        return value

    def amount(name, allow_zero=False):
        try:
            value = Decimal(field(name, True, 20))
            if not value.is_finite() or value < 0 or (value == 0 and not allow_zero) or value > 1000000 or value.as_tuple().exponent < -2:
                raise ValueError()
            return int(value * 100)
        except (InvalidOperation, ValueError):
            abort(400, 'Enter a valid amount with up to two decimal places, no greater than $1,000,000.')

    @app.get('/language/<language>')
    def set_language(language):
        if language not in LANGUAGES:
            abort(404)
        session['language'] = language
        # Only known local application routes may be used as the return path.
        from urllib.parse import urlsplit
        target = request.args.get('next', '/')
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not target.startswith('/') or target.startswith('//') or '\\' in target:
            target = '/'
        return redirect(target)

    @app.get('/health')
    def health():
        db.session.execute(select(1))
        return {'status': 'ok'}

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            import time
            time.sleep(1)
            email = email_field()
            ensure_bootstrap_owner()
            user = db.session.scalar(select(StaffUser).where(StaffUser.email == email.lower()))
            if user and user.status == 'active' and check_password_hash(user.password_hash, request.form.get('password', '')):
                language = session.get('language', 'en')
                session.clear()
                session['language'] = language
                session['user_id'] = user.id
                session.permanent = True
                user.last_login_at = utcnow()
                db.session.commit()
                return redirect(url_for('dashboard'))
            flash('Email or password is incorrect.', 'error')
        return render_template('login.html', title='Staff sign in')

    @app.post('/logout')
    def logout():
        language = session.get('language', 'en')
        session.clear()
        session['language'] = language
        return redirect(url_for('login'))

    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            email = email_field()
            user = db.session.scalar(select(StaffUser).where(
                StaffUser.email == email, StaffUser.status == 'active'))
            if user:
                db.session.execute(db.update(AccountToken).where(
                    AccountToken.staff_user_id == user.id, AccountToken.purpose == 'reset',
                    AccountToken.used_at.is_(None)).values(used_at=utcnow()))
                raw = account_token(user, 'reset', 1)
                link = absolute_url('reset_password', token=raw)
                send_email('password_reset', user.email, 'Reset your Yazory password',
                    f'A password reset was requested for your Yazory account.\n\nReset password: {link}\n\nThis link expires in 1 hour. If you did not request this, ignore this email.',
                    staff_user_id=user.id)
                db.session.commit()
            flash('If an active account uses that email, a reset link has been sent.')
            return redirect(url_for('login'))
        return render_template('forgot_password.html', title='Reset password')

    @app.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        record = token_record(token, 'reset')
        if record is None:
            abort(400, 'This password-reset link is invalid or expired.')
        if request.method == 'POST':
            password = request.form.get('password', '')
            confirmation = request.form.get('password_confirmation', '')
            if not 12 <= len(password) <= 256 or password != confirmation:
                abort(400, 'Passwords must match and contain at least 12 characters.')
            record.staff_user.password_hash = generate_password_hash(password)
            record.used_at = utcnow()
            db.session.commit()
            flash('Password updated. You can now sign in.')
            return redirect(url_for('login'))
        return render_template('set_password.html', title='Reset password', invitation=False)

    @app.route('/accept-invitation/<token>', methods=['GET', 'POST'])
    def accept_invitation(token):
        record = token_record(token, 'invite')
        if record is None or record.staff_user.status != 'pending':
            abort(400, 'This invitation is invalid, expired, or already used.')
        if request.method == 'POST':
            password = request.form.get('password', '')
            confirmation = request.form.get('password_confirmation', '')
            name = field('name', True)
            if not 12 <= len(password) <= 256 or password != confirmation:
                abort(400, 'Passwords must match and contain at least 12 characters.')
            user = record.staff_user
            user.name = name
            user.password_hash = generate_password_hash(password)
            user.status = 'active'
            user.activated_at = utcnow()
            record.used_at = utcnow()
            audit(f'Accepted staff invitation: {user.email}')
            db.session.commit()
            flash('Your Yazory account is ready. Sign in to continue.')
            return redirect(url_for('login'))
        return render_template('set_password.html', title='Accept invitation', invitation=True,
                               invited_user=record.staff_user)

    @app.get('/')
    def dashboard():
        if current_user() and current_user().role == 'fundraiser':
            return redirect(url_for('fundraising'))
        statement = select(Family).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(statement).all()
        family_ids = [family.id for family in families]
        month = datetime.now().strftime('%Y-%m')
        expenses = db.session.scalars(select(Expense).where(Expense.month == month, Expense.family_id.in_(family_ids))).all()
        network_visible = organization_admin() or bool(current_user() and current_user().role in ('family_admin', 'fundraiser'))
        active_family_ids = select(Family.id).where(Family.status == 'Active', Family.id.in_(family_ids))
        pledged = unique_pledged_total(active_family_ids) if network_visible else 0
        requested_statement = select(Expense).where(Expense.status == 'Requested').order_by(Expense.id.desc())
        if not organization_admin():
            requested_statement = requested_statement.where(Expense.family_id.in_(
                select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        requested = db.session.scalars(requested_statement).all()
        received = db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.family_id.in_(family_ids))) if family_ids and network_visible else 0
        return render_template('dashboard.html', title='Overview', families=families, active=sum(f.status=='Active' for f in families), pledged=pledged, received=received, network_visible=network_visible, shortfall=sum(budget_totals(f)['shortfall'] for f in families), approved=sum(e.amount_cents for e in expenses if e.status in ('Approved','Paid')), paid=sum(e.amount_cents for e in expenses if e.status=='Paid'), requested=requested)

    @app.get('/families')
    def families():
        require_capability(('family_admin', 'office_employee'))
        query = request.args.get('q', '').strip()[:160]
        statement = select(Family).order_by(Family.id.desc())
        if query:
            statement = statement.where(Family.name.icontains(query, autoescape=True))
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        return render_template('families.html', title='Families', families=db.session.scalars(statement).all(), query=query)

    @app.get('/cases')
    def cases():
        """Modern case-directory URL; the established families URL remains valid."""
        return families()

    def intake_form(family, title, error=None):
        values = dict(request.form) if error else ({key: getattr(family, key) for key in
            ('name','spouse','phone','address','city','state','zip_code','father','inlaws','inlaws_maiden_name','inlaws_family','rabbi','rabbi_phone','weekday_shul','shabbos_shul','shul_gabbai','shul_gabbai_phone','circumstances')} if family else {})
        budget = intake_for_form(family.intake_record.data if family and family.intake_record else {})
        if error:
            budget.update(request.form)
            import json
            for group in ('accounts', 'assistance'):
                try:
                    entries = json.loads(request.form.get(group + '_json', '[]'))
                    budget[group] = entries if isinstance(entries, list) else []
                except ValueError:
                    budget[group] = []
        return render_template('family_form.html', family=family, title=title, values=values, budget=budget, intake_error=error)

    def save_intake(family, data):
        if data is not None:
            record = db.session.get(HouseholdIntake, family.id)
            if record is None:
                record = HouseholdIntake(family_id=family.id)
                db.session.add(record)
            record.data = data

    @app.route('/families/new', methods=['GET', 'POST'])
    def new_family():
        require_capability(('organization_admin', 'office_employee'))
        if request.method == 'POST':
            try:
                intake_data = validate_intake(request.form) if request.form.get('intake_version') else None
            except ValueError as exc:
                return intake_form(None, 'New family intake', str(exc)), 400
            limits = {'address':300, 'city':120, 'state':80, 'zip_code':20, 'phone':80, 'rabbi_phone':80, 'shul_gabbai_phone':80, 'inlaws_family':1000}
            family = Family(name=field('name', True), **{k: field(k, limit=limits.get(k, 160)) for k in ['spouse','phone','address','city','state','zip_code','father','inlaws','inlaws_maiden_name','inlaws_family','rabbi','rabbi_phone','weekday_shul','shabbos_shul','shul_gabbai','shul_gabbai_phone']}, circumstances=field('circumstances', limit=5000))
            db.session.add(family)
            db.session.flush()
            save_intake(family, intake_data)
            # An office intake never creates an unassigned household.
            if not organization_admin():
                db.session.add(FamilyAssignment(staff_user_id=current_user().id, family_id=family.id))
            audit('Created family intake', family.id)
            db.session.commit()
            flash('Family intake saved.')
            return redirect(url_for('family_detail', family_id=family.id))
        return intake_form(None, 'New family intake')

    @app.route('/families/<int:family_id>/edit', methods=['GET', 'POST'])
    def edit_family(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        if request.method == 'POST':
            try:
                intake_data = validate_intake(request.form) if request.form.get('intake_version') else None
            except ValueError as exc:
                return intake_form(family, 'Edit family profile', str(exc)), 400
            limits = {'circumstances':5000, 'inlaws_family':1000, 'address':300, 'city':120, 'state':80, 'zip_code':20, 'phone':80, 'rabbi_phone':80, 'shul_gabbai_phone':80}
            for key in ['name','spouse','phone','address','city','state','zip_code','father','inlaws','inlaws_maiden_name','inlaws_family','rabbi','rabbi_phone','weekday_shul','shabbos_shul','shul_gabbai','shul_gabbai_phone','circumstances']:
                setattr(family, key, field(key, required=key=='name', limit=limits.get(key, 160)))
            save_intake(family, intake_data)
            audit('Updated family profile', family.id)
            db.session.commit()
            flash('Profile updated.')
            return redirect(url_for('family_detail', family_id=family.id))
        return intake_form(family, 'Edit family profile')

    @app.get('/families/<int:family_id>')
    def family_detail(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        if current_user() and current_user().role == 'office_employee':
            return render_template('family_office_with_documents.html', title=family.name, family=family)
        activity = db.session.scalars(select(Audit).where(Audit.family_id==family.id).order_by(Audit.id.desc()).limit(30)).all()
        for contact in family.contacts:
            contact.connected_cases = linked_contact_count(contact)
        return render_template('family.html', title=family.name, family=family, activity=activity,
                               budget=budget_totals(family),
                               pledged=sum(c.monthly_equivalent_cents for c in family.contacts if c.status=='Pledged'))

    @app.get('/families/<int:family_id>/print')
    def family_print_report(family_id):
        """One filterable, print-ready record for every list on a family profile."""
        require_capability(('family_admin',))
        family = accessible_family_or_404(family_id)
        query = request.args.get('q', '').strip()[:160]
        section = request.args.get('section', 'all')
        supporter_status = request.args.get('supporter_status', '')
        expense_status = request.args.get('expense_status', '')
        if section not in {'all', 'children', 'supporters', 'donations', 'expenses', 'documents', 'activity'}:
            abort(400, 'Choose a valid report section.')
        if supporter_status and supporter_status not in CONTACT_STATUSES:
            abort(400, 'Choose a valid supporter status.')
        if expense_status and expense_status not in EXPENSE_TRANSITIONS:
            abort(400, 'Choose a valid expense status.')

        def report_date(name):
            raw = request.args.get(name, '').strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw)
            except ValueError:
                abort(400, 'Enter a valid report date.')

        date_from, date_to = report_date('date_from'), report_date('date_to')
        if date_from and date_to and date_from > date_to:
            abort(400, 'The start date must be before the end date.')
        needle = query.casefold()
        matches = lambda *values: not needle or any(needle in str(value or '').casefold() for value in values)

        children = [child for child in sorted(family.children, key=lambda row: (row.age, row.name.casefold()))
                    if matches(child.name, child.age, child.grade, child.school, child.tuition_contact, child.spouse_name)]
        contacts = [contact for contact in sorted(family.contacts, key=lambda row: row.name.casefold())
                    if (not supporter_status or contact.status == supporter_status)
                    and matches(contact.name, contact.relationship, contact.phone, contact.status)]
        receipt_statement = select(Receipt).where(Receipt.family_id == family.id)
        if date_from:
            receipt_statement = receipt_statement.where(Receipt.received_on >= date_from)
        if date_to:
            receipt_statement = receipt_statement.where(Receipt.received_on <= date_to)
        receipts = [receipt for receipt in db.session.scalars(receipt_statement.order_by(
            Receipt.received_on.desc(), Receipt.id.desc())).all()
            if matches(receipt.contact.name, receipt.amount_cents / 100, receipt.reference, receipt.note,
                       receipt.received_on.isoformat())]
        expenses = [expense for expense in sorted(family.expenses, key=lambda row: (row.month, row.id), reverse=True)
                    if (not expense_status or expense.status == expense_status)
                    and matches(expense.category, expense.payee, expense.month, expense.amount_cents / 100,
                                expense.status, expense.payment_reference, expense.note)]
        documents = [document for document in sorted(family.documents, key=lambda row: row.uploaded_at, reverse=True)
                     if matches(document.filename, document.content_type)]
        activity = [row for row in db.session.scalars(select(Audit).where(
            Audit.family_id == family.id).order_by(Audit.id.desc())).all()
                    if matches(row.actor, row.action, row.at.isoformat())]
        return render_template('family_print.html', title='Profile report', family=family,
            query=query, section=section, supporter_status=supporter_status, expense_status=expense_status,
            date_from=date_from, date_to=date_to, children=children, contacts=contacts, receipts=receipts,
            expenses=expenses, documents=documents, activity=activity, budget=budget_totals(family),
            pledged=sum(contact.monthly_equivalent_cents for contact in family.contacts if contact.status == 'Pledged'),
            received=sum(receipt.amount_cents for receipt in receipts), generated_at=datetime.now(timezone.utc))

    @app.route('/families/<int:family_id>/expense-report', methods=['GET', 'POST'])
    def family_expense_report(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        record = db.session.get(HouseholdBudget, family_id)
        data = record.data if record else {}
        error = None
        if request.method == 'POST':
            try:
                data = child_budget.parse(request.form, family.children)
            except ValueError as exc:
                error = str(exc)
            else:
                if record is None:
                    record = HouseholdBudget(family_id=family_id)
                    db.session.add(record)
                record.data = data
                for child in family.children:
                    child.age = data['children'][str(child.id)]['age']
                audit('Updated household expense plan', family_id)
                db.session.commit()
                flash('Profile updated.')
                return redirect(url_for('family_expense_report', family_id=family_id))
        report = child_budget.calculate(data, family.intake_record.data if family.intake_record else {},
                                        family.children, child_bands())
        return render_template('expense_report.html', title='Monthly expense report', family=family,
            report=report, budget=data, categories=child_budget.CATEGORIES, components=child_budget.COMPONENTS,
            bands=child_budget.BANDS, error=error), 400 if error else 200

    @app.post('/families/<int:family_id>/status')
    def family_status(family_id):
        require_organization_admin()
        family = accessible_family_or_404(family_id)
        status = field('status', True)
        if status not in FAMILY_TRANSITIONS[family.status]:
            abort(400, 'This case status transition is not allowed.')
        old = family.status
        family.status = status
        audit(f'Case status: {old} → {status}', family.id)
        notify_users(assigned_users(family.id), 'case_status',
            f'Yazory case YZ-{family.id:04d} status updated',
            f'Case YZ-{family.id:04d} changed from {old} to {status}. Sign in to Yazory to review it.', family.id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family.id))

    @app.post('/families/<int:family_id>/children')
    def add_child(family_id):
        require_capability(('family_admin', 'office_employee'))
        accessible_family_or_404(family_id)
        try:
            age = int(field('age', True))
            if not 0 <= age <= 120: raise ValueError()
        except ValueError:
            abort(400, 'Age must be between 0 and 120.')
        db.session.add(Child(family_id=family_id, name=field('name', True), age=age,
            grade=field('grade', limit=80), school=field('school'), tuition_contact=field('tuition_contact', limit=300),
            married=request.form.get('married') == 'yes', spouse_name=field('spouse_name')))
        audit('Added child and school details', family_id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family_id))

    @app.post('/families/<int:family_id>/gabbais')
    def add_gabbai(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        db.session.add(ShulGabbai(
            family_id=family.id,
            name=field('name', True),
            phone=field('phone', limit=80),
        ))
        audit('Added shul gabbai', family.id)
        db.session.commit()
        flash('Shul gabbai added.')
        return redirect(url_for('family_detail', family_id=family.id))

    @app.post('/gabbais/<int:gabbai_id>')
    def update_gabbai(gabbai_id):
        require_capability(('family_admin', 'office_employee'))
        gabbai = db.get_or_404(ShulGabbai, gabbai_id)
        accessible_family_or_404(gabbai.family_id)
        gabbai.name = field('name', True)
        gabbai.phone = field('phone', limit=80)
        audit('Updated shul gabbai', gabbai.family_id)
        db.session.commit()
        flash('Shul gabbai updated.')
        return redirect(url_for('family_detail', family_id=gabbai.family_id))

    @app.post('/children/<int:child_id>')
    def update_child(child_id):
        require_capability(('family_admin', 'office_employee'))
        child = db.session.get(Child, child_id)
        if child is None:
            abort(404)
        accessible_family_or_404(child.family_id)
        try:
            age = int(field('age', True))
            if not 0 <= age <= 120: raise ValueError()
        except ValueError:
            abort(400, 'Age must be between 0 and 120.')
        child.name = field('name', True)
        child.age = age
        child.grade = field('grade', limit=80)
        child.school = field('school')
        child.tuition_contact = field('tuition_contact', limit=300)
        child.married = request.form.get('married') == 'yes'
        child.spouse_name = field('spouse_name')
        audit('Updated child and spouse details', child.family_id)
        db.session.commit()
        flash('Child and spouse updated.')
        return redirect(url_for('family_detail', family_id=child.family_id))

    @app.post('/families/<int:family_id>/contacts')
    def add_contact(family_id):
        require_capability(('family_admin', 'fundraiser'))
        if not can_access_family(family_id):
            abort(403, 'You are not assigned to this family.')
        if db.session.get(Family, family_id) is None:
            abort(404)
        relationship = field('relationship', True)
        status = field('status', True)
        if relationship not in set(RELATIONSHIPS) | LEGACY_RELATIONSHIPS or status not in CONTACT_STATUSES: abort(400)
        pledge = amount('monthly', allow_zero=status!='Pledged')
        pledge_frequency = field('pledge_frequency') or 'Monthly'
        if pledge_frequency not in PLEDGE_FREQUENCIES: abort(400, 'Choose a valid donation frequency.')
        parent_contact_id = request.form.get('parent_contact_id', type=int)
        parent_connection = field('parent_connection')
        if parent_contact_id:
            parent = db.session.scalar(select(Contact).where(
                Contact.id == parent_contact_id,
                Contact.family_id == family_id,
                Contact.parent_contact_id.is_(None)))
            if parent is None:
                abort(400, 'Choose a valid parent supporter.')
            if parent_connection not in ('Son', 'Son-in-law'):
                abort(400, 'Choose whether this person is a son or son-in-law of the selected supporter.')
        else:
            parent_connection = ''
        name = field('name', True)
        phone = field('phone', limit=80)
        key = supporter_key(name, phone)
        existing = db.session.scalar(select(Contact).where(Contact.supporter_key == key).order_by(Contact.id))
        duplicate_case = db.session.scalar(select(Contact.id).where(
            Contact.family_id == family_id, Contact.supporter_key == key))
        if duplicate_case:
            abort(400, 'This supporter is already connected to this case.')
        if existing:
            pledge, pledge_frequency, status = existing.monthly_cents, existing.pledge_frequency, existing.status
            if not phone:
                phone = existing.phone
        db.session.add(Contact(family_id=family_id, name=name, relationship=relationship, phone=phone,
                               supporter_key=key, parent_contact_id=parent_contact_id,
                               parent_connection=parent_connection, monthly_cents=pledge,
                               pledge_frequency=pledge_frequency, status=status))
        audit('Added donor network contact', family_id)
        db.session.commit()
        return redirect(url_for('supporters', family_id=family_id))

    @app.post('/contacts/<int:contact_id>')
    def update_contact(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        # Scope the query to an assigned family rather than exposing a contact row.
        contact = db.session.scalar(select(Contact).where(Contact.id == contact_id, Contact.family_id.in_(
            select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))) if not organization_admin() else db.get_or_404(Contact, contact_id)
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        status = field('status', True)
        if status not in CONTACT_STATUSES: abort(400)
        monthly_cents = amount('monthly', allow_zero=status!='Pledged')
        pledge_frequency = field('pledge_frequency') or 'Monthly'
        if pledge_frequency not in PLEDGE_FREQUENCIES: abort(400, 'Choose a valid donation frequency.')
        linked = [contact]
        if contact.supporter_key:
            linked = db.session.scalars(select(Contact).where(Contact.supporter_key == contact.supporter_key)).all()
        for linked_contact in linked:
            linked_contact.status = status
            linked_contact.monthly_cents = monthly_cents
            linked_contact.pledge_frequency = pledge_frequency
        audit(f'Updated donor pledge: {status}', contact.family_id)
        db.session.commit()
        return redirect(url_for('fundraising_detail' if current_user() and current_user().role == 'fundraiser' else 'family_detail', family_id=contact.family_id))

    @app.route('/contacts/<int:contact_id>/edit', methods=['GET', 'POST'])
    def edit_contact(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        possible_parents = db.session.scalars(select(Contact).where(
            Contact.family_id == contact.family_id,
            Contact.id != contact.id,
            Contact.parent_contact_id.is_(None)
        ).order_by(Contact.name)).all()
        if request.method == 'POST':
            relationship = field('relationship', True)
            status = field('status', True)
            if relationship not in set(RELATIONSHIPS) | LEGACY_RELATIONSHIPS or status not in CONTACT_STATUSES:
                abort(400)
            pledge_frequency = field('pledge_frequency') or 'Monthly'
            if pledge_frequency not in PLEDGE_FREQUENCIES:
                abort(400, 'Choose a valid donation frequency.')
            parent_contact_id = request.form.get('parent_contact_id', type=int)
            if parent_contact_id and not any(row.id == parent_contact_id for row in possible_parents):
                abort(400, 'Choose a valid parent supporter.')
            parent_connection = field('parent_connection')
            if parent_contact_id and parent_connection not in ('Son', 'Son-in-law'):
                abort(400, 'Choose whether this person is a son or son-in-law of the selected supporter.')
            if not parent_contact_id:
                parent_connection = ''
            name = field('name', True)
            phone = field('phone', limit=80)
            new_key = supporter_key(name, phone)
            linked = db.session.scalars(select(Contact).where(
                Contact.supporter_key == contact.supporter_key)).all() if contact.supporter_key else [contact]
            duplicate = db.session.scalar(select(Contact.id).where(
                Contact.family_id == contact.family_id,
                Contact.supporter_key == new_key,
                Contact.id.not_in([row.id for row in linked])))
            if duplicate:
                abort(400, 'This supporter is already connected to this case.')
            for linked_contact in linked:
                linked_contact.name = name
                linked_contact.phone = phone
                linked_contact.supporter_key = new_key
                linked_contact.status = status
                linked_contact.monthly_cents = amount('monthly', allow_zero=status != 'Pledged')
                linked_contact.pledge_frequency = pledge_frequency
            contact.relationship = relationship
            contact.parent_contact_id = parent_contact_id
            contact.parent_connection = parent_connection
            audit(f'Updated supporter details: {name}', contact.family_id)
            db.session.commit()
            flash('Supporter updated.')
            return redirect(url_for('supporter_detail', contact_id=contact.id))
        return render_template('supporter_edit.html', title='Edit supporter', contact=contact,
                               possible_parents=possible_parents)

    @app.post('/contacts/<int:contact_id>/children')
    def add_contact_child(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        contact = db.session.scalar(select(Contact).where(
            Contact.id == contact_id,
            Contact.family_id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))) if not organization_admin() else db.get_or_404(Contact, contact_id)
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        name = field('name', True)
        spouse_name = field('spouse_name')
        phone = field('phone', limit=80)
        duplicate = db.session.scalar(select(ContactChild.id).where(
            ContactChild.contact_id == contact.id,
            func.lower(ContactChild.name) == name.lower()))
        if duplicate:
            abort(400, 'This child is already listed under this supporter.')
        db.session.add(ContactChild(contact_id=contact.id, name=name,
                                    spouse_name=spouse_name, phone=phone))
        audit(f'Added child under supporter: {contact.name}', contact.family_id)
        db.session.commit()
        return redirect(url_for('fundraising_detail' if current_user() and current_user().role == 'fundraiser' else 'family_detail', family_id=contact.family_id))

    @app.post('/contacts/<int:contact_id>/delete')
    def delete_contact(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        if contact.receipts:
            abort(400, 'This supporter cannot be deleted because donation receipts are recorded.')
        family_id = contact.family_id
        name = contact.name
        db.session.delete(contact)
        audit(f'Deleted supporter: {name}', family_id)
        db.session.commit()
        flash('Supporter deleted.')
        next_url = request.form.get('next', '')
        return redirect(next_url if next_url.startswith('/') and not next_url.startswith('//') else url_for('supporters'))

    def accessible_document_or_403(document_id):
        if organization_admin():
            return db.get_or_404(Document, document_id)
        document = db.session.scalar(select(Document).where(
            Document.id == document_id,
            Document.family_id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id))))
        if document is None:
            abort(403, 'You are not assigned to this family.')
        return document

    @app.post('/families/<int:family_id>/documents')
    def add_document(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        upload = request.files.get('document')
        filename = secure_filename(upload.filename or '') if upload else ''
        if not upload or not filename:
            abort(400, 'Choose a PDF, PNG, or JPEG document.')
        data = upload.read()
        if not data or len(data) > 8 * 1024 * 1024:
            abort(400, 'Document must be between 1 byte and 8 MB.')
        extension = os.path.splitext(filename)[1].lower()
        if data.startswith(b'%PDF-'):
            detected_type, allowed_extensions = 'application/pdf', {'.pdf'}
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):
            detected_type, allowed_extensions = 'image/png', {'.png'}
        elif data.startswith(b'\xff\xd8\xff'):
            detected_type, allowed_extensions = 'image/jpeg', {'.jpg', '.jpeg'}
        else:
            abort(400, 'Choose a PDF, PNG, or JPEG document.')
        if extension not in allowed_extensions:
            abort(400, 'The document filename extension does not match its contents.')
        db.session.add(Document(family_id=family.id, filename=filename,
                                content_type=detected_type, data=data))
        audit('Added family document', family.id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family.id))

    @app.get('/documents/<int:document_id>')
    def download_document(document_id):
        require_capability(('family_admin', 'office_employee'))
        document = accessible_document_or_403(document_id)
        return send_file(BytesIO(document.data), mimetype=document.content_type,
                         as_attachment=True, download_name=document.filename,
                         max_age=0)

    @app.post('/documents/<int:document_id>/delete')
    def delete_document(document_id):
        require_capability(('family_admin', 'office_employee'))
        document = accessible_document_or_403(document_id)
        family_id = document.family_id
        db.session.delete(document)
        audit('Deleted family document', family_id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family_id))

    @app.post('/families/<int:family_id>/expenses')
    def add_expense(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        if family.status in ('Closed', 'Declined'): abort(400, 'Reopen the case before requesting an expense.')
        category = field('category', True)
        if category not in expense_categories(): abort(400)
        month = field('month', True, 7)
        try:
            if datetime.strptime(month, '%Y-%m').strftime('%Y-%m') != month: raise ValueError()
        except ValueError:
            abort(400, 'Enter a valid month.')
        expense = Expense(family_id=family_id, category=category, payee=field('payee', True), amount_cents=amount('amount'), month=month, note=field('note', limit=5000))
        db.session.add(expense)
        db.session.flush()
        audit('Submitted expense request', family_id)
        notify_users(organization_admins(), 'expense_requested',
            f'Expense request for case YZ-{family.id:04d}',
            f'A new {category} expense request for ${expense.amount_cents / 100:,.2f} requires review. Sign in to Yazory for the full request.', family.id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family_id))

    @app.get('/fundraising')
    def fundraising():
        require_capability(('fundraiser', 'family_admin'))
        statement = select(Family.id.label('id'), Family.name.label('name')).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.execute(statement).all()
        # Each case still shows the supporter commitment attributed to it. The
        # organization dashboard/billing rollup de-duplicates the shared person.
        pledged = {
            family.id: sum(contact.monthly_equivalent_cents for contact in db.session.scalars(select(Contact).where(
                Contact.family_id == family.id, Contact.status == 'Pledged')).all())
            for family in families
        }
        received = {family.id: db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.family_id == family.id)) for family in families}
        # Fundraisers receive no target/shortfall: even an aggregate may disclose
        # confidential household budget information. Authorized family/admin users
        # may use the saved shortfall as an internal planning target.
        show_targets = not (current_user() and current_user().role == 'fundraiser')
        targets = ({family.id: budget_totals(db.session.get(Family, family.id))['shortfall'] for family in families}
                   if show_targets else {})
        return render_template('fundraising.html', title='Fundraising workspace', families=families,
                               pledged=pledged, received=received, targets=targets,
                               show_targets=show_targets)

    @app.get('/fundraising/<int:family_id>')
    def fundraising_detail(family_id):
        require_capability(('fundraiser', 'family_admin'))
        if not can_access_family(family_id):
            abort(403, 'You are not assigned to this family.')
        family = db.session.execute(select(Family.id.label('id'), Family.name.label('name')).where(
            Family.id == family_id)).one_or_none()
        if family is None:
            abort(404)
        contacts = db.session.scalars(select(Contact).where(Contact.family_id == family.id).order_by(Contact.id)).all()
        for contact in contacts:
            contact.connected_cases = linked_contact_count(contact)
        pledged = sum(contact.monthly_equivalent_cents for contact in contacts if contact.status == 'Pledged')
        return render_template('fundraising_detail.html', title='Fundraising workspace', family=family,
                               contacts=contacts, pledged=pledged)

    def scoped_contacts_statement():
        statement = select(Contact).order_by(Contact.id.desc())
        if not organization_admin():
            statement = statement.where(Contact.family_id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        return statement

    @app.get('/collections')
    def collections():
        # Office employees intentionally do not receive donor or receipt information.
        require_capability(('family_admin', 'fundraiser'))
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        try:
            if datetime.strptime(month, '%Y-%m').strftime('%Y-%m') != month:
                raise ValueError()
        except ValueError:
            abort(400, 'Enter a valid month.')
        month_start = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        contacts = db.session.scalars(scoped_contacts_statement()).all()
        family_ids = [contact.family_id for contact in contacts]
        receipts = db.session.scalars(select(Receipt).where(
            Receipt.family_id.in_(family_ids),
            Receipt.received_on >= month_start, Receipt.received_on < month_end
        ).order_by(Receipt.received_on.desc(), Receipt.id.desc())).all() if family_ids else []
        received_by_contact = {}
        for receipt in receipts:
            received_by_contact[receipt.contact_id] = received_by_contact.get(receipt.contact_id, 0) + receipt.amount_cents
        lifetime_by_contact = {contact.id: db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.contact_id == contact.id)) for contact in contacts}
        return render_template('collections.html', title='Collections', contacts=contacts,
                               receipts=receipts, received_by_contact=received_by_contact,
                               lifetime_by_contact=lifetime_by_contact, month=month)

    @app.post('/collections/receipts')
    def record_receipt():
        require_capability(('family_admin', 'fundraiser'))
        contact_id = request.form.get('contact_id', type=int)
        if not contact_id:
            abort(400, 'Choose a supporter.')
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        received_on = field('received_on', True, 10)
        try:
            received_date = datetime.strptime(received_on, '%Y-%m-%d').date()
        except ValueError:
            abort(400, 'Enter a valid received date.')
        receipt = Receipt(contact_id=contact.id, family_id=contact.family_id,
                          amount_cents=amount('amount'), received_on=received_date,
                          reference=field('reference', limit=200),
                          note=field('note', limit=5000),
                          recorded_by=current_user().id if current_user() else None)
        db.session.add(receipt)
        audit('Recorded manual receipt', contact.family_id)
        db.session.commit()
        flash('Manual receipt recorded.')
        return redirect(url_for('collections', month=received_date.strftime('%Y-%m')))

    @app.get('/supporters')
    def supporters():
        require_capability(('family_admin', 'fundraiser'))
        query = request.args.get('q', '').strip()[:160]
        family_id = request.args.get('family_id', type=int)
        statement = scoped_contacts_statement()
        if family_id:
            if not can_access_family(family_id):
                abort(403, 'You are not assigned to this family.')
            statement = statement.where(Contact.family_id == family_id)
        if query:
            statement = statement.where(Contact.name.icontains(query, autoescape=True))
        contacts = db.session.scalars(statement).all()
        family_statement = select(Family).order_by(Family.name)
        if not organization_admin():
            family_statement = family_statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(family_statement).all()
        family_ids = [family.id for family in families]
        possible_parents = db.session.scalars(select(Contact).where(
            Contact.family_id.in_(family_ids), Contact.parent_contact_id.is_(None)
        ).order_by(Contact.family_id, Contact.name)).all() if family_ids else []
        totals = {c.id: db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.contact_id == c.id)) for c in contacts}
        return render_template('supporters.html', title='Supporters', contacts=contacts,
                               received=totals, query=query, families=families,
                               selected_family_id=family_id, possible_parents=possible_parents)

    @app.get('/supporters/<int:contact_id>')
    def supporter_detail(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        linked_statement = scoped_contacts_statement()
        if contact.supporter_key:
            linked_statement = linked_statement.where(Contact.supporter_key == contact.supporter_key)
        else:
            linked_statement = linked_statement.where(Contact.id == contact.id)
        linked_contacts = db.session.scalars(linked_statement.order_by(Contact.id)).all()
        contact_ids = [row.id for row in linked_contacts]
        receipts = db.session.scalars(select(Receipt).where(
            Receipt.contact_id.in_(contact_ids)
        ).order_by(Receipt.received_on.desc(), Receipt.id.desc())).all() if contact_ids else []
        return render_template('supporter_detail.html', title='Supporter history',
                               supporter=contact, linked_contacts=linked_contacts,
                               receipts=receipts,
                               total_received=sum(receipt.amount_cents for receipt in receipts))

    @app.get('/approvals')
    def approvals():
        require_organization_admin()
        expenses = db.session.scalars(select(Expense).where(Expense.status == 'Requested').order_by(Expense.id.desc())).all()
        return render_template('approvals.html', title='Approvals', expenses=expenses)

    @app.get('/reports')
    def reports():
        require_organization_admin()
        families = db.session.scalars(select(Family).order_by(Family.name)).all()
        rows = []
        for family in families:
            totals = budget_totals(family)
            pledged = sum(c.monthly_equivalent_cents for c in family.contacts if c.status == 'Pledged')
            received = db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(Receipt.family_id == family.id))
            approved = db.session.scalar(select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
                Expense.family_id == family.id, Expense.status == 'Approved',
                Expense.category != 'Organization expense'))
            paid = db.session.scalar(select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
                Expense.family_id == family.id, Expense.status == 'Paid',
                Expense.category != 'Organization expense'))
            org_costs = db.session.scalar(select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
                Expense.family_id == family.id, Expense.category == 'Organization expense',
                Expense.status == 'Paid'))
            rows.append(dict(family=family, **totals, pledged=pledged, received=received,
                             approved=approved, paid=paid, organization_costs=org_costs))
        return render_template('reports.html', title='Reports', rows=rows)

    @app.route('/controls', methods=['GET', 'POST'])
    def controls():
        require_organization_admin()
        if request.method == 'POST':
            import json
            categories = [x.strip() for x in request.form.get('categories', '').splitlines() if x.strip()]
            try:
                bands = json.loads(request.form.get('child_bands', '[]'))
            except ValueError:
                abort(400, 'Enter valid child estimate settings.')
            if not categories or len(categories) > len(DEFAULT_CATEGORIES) or any(x not in DEFAULT_CATEGORIES for x in categories):
                abort(400, 'Choose valid expense categories.')
            try:
                valid_bands = valid_child_bands(bands)
            except (KeyError, TypeError, ValueError):
                valid_bands = False
            if not valid_bands:
                abort(400, 'Enter valid child estimate settings.')
            for key, value in [('expense_categories', categories), ('child_estimate_bands', bands)]:
                row = db.session.get(OrganizationSetting, key)
                if row: row.value = value
                else: db.session.add(OrganizationSetting(key=key, value=value))
            audit('Updated organization controls')
            db.session.commit()
            flash('Controls saved.')
            return redirect(url_for('controls'))
        import json
        return render_template('controls.html', title='Controls', categories=expense_categories(),
                               bands_json=json.dumps(child_bands(), indent=2))

    @app.route('/people-access', methods=['GET', 'POST'])
    def people_access():
        require_organization_admin()
        return staff()

    @app.get('/expenses')
    def expenses():
        require_capability(('family_admin', 'office_employee'))
        status = request.args.get('status', '')
        statement = select(Expense).order_by(Expense.id.desc())
        if status:
            if status not in EXPENSE_TRANSITIONS: abort(400)
            statement = statement.where(Expense.status==status)
        if not organization_admin():
            statement = statement.where(Expense.family_id.in_(select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        return render_template('expenses.html', title='Expenses & approvals', expenses=db.session.scalars(statement).all(), selected_status=status)

    @app.post('/expenses/<int:expense_id>/status')
    def expense_status(expense_id):
        require_organization_admin()
        expense = db.get_or_404(Expense, expense_id)
        status = field('status', True)
        if status not in EXPENSE_TRANSITIONS[expense.status]: abort(400, 'This expense transition is not allowed.')
        if status in ('Approved','Paid') and expense.family.status != 'Active': abort(400, 'Only active cases can have expenses approved or paid.')
        if status == 'Paid':
            expense.payment_reference = field('payment_reference', True, 200)
        old = expense.status
        expense.status = status
        audit(f'Expense #{expense.id}: {old} → {status}', expense.family_id)
        notify_users(assigned_users(expense.family_id, ('family_admin', 'office_employee')),
            'expense_status', f'Expense request for YZ-{expense.family_id:04d}: {status}',
            f'The ${expense.amount_cents / 100:,.2f} {expense.category} expense changed from {old} to {status}. Sign in to Yazory for details.',
            expense.family_id)
        db.session.commit()
        return redirect(url_for('expenses'))

    @app.get('/activity')
    def activity():
        require_organization_admin()
        return render_template('activity.html', title='Activity log', activity=db.session.scalars(select(Audit).order_by(Audit.id.desc()).limit(200)).all())

    @app.get('/emails')
    def email_history():
        require_organization_admin()
        messages = db.session.scalars(select(EmailMessage).order_by(EmailMessage.id.desc()).limit(250)).all()
        return render_template('email_history.html', title='Email history', messages=messages)

    @app.route('/staff', methods=['GET', 'POST'])
    def staff():
        require_organization_admin()
        if request.method == 'POST':
            email = email_field()
            role = field('role', True, 30)
            name = field('name')
            if role not in STAFF_ROLES:
                abort(400, 'Choose a valid role.')
            if db.session.scalar(select(StaffUser.id).where(StaffUser.email == email)):
                abort(400, 'A staff account already uses this email.')
            # Existing automated tests may still supply a password; real users always choose their own.
            test_password = request.form.get('password', '') if app.config['TESTING'] else ''
            user = StaffUser(email=email, name=name,
                password_hash=generate_password_hash(test_password) if len(test_password) >= 12 else '!invited',
                role=role, status='active' if len(test_password) >= 12 else 'pending',
                invited_at=utcnow())
            db.session.add(user)
            db.session.flush()
            family_id = request.form.get('family_id', type=int)
            if family_id and role != 'organization_admin':
                family = db.session.get(Family, family_id)
                if family is None:
                    abort(400, 'Choose a valid family assignment.')
                db.session.add(FamilyAssignment(staff_user_id=user.id, family_id=family.id))
            if user.status == 'pending':
                raw = account_token(user, 'invite', 48, current_user())
                link = absolute_url('accept_invitation', token=raw)
                message = send_email('staff_invitation', user.email, 'You are invited to Yazory',
                    f'You have been invited to Yazory as {role.replace("_", " ")}.\n\nAccept invitation: {link}\n\nThis secure link expires in 48 hours.',
                    staff_user_id=user.id)
            audit(f'Invited staff user: {email}')
            db.session.commit()
            flash('Invitation created, but email delivery failed. Check Email history.' if
                  user.status == 'pending' and message.status == 'failed' else
                  'Invitation created and email queued.')
            return redirect(url_for('staff'))
        owner = db.session.scalar(select(StaffUser).where(StaffUser.email == app.config['ADMIN_EMAIL'].strip().lower()))
        return render_template('staff.html', title='Staff & assignments', users=db.session.scalars(select(StaffUser).order_by(StaffUser.email)).all(), families=db.session.scalars(select(Family).order_by(Family.name)).all(), owner_user_id=owner.id if owner else None)

    @app.post('/staff/<int:user_id>/resend-invitation')
    def resend_invitation(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        if user.status != 'pending':
            abort(400, 'Only pending invitations can be resent.')
        db.session.execute(db.update(AccountToken).where(
            AccountToken.staff_user_id == user.id, AccountToken.purpose == 'invite',
            AccountToken.used_at.is_(None)).values(used_at=utcnow()))
        raw = account_token(user, 'invite', 48, current_user())
        user.invited_at = utcnow()
        message = send_email('staff_invitation', user.email, 'You are invited to Yazory',
            f'Your Yazory invitation was renewed.\n\nAccept invitation: {absolute_url("accept_invitation", token=raw)}\n\nThis secure link expires in 48 hours.',
            staff_user_id=user.id)
        audit(f'Resent staff invitation: {user.email}')
        db.session.commit()
        flash('Invitation renewed, but email delivery failed. Check Email history.' if
              message.status == 'failed' else 'Invitation resent.')
        return redirect(url_for('staff'))

    @app.post('/staff/<int:user_id>/status')
    def staff_status(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        new_status = field('status', True, 20)
        owner_email = app.config['ADMIN_EMAIL'].strip().lower()
        if user.email == owner_email or new_status not in ('active', 'deactivated'):
            abort(400, 'This account status cannot be changed.')
        if user.status == 'pending':
            abort(400, 'Cancel the pending invitation instead.')
        user.status = new_status
        audit(f'{"Activated" if new_status == "active" else "Deactivated"} staff user: {user.email}')
        db.session.commit()
        flash('Account status updated.')
        return redirect(url_for('staff'))

    @app.post('/staff/<int:user_id>/cancel-invitation')
    def cancel_invitation(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        if user.status != 'pending':
            abort(400, 'Only pending invitations can be cancelled.')
        user.status = 'cancelled'
        db.session.execute(db.update(AccountToken).where(
            AccountToken.staff_user_id == user.id, AccountToken.purpose == 'invite',
            AccountToken.used_at.is_(None)).values(used_at=utcnow()))
        audit(f'Cancelled staff invitation: {user.email}')
        db.session.commit()
        flash('Invitation cancelled.')
        return redirect(url_for('staff'))

    @app.get('/settings')
    def settings():
        require_organization_admin()
        return redirect(url_for('controls'))

    @app.post('/staff/<int:user_id>/role')
    def staff_role(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        role = field('role', True, 30)
        if role not in STAFF_ROLES:
            abort(400)
        if user.email == app.config['ADMIN_EMAIL'].strip().lower() and role != 'organization_admin':
            abort(400, 'The owner organization administrator cannot be demoted.')
        if user.role == 'organization_admin' and role != 'organization_admin':
            admin_count = db.session.scalar(select(func.count()).select_from(StaffUser).where(
                StaffUser.role == 'organization_admin'))
            if admin_count <= 1:
                abort(400, 'At least one organization administrator is required.')
        user.role = role
        if role == 'organization_admin':
            db.session.execute(db.delete(FamilyAssignment).where(FamilyAssignment.staff_user_id == user.id))
        audit(f'Updated staff role for {user.email}')
        db.session.commit()
        return redirect(url_for('staff'))

    @app.post('/staff/<int:user_id>/assignments')
    def staff_assignment(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        family = db.get_or_404(Family, request.form.get('family_id', type=int))
        if user.role == 'organization_admin':
            abort(400, 'Organization administrators do not use family assignments.')
        assignment = db.session.scalar(select(FamilyAssignment).where(FamilyAssignment.staff_user_id == user.id, FamilyAssignment.family_id == family.id))
        if assignment:
            db.session.delete(assignment)
            action = ('Revoked family administrator: ' if user.role == 'family_admin'
                      else 'Revoked staff assignment: ')
        else:
            db.session.add(FamilyAssignment(staff_user_id=user.id, family_id=family.id))
            action = ('Assigned family administrator: ' if user.role == 'family_admin'
                      else 'Assigned staff member: ')
        audit(f'{action}{user.email}', family.id)
        if user.status == 'active':
            change = 'removed from' if assignment else 'assigned to'
            send_email('family_assignment', user.email, f'Yazory family access {"removed" if assignment else "assigned"}',
                f'You were {change} case YZ-{family.id:04d}. Sign in to Yazory to review your current assignments.',
                staff_user_id=user.id, family_id=family.id)
        db.session.commit()
        return redirect(url_for('staff'))

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error(exc):
        return render_template('error.html', title='Unable to complete request', message=exc.description), exc.code

    @app.cli.command('init-db')
    def init_db():
        ensure_schema()
        contact_columns = {column['name'] for column in inspect(db.engine).get_columns('contact')}
        if 'supporter_key' not in contact_columns:
            db.session.execute(text("ALTER TABLE contact ADD COLUMN supporter_key VARCHAR(200) DEFAULT '' NOT NULL"))
        if 'pledge_frequency' not in contact_columns:
            db.session.execute(text("ALTER TABLE contact ADD COLUMN pledge_frequency VARCHAR(20) DEFAULT 'Monthly' NOT NULL"))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_contact_supporter_key ON contact (supporter_key)'))
        db.session.commit()
        for contact in db.session.scalars(select(Contact).where(Contact.supporter_key == '')).all():
            contact.supporter_key = supporter_key(contact.name, contact.phone)
        db.session.commit()
        ensure_bootstrap_owner()
        print('Database initialized. Existing records preserved.')

    @app.cli.command('migrate-db')
    def migrate_db():
        """Add tables absent from a legacy deployment; never drop or rewrite data."""
        db.create_all()
        print('Database migration completed. Existing records preserved.')

    with app.app_context():
        # Hosting can start Gunicorn without executing the configured pre-start
        # command. Apply the additive, idempotent upgrades here as well so no
        # request can reach a model whose columns are missing in production.
        ensure_schema()
        if app.config['DEMO']:
            if not db.session.scalar(select(Family.id).limit(1)):
                family = Family(name='Sample family', spouse='Sample spouse', father='Sample father', inlaws='Sample in-laws', rabbi='Community rabbi', weekday_shul='Local shul', shabbos_shul='Local shul', circumstances='Fictional example: a household needs help with everyday expenses during illness.', status='Active')
                db.session.add(family)
                db.session.flush()
                db.session.add_all([Child(family_id=family.id, name='Sample child', age=9, grade='4', school='Sample school', tuition_contact='School tuition office'), Contact(family_id=family.id, name='Sample sibling', relationship='Sibling', monthly_cents=18000, status='Pledged'), Expense(family_id=family.id, category='Groceries', payee='Sample grocery', amount_cents=45000, month=datetime.now().strftime('%Y-%m'))])
                audit_entry = Audit(actor='System', action='Created fictional demo records', family_id=family.id)
                db.session.add(audit_entry)
                db.session.commit()
        else:
            ensure_bootstrap_owner()
    return app

if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
