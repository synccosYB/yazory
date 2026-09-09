import os
import secrets
import hmac
import re
import hashlib
from html import escape
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import case, select, func, or_, UniqueConstraint, inspect, text
from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from translations import LANGUAGES, translate, translate_audit

from intake import validate_intake, intake_for_form
from budget_report import household_report
import child_budget
from email_service import deliver
from stripe_gateway import (create_account_link, create_checkout_session,
                            create_billing_portal_session, create_connected_account, create_transfer,
                            construct_webhook_event, retrieve_connected_account)

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
    yeshivah = db.Column(db.String(160), default='')
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

class Institution(db.Model):
    """A shared shul or yeshivah record used across every person profile."""
    __table_args__ = (UniqueConstraint('kind', 'name', 'city', name='uq_institution_kind_name_city'),)
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    address = db.Column(db.String(240), nullable=False, default='')
    city = db.Column(db.String(120), nullable=False, default='')
    state = db.Column(db.String(80), nullable=False, default='')
    phone = db.Column(db.String(80), nullable=False, default='')
    affiliations = db.relationship('PersonAffiliation', backref='institution', lazy=True,
                                   cascade='all, delete-orphan', order_by='PersonAffiliation.id')

class PersonAffiliation(db.Model):
    """Connect any Yazory person to a shul or a graded yeshivah history row."""
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=False, index=True)
    person_type = db.Column(db.String(20), nullable=False, index=True)
    person_id = db.Column(db.Integer, nullable=False, index=True)
    grade = db.Column(db.String(80), nullable=False, default='')
    year_from = db.Column(db.Integer, nullable=True)
    year_to = db.Column(db.Integer, nullable=True)
    note = db.Column(db.String(300), nullable=False, default='')

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
    phone = db.Column(db.String(80), nullable=False, default='')
    address = db.Column(db.String(240), nullable=False, default='')
    city = db.Column(db.String(120), nullable=False, default='')
    state = db.Column(db.String(80), nullable=False, default='')
    zip_code = db.Column(db.String(20), nullable=False, default='')
    job_title = db.Column(db.String(120), nullable=False, default='')
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


class StripePayment(db.Model):
    """A Stripe Checkout attempt tied to one case-specific supporter pledge."""
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=False, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)
    checkout_session_id = db.Column(db.String(255), unique=True, index=True)
    checkout_url = db.Column(db.Text, default='')
    payment_intent_id = db.Column(db.String(255), default='', index=True)
    subscription_id = db.Column(db.String(255), default='', index=True)
    customer_id = db.Column(db.String(255), default='', index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='usd')
    frequency = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='creating', index=True)
    successful_charges = db.Column(db.Integer, nullable=False, default=0)
    last_paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    contact = db.relationship('Contact', backref=db.backref('stripe_payments', lazy=True))
    family = db.relationship('Family')


class StripeEvent(db.Model):
    """Processed webhook IDs make financial side effects idempotent."""
    id = db.Column(db.String(255), primary_key=True)
    event_type = db.Column(db.String(100), nullable=False, index=True)
    received_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class StripeRecipient(db.Model):
    """A family or vendor that receives funds through a Stripe connected account."""
    __table_args__ = (UniqueConstraint('kind', 'recipient_key', name='uq_stripe_recipient_kind_key'),)
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    recipient_key = db.Column(db.String(200), nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    stripe_account_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    details_submitted = db.Column(db.Boolean, nullable=False, default=False)
    payouts_enabled = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(30), nullable=False, default='onboarding', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    family = db.relationship('Family')


class StripeTransfer(db.Model):
    """A transfer from Yazory to a verified connected-account balance."""
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'), nullable=False, unique=True, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('stripe_recipient.id'), nullable=False, index=True)
    stripe_transfer_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='usd')
    status = db.Column(db.String(30), nullable=False, default='transferred', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expense = db.relationship('Expense')
    recipient = db.relationship('StripeRecipient')

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

class CharityCampaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, unique=True)
    external_id = db.Column(db.String(100), nullable=False, unique=True)
    key_env = db.Column(db.String(100), nullable=False, unique=True)
    label = db.Column(db.String(160), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    last_sync = db.Column(db.DateTime)
    last_error = db.Column(db.String(300))

class CharityDonor(db.Model):
    __table_args__ = (UniqueConstraint('campaign_id', 'identity'),)
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('charity_campaign.id'), nullable=False)
    identity = db.Column(db.String(300), nullable=False)
    name = db.Column(db.String(300), nullable=False)
    email = db.Column(db.String(300), nullable=False)
    phone = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'))

class CharityDonation(db.Model):
    __table_args__ = (UniqueConstraint('campaign_id', 'external_id'),)
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('charity_campaign.id'), nullable=False)
    external_id = db.Column(db.String(100), nullable=False)
    donor_id = db.Column(db.Integer, db.ForeignKey('charity_donor.id'), nullable=False)
    donor = db.relationship('CharityDonor')
    amount_cents = db.Column(db.BigInteger, nullable=False)
    net_cents = db.Column(db.BigInteger, nullable=False)
    donation_time = db.Column(db.DateTime, nullable=False)
    anonymous = db.Column(db.Boolean, nullable=False)
    subscription = db.Column(db.Boolean, nullable=False)
    team = db.Column(db.String(300), nullable=False)
    notes = db.Column(db.Text, nullable=False)

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
                      APP_BASE_URL=os.getenv('APP_BASE_URL', '').rstrip('/'),
                      STRIPE_SECRET_KEY=os.getenv('STRIPE_SECRET_KEY', ''),
                      STRIPE_PUBLISHABLE_KEY=os.getenv('STRIPE_PUBLISHABLE_KEY', ''),
                      STRIPE_WEBHOOK_SECRET=os.getenv('STRIPE_WEBHOOK_SECRET', ''),
                      STRIPE_CONNECT_COUNTRY=os.getenv('STRIPE_CONNECT_COUNTRY', 'US').upper(),
                      STRIPE_CURRENCY=os.getenv('STRIPE_CURRENCY', 'usd').lower())
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

    @app.template_filter('phone')
    def phone(value):
        """Display North American phone numbers consistently without altering saved data."""
        value = (value or '').strip()
        digits = re.sub(r'\D', '', value)
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        if len(digits) == 10:
            return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'
        return value

    def supporter_key(name, phone, fallback=None):
        """Identify one supporter across cases by phone; names are not unique."""
        digits = re.sub(r'\D', '', phone or '')
        if len(digits) >= 7:
            return 'phone:' + digits[-10:]
        return fallback or 'record:' + secrets.token_hex(16)

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
        safe_body = re.sub(
            r'(https?://[^\s<]+)',
            r'<a href="\1" style="display:inline-block;background:#b49a52;color:#172f4c;font-weight:700;line-height:1.4;text-decoration:none;padding:11px 17px;border-radius:5px;word-break:break-word">\1</a>',
            safe_body)
        paragraphs = ''.join(
            f'<p style="margin:0 0 18px;color:#17385f;font-size:16px;line-height:1.65">'
            f'{paragraph.replace(chr(10), "<br>")}</p>'
            for paragraph in safe_body.split('\n\n') if paragraph
        )
        logo_url = absolute_url('static', filename='yazory-logo.png')
        html = f'''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8f7f3;font-family:Arial,'Segoe UI',sans-serif;color:#17385f">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f8f7f3">
<tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:620px;background:#ffffff;border:1px solid #e3e5e9;border-radius:8px;overflow:hidden">
<tr><td align="center" style="background:#ffffff;padding:24px 24px 18px;border-bottom:4px solid #b49a52">
<img src="{logo_url}" width="150" alt="Yazory · יעזורי" style="display:block;width:150px;max-width:45%;height:auto;border:0">
</td></tr>
<tr><td style="padding:34px 38px 24px">{paragraphs}</td></tr>
<tr><td style="background:#173e66;padding:20px 28px;text-align:center;color:#ffffff">
<div style="font-size:14px;font-weight:700;letter-spacing:.3px">Yazory · יעזורי</div>
<div style="margin-top:6px;color:#d4dfeb;font-size:12px;line-height:1.5">A circle of support.</div>
</td></tr>
</table>
</td></tr></table>
</body></html>'''
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
            'phone': "VARCHAR(80) NOT NULL DEFAULT ''",
            'address': "VARCHAR(240) NOT NULL DEFAULT ''",
            'city': "VARCHAR(120) NOT NULL DEFAULT ''",
            'state': "VARCHAR(80) NOT NULL DEFAULT ''",
            'zip_code': "VARCHAR(20) NOT NULL DEFAULT ''",
            'job_title': "VARCHAR(120) NOT NULL DEFAULT ''",
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
            'yeshivah': 'VARCHAR(160)',
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
        # Older versions stored names entered through "Add another child" as
        # display-only ContactChild rows. Promote them once into real supporter
        # profiles so they have their own status, pledge, history, and page.
        for legacy_child in db.session.scalars(select(ContactChild).order_by(ContactChild.id)).all():
            parent = db.session.get(Contact, legacy_child.contact_id)
            if parent is None:
                continue
            child_contact = Contact(
                family_id=parent.family_id, name=legacy_child.name,
                relationship='Nephew', phone=legacy_child.phone or '',
                supporter_key=supporter_key(legacy_child.name, legacy_child.phone),
                parent_contact_id=parent.id, parent_connection='Son',
                monthly_cents=0, pledge_frequency='Monthly', status='To contact')
            db.session.add(child_contact)
            db.session.flush()
            db.session.execute(db.update(PersonAffiliation).where(
                PersonAffiliation.person_type == 'supporter_child',
                PersonAffiliation.person_id == legacy_child.id).values(
                    person_type='supporter', person_id=child_contact.id))
            if legacy_child.spouse_name:
                spouse_contact = Contact(
                    family_id=parent.family_id, name=legacy_child.spouse_name,
                    relationship='Nephew', phone='',
                    supporter_key=supporter_key(legacy_child.spouse_name, ''),
                    parent_contact_id=parent.id, parent_connection='Son-in-law',
                    monthly_cents=0, pledge_frequency='Monthly', status='To contact')
                db.session.add(spouse_contact)
                db.session.flush()
                db.session.execute(db.update(PersonAffiliation).where(
                    PersonAffiliation.person_type == 'supporter_child_spouse',
                    PersonAffiliation.person_id == legacy_child.id).values(
                        person_type='supporter', person_id=spouse_contact.id))
            db.session.delete(legacy_child)
        # Correct this known legacy entry: it was entered through the old
        # child-only form, but he is the supporter's son-in-law.
        for contact in db.session.scalars(select(Contact).where(
                Contact.name == 'נתן גרינפעלד')).all():
            if (contact.parent_supporter and
                    contact.parent_supporter.name == 'חיים אלעזר מנחם מענדל באכנער'):
                contact.parent_connection = 'Son-in-law'
        stripe_payment_columns = {column['name'] for column in inspect(db.engine).get_columns('stripe_payment')}
        if 'successful_charges' not in stripe_payment_columns:
            db.session.execute(text(
                'ALTER TABLE stripe_payment ADD COLUMN successful_charges INTEGER NOT NULL DEFAULT 0'))
        if 'last_paid_at' not in stripe_payment_columns:
            db.session.execute(text('ALTER TABLE stripe_payment ADD COLUMN last_paid_at TIMESTAMP'))
        # Backfill the central directories from every profile that already has
        # shul or yeshivah details. The helpers are idempotent, so startup never
        # creates duplicate people or institutions.
        for family in db.session.scalars(select(Family)).all():
            connect_family_profile_directories(family)
        for child in db.session.scalars(select(Child)).all():
            connect_child_profile_directory(child)
        merge_duplicate_institutions()
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

    def directory_people():
        """Return every connectable person without merging people who share a name."""
        people = []
        for family in db.session.scalars(select(Family).order_by(Family.name)).all():
            people.append(('family', family.id, family.name, 'Applicant', family.name))
            if family.spouse:
                people.append(('spouse', family.id, family.spouse, 'Spouse', family.name))
        for child in db.session.scalars(select(Child).order_by(Child.name)).all():
            people.append(('child', child.id, child.name, 'Child', child.family.name))
            if child.spouse_name:
                people.append(('child_spouse', child.id, child.spouse_name, 'Spouse', child.name))
        for supporter in db.session.scalars(select(Contact).order_by(Contact.name)).all():
            people.append(('supporter', supporter.id, supporter.name, 'Supporter', supporter.family.name))
        for child in db.session.scalars(select(ContactChild).order_by(ContactChild.name)).all():
            people.append(('supporter_child', child.id, child.name, 'Supporter’s child', child.contact.name))
            if child.spouse_name:
                people.append(('supporter_child_spouse', child.id, child.spouse_name, 'Spouse', child.name))
        for user in db.session.scalars(select(StaffUser).order_by(StaffUser.name, StaffUser.email)).all():
            people.append(('staff', user.id, user.name or user.email, 'Staff member', user.email))
        return people

    def directory_person_hierarchy():
        """Describe how directory people nest beneath their household or parent."""
        hierarchy = {}
        for family in db.session.scalars(select(Family).order_by(Family.name)).all():
            root = ('family', family.id)
            hierarchy[root] = {'depth': 0, 'parent_name': '',
                               'sort_key': (family.name.lower(), 0, family.name.lower())}
            if family.spouse:
                hierarchy[('spouse', family.id)] = {
                    'depth': 1, 'parent_name': family.name,
                    'sort_key': (family.name.lower(), 1, family.spouse.lower())}
            for child in sorted(family.children, key=lambda row: row.name.lower()):
                hierarchy[('child', child.id)] = {
                    'depth': 1, 'parent_name': family.name,
                    'sort_key': (family.name.lower(), 2, child.name.lower(), 0)}
                if child.spouse_name:
                    hierarchy[('child_spouse', child.id)] = {
                        'depth': 2, 'parent_name': child.name,
                        'sort_key': (family.name.lower(), 2, child.name.lower(), 1,
                                     child.spouse_name.lower())}
        for supporter in db.session.scalars(select(Contact).order_by(Contact.name)).all():
            parent = supporter.parent_supporter
            root_name = parent.name if parent else supporter.name
            hierarchy[('supporter', supporter.id)] = {
                'depth': 1 if parent else 0,
                'parent_name': parent.name if parent else '',
                'sort_key': ('supporter', supporter.family.name.lower(), root_name.lower(),
                             1 if parent else 0, supporter.name.lower())}
            for child in supporter.children:
                hierarchy[('supporter_child', child.id)] = {
                    'depth': 1, 'parent_name': supporter.name,
                    'sort_key': ('supporter', supporter.family.name.lower(),
                                 supporter.name.lower(), 2, child.name.lower(), 0)}
                if child.spouse_name:
                    hierarchy[('supporter_child_spouse', child.id)] = {
                        'depth': 2, 'parent_name': child.name,
                        'sort_key': ('supporter', supporter.family.name.lower(),
                                     supporter.name.lower(), 2, child.name.lower(), 1,
                                     child.spouse_name.lower())}
        return hierarchy

    def valid_directory_person(person_type, person_id):
        return any(kind == person_type and row_id == person_id
                   for kind, row_id, *_ in directory_people())

    def find_or_create_institution(kind, name, city='', state=''):
        """Reuse one central institution record when profile fields name it."""
        name, city, state = (name or '').strip(), (city or '').strip(), (state or '').strip()
        if not name:
            return None
        institution = db.session.scalar(select(Institution).where(
            Institution.kind == kind,
            func.lower(Institution.name) == name.lower(),
        ))
        if institution is None:
            institution = Institution(kind=kind, name=name, city=city, state=state)
            db.session.add(institution)
            db.session.flush()
        return institution

    def merge_duplicate_institutions():
        """Merge same-named rows that were accidentally created with different cities."""
        canonical_by_name = {}
        for duplicate in db.session.scalars(select(Institution).order_by(Institution.id)).all():
            key = (duplicate.kind, duplicate.name.strip().casefold())
            canonical = canonical_by_name.get(key)
            if canonical is None:
                canonical_by_name[key] = duplicate
                continue
            for attribute in ('address', 'city', 'state', 'phone'):
                if not getattr(canonical, attribute) and getattr(duplicate, attribute):
                    setattr(canonical, attribute, getattr(duplicate, attribute))
            for affiliation in list(duplicate.affiliations):
                existing = db.session.scalar(select(PersonAffiliation.id).where(
                    PersonAffiliation.institution_id == canonical.id,
                    PersonAffiliation.person_type == affiliation.person_type,
                    PersonAffiliation.person_id == affiliation.person_id,
                    PersonAffiliation.grade == affiliation.grade,
                    PersonAffiliation.year_from == affiliation.year_from,
                    PersonAffiliation.year_to == affiliation.year_to,
                ))
                if existing:
                    db.session.delete(affiliation)
                else:
                    affiliation.institution = canonical
            db.session.delete(duplicate)

    def ensure_profile_affiliation(institution, person_type, person_id, grade='', note=''):
        if institution is None:
            return None
        existing = db.session.scalar(select(PersonAffiliation).where(
            PersonAffiliation.institution_id == institution.id,
            PersonAffiliation.person_type == person_type,
            PersonAffiliation.person_id == person_id,
            PersonAffiliation.grade == grade,
        ))
        if existing is None:
            existing = PersonAffiliation(
                institution_id=institution.id, person_type=person_type,
                person_id=person_id, grade=grade, note=note)
            db.session.add(existing)
        return existing

    def connect_family_profile_directories(family, yeshivah_history=None):
        """Keep the applicant connected to profile shuls and yeshivah."""
        seen = set()
        current_institution_ids = set()
        for label, shul_name in (('Weekday shul', family.weekday_shul),
                                 ('Shabbos shul', family.shabbos_shul)):
            normalized = (shul_name or '').strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            institution = find_or_create_institution(
                'Shul', shul_name, family.city, family.state)
            current_institution_ids.add(institution.id)
            ensure_profile_affiliation(
                institution, 'family', family.id, note=label + ' · Family profile')
        if yeshivah_history is not None:
            db.session.execute(db.delete(PersonAffiliation).where(
                PersonAffiliation.person_type == 'family',
                PersonAffiliation.person_id == family.id,
                PersonAffiliation.institution_id.in_(select(Institution.id).where(
                    Institution.kind == 'Yeshivah'))))
            for history in yeshivah_history:
                yeshivah = find_or_create_institution('Yeshivah', history['name'])
                current_institution_ids.add(yeshivah.id)
                db.session.add(PersonAffiliation(
                    institution_id=yeshivah.id, person_type='family',
                    person_id=family.id, grade=history['grade'],
                    year_from=history['year_from'], year_to=history['year_to'],
                    note='Applicant profile · Family profile'))
        else:
            yeshivah = find_or_create_institution('Yeshivah', family.yeshivah)
            if yeshivah is not None:
                current_institution_ids.add(yeshivah.id)
                ensure_profile_affiliation(
                    yeshivah, 'family', family.id, note='Applicant profile · Family profile')

        # Replace only the automatic profile links; keep manually entered links.
        automatic = db.session.scalars(select(PersonAffiliation).where(
            PersonAffiliation.person_type == 'family',
            PersonAffiliation.person_id == family.id,
            PersonAffiliation.note.contains('Family profile'),
        )).all()
        for affiliation in automatic:
            if affiliation.institution_id not in current_institution_ids:
                db.session.delete(affiliation)

    def connect_child_profile_directory(child):
        """Connect a child to the yeshivah and grade saved on that child."""
        if not (child.school or '').strip() or not (child.grade or '').strip():
            return
        institution = find_or_create_institution('Yeshivah', child.school)
        ensure_profile_affiliation(
            institution, 'child', child.id, grade=child.grade,
            note='Child profile')

    def setting(key, default):
        cache = g.setdefault('_settings_cache', {})
        if key in cache:
            return cache[key]
        row = db.session.get(OrganizationSetting, key)
        value = row.value if row and isinstance(row.value, type(default)) else default
        cache[key] = value
        return value

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

    budget_not_provided = object()

    def budget_totals(family, budget_record=budget_not_provided):
        """One authoritative calculation shared by every budget-facing screen."""
        intake = family.intake_record.data if family.intake_record else {}
        record = (db.session.get(HouseholdBudget, family.id)
                  if budget_record is budget_not_provided else budget_record)
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

    @app.template_filter('eastern_time')
    def eastern_time(value, format_string='%m/%d/%Y %I:%M %p %Z'):
        """Render UTC database timestamps in the organization's Eastern timezone."""
        if value is None:
            return ''
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo('America/New_York')).strftime(format_string)
    from workflows import install_workflows
    install_workflows(app, db, globals(), dict(current_user=current_user, organization_admin=organization_admin,
        can_access_family=can_access_family))
    from supporter_network import install_network
    install_network(app, db, globals(), dict(current_user=current_user, can_access_family=can_access_family, supporter_key=supporter_key))

    @app.context_processor
    def common():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        user = current_user()
        return dict(language=session.get('language', 'en'), languages=LANGUAGES, direction='rtl' if session.get('language') in ('he','yi') else 'ltr', csrf=session['csrf'], demo=app.config['DEMO'], stripe_enabled=bool(app.config['STRIPE_SECRET_KEY']), categories=expense_categories(), relationships=RELATIONSHIPS, contact_statuses=CONTACT_STATUSES, pledge_frequencies=PLEDGE_FREQUENCIES, family_transitions=FAMILY_TRANSITIONS, expense_transitions=EXPENSE_TRANSITIONS, current_month=datetime.now().strftime('%Y-%m'), document_allowed=app.extensions['workflows']['document_allowed'], contact_visible=contact_visible, current_staff=user, is_org_admin=organization_admin(), can_manage_household=can_manage_household(), can_manage_supporters=can_manage_supporters(), is_fundraiser=bool(user and user.role == 'fundraiser'))

    @app.before_request
    def security():
        public_endpoints = ('static', 'health', 'set_language', 'login', 'forgot_password',
                            'reset_password', 'accept_invitation', 'about', 'privacy',
                            'terms', 'donation_policy', 'stripe_webhook',
                            'stripe_success', 'stripe_cancel')
        if request.endpoint in ('static', 'health', 'set_language'):
            return
        if request.method == 'POST' and request.endpoint != 'stripe_webhook':
            if not session.get('csrf') or not hmac.compare_digest(
                    session.get('csrf', ''), request.form.get('csrf', '')):
                abort(400, 'Your form expired. Reload the page and try again.')
        if not app.config['DEMO'] and request.endpoint not in public_endpoints:
            if not session.get('user_id'):
                return redirect(url_for('login'))
            if current_user() is None or not app.extensions['workflows']['active_user'](current_user()):
                language = session.get('language', 'en')
                session.clear()
                session['language'] = language
                return redirect(url_for('login'))

    @app.before_request
    def audit_read_only():
        if not app.config['DEMO'] and current_user() and request.method=='POST' and current_user().role!='organization_admin' and app.extensions['workflows']['roles']()=={'auditor'} and request.endpoint not in ('work_action','logout'):
            abort(403, 'Auditor access is read-only outside assigned audit reviews.')

    @app.before_request
    def preserve_closed_case():
        if not app.extensions['workflows']['enforced']() or request.method!='POST':return
        if request.endpoint in ('edit_family','family_expense_report','add_child','add_contact','add_document'):
            family_id=(request.view_args or {}).get('family_id')
            if can_access_family(family_id):
                family=db.session.get(Family,family_id)
                if family and family.status=='Closed':abort(400,'Reopen the case before starting new operations.')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = ("default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' https://js.stripe.com; connect-src 'self' https://api.stripe.com https://checkout.stripe.com; "
            "frame-src https://js.stripe.com https://hooks.stripe.com https://checkout.stripe.com; "
            "img-src 'self' data: https://*.stripe.com; base-uri 'self'; form-action 'self' https://checkout.stripe.com; frame-ancestors 'none'")
        # Versioned static URLs are safe to retain locally. Previously every
        # navigation downloaded the stylesheet, scripts and logo again.
        if request.endpoint == 'static':
            response.headers['Cache-Control'] = 'public, max-age=86400'
        else:
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

    def stripe_value(value, key, default=None):
        if value is None:
            return default
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def stripe_receipt(contact, amount_cents, reference, donor_email=''):
        existing = db.session.scalar(select(Receipt).where(Receipt.reference == reference))
        if existing:
            return existing, False
        receipt = Receipt(contact_id=contact.id, family_id=contact.family_id,
                          amount_cents=amount_cents, received_on=date.today(),
                          reference=reference, note='Processed securely by Stripe')
        db.session.add(receipt)
        if donor_email:
            send_email('donation_receipt', donor_email, 'Your Yazory donation receipt',
                       f'Thank you for your donation of ${amount_cents / 100:,.2f}.\n\n'
                       f'Receipt reference: {reference}\n\n'
                       'Yazory is developed and operated by Synccos Inc.',
                       family_id=contact.family_id)
        return receipt, True

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

    def public_page(page, title):
        return render_template('public_site.html', page=page, title=title)

    @app.get('/about')
    def about():
        return public_page('about', 'About Yazory')

    @app.get('/privacy')
    def privacy():
        return public_page('privacy', 'Privacy policy')

    @app.get('/terms')
    def terms():
        return public_page('terms', 'Terms of service')

    @app.get('/donation-policy')
    def donation_policy():
        return public_page('donation-policy', 'Donation and recurring payment policy')

    @app.get('/supporters/<int:contact_id>/donate')
    def supporter_donation(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        return render_template(
            'donation_checkout.html', title='Donation checkout', supporter=contact,
            default_amount=contact.monthly_cents / 100 if contact.monthly_cents >= 100 else 1,
            default_frequency=contact.pledge_frequency if contact.monthly_cents >= 100 else 'One time',
            stripe_publishable_key=app.config['STRIPE_PUBLISHABLE_KEY'])

    @app.post('/supporters/<int:contact_id>/embedded-checkout-session')
    def embedded_checkout_session(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        if not app.config['STRIPE_SECRET_KEY'] or not app.config['STRIPE_PUBLISHABLE_KEY']:
            return {'error': 'Embedded Stripe Checkout is not configured.'}, 503
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            return {'error': 'You are not assigned to this family.'}, 403
        payment_amount = amount('amount')
        frequency = field('frequency', True, 20)
        if frequency not in PLEDGE_FREQUENCIES:
            return {'error': 'Choose a valid donation frequency.'}, 400
        metadata = {'contact_id': str(contact.id), 'family_id': str(contact.family_id),
                    'amount_cents': str(payment_amount), 'frequency': frequency}
        line_item = {'price_data': {'currency': app.config['STRIPE_CURRENCY'],
                     'product_data': {'name': 'Yazory donation'},
                     'unit_amount': payment_amount}, 'quantity': 1}
        if frequency != 'One time':
            line_item['price_data']['recurring'] = {
                'interval': 'week' if frequency == 'Weekly' else 'month'}
        params = {
            'ui_mode': 'embedded',
            'mode': 'payment' if frequency == 'One time' else 'subscription',
            'line_items': [line_item], 'metadata': metadata,
            'return_url': absolute_url('stripe_success') + '?session_id={CHECKOUT_SESSION_ID}',
            'payment_intent_data': {'metadata': metadata} if frequency == 'One time' else None,
            'subscription_data': {'metadata': metadata} if frequency != 'One time' else None,
        }
        try:
            checkout = create_checkout_session(
                app.config['STRIPE_SECRET_KEY'],
                {key: value for key, value in params.items() if value is not None},
                f'yazory-embedded-{secrets.token_hex(16)}')
        except Exception as exc:
            app.logger.exception('Embedded Stripe Checkout creation failed')
            return {'error': getattr(exc, 'user_message', None) or
                    'Stripe could not prepare the payment form.'}, 502
        client_secret = stripe_value(checkout, 'client_secret', '')
        if not client_secret:
            return {'error': 'Stripe did not return an embedded payment form.'}, 502
        return {'client_secret': client_secret}

    @app.get('/stripe-payments/<int:payment_id>/manage')
    def manage_stripe_payment(payment_id):
        require_capability(('family_admin', 'fundraiser'))
        payment = db.get_or_404(StripePayment, payment_id)
        if not can_access_family(payment.family_id) or not contact_visible(db.session.get(Contact,payment.contact_id)):
            abort(403, 'You are not assigned to this family.')
        if not payment.subscription_id or not payment.customer_id:
            flash('This donation does not have an active recurring billing account.', 'error')
            return redirect(url_for('supporter_detail', contact_id=payment.contact_id))
        try:
            portal = create_billing_portal_session(
                app.config['STRIPE_SECRET_KEY'], payment.customer_id,
                absolute_url('supporter_detail', contact_id=payment.contact_id))
        except Exception as exc:
            app.logger.exception('Stripe billing portal creation failed')
            flash(getattr(exc, 'user_message', None) or
                  'Stripe could not open recurring-donation management.', 'error')
            return redirect(url_for('supporter_detail', contact_id=payment.contact_id))
        return redirect(stripe_value(portal, 'url', ''), code=303)

    @app.route('/supporters/<int:contact_id>/stripe-checkout', methods=['GET', 'POST'])
    def stripe_checkout(contact_id):
        """Create a Stripe-hosted payment page; Yazory never receives card details."""
        require_capability(('family_admin', 'fundraiser'))
        if not app.config['STRIPE_SECRET_KEY']:
            abort(503, 'Stripe payments are not configured.')
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        if request.method == 'GET':
            try:
                entered_amount = Decimal(request.args.get('amount', ''))
                if (not entered_amount.is_finite() or entered_amount <= 0 or
                        entered_amount > 1000000 or entered_amount.as_tuple().exponent < -2):
                    raise ValueError()
                payment_amount = int(entered_amount * 100)
            except (InvalidOperation, ValueError):
                abort(400, 'Enter a valid amount with up to two decimal places, no greater than $1,000,000.')
            frequency = request.args.get('frequency', '')[:20]
        else:
            payment_amount = amount('amount')
            frequency = field('frequency', True, 20)
        if frequency not in PLEDGE_FREQUENCIES:
            abort(400, 'Choose a valid donation frequency.')
        # Do not write to the database before opening Checkout. A blocked
        # database flush previously held the browser on "Opening Stripe…" even
        # though Stripe itself was reachable. Stripe returns the session first;
        # we then persist the local tracking record before redirecting the user.
        metadata = {
            'contact_id': str(contact.id), 'family_id': str(contact.family_id),
            'amount_cents': str(payment_amount), 'frequency': frequency,
        }
        line_item = {'price_data': {'currency': app.config['STRIPE_CURRENCY'],
                     'product_data': {'name': 'Yazory donation'},
                     'unit_amount': payment_amount}, 'quantity': 1}
        params = {'mode': 'payment' if frequency == 'One time' else 'subscription',
                  'line_items': [line_item], 'customer_creation': 'always' if frequency == 'One time' else None,
                  'success_url': absolute_url('stripe_success') + '?session_id={CHECKOUT_SESSION_ID}',
                  'cancel_url': absolute_url('stripe_cancel'), 'metadata': metadata,
                  'payment_intent_data': {'metadata': metadata} if frequency == 'One time' else None,
                  'subscription_data': {'metadata': metadata} if frequency != 'One time' else None}
        if frequency != 'One time':
            line_item['price_data']['recurring'] = {
                'interval': 'week' if frequency == 'Weekly' else 'month'}
        params = {key: value for key, value in params.items() if value is not None}
        try:
            checkout = create_checkout_session(app.config['STRIPE_SECRET_KEY'], params,
                                               f'yazory-checkout-{secrets.token_hex(16)}')
        except Exception as exc:
            db.session.rollback()
            # Stripe errors used to land on a generic 502 page, which made the
            # Checkout button look as though it had done nothing. Return the
            # supporter to the form and show Stripe's safe, user-facing reason.
            user_message = getattr(exc, 'user_message', None)
            app.logger.exception('Stripe Checkout session creation failed')
            flash(user_message or
                  'Stripe could not open the secure payment page. Check that the live Stripe account is activated and try again.',
                  'error')
            return redirect(url_for('supporter_detail', contact_id=contact.id))
        checkout_session_id = stripe_value(checkout, 'id', '')
        checkout_url = stripe_value(checkout, 'url', '')
        if not checkout_session_id or not checkout_url:
            flash('Stripe did not return a secure payment page. Please try again.', 'error')
            return redirect(url_for('supporter_detail', contact_id=contact.id))
        # Do not make the donor wait for a database write. The signed Stripe
        # webhook creates the local payment record when Checkout completes.
        return redirect(checkout_url, code=303)

    @app.get('/stripe/success')
    def stripe_success():
        payment = db.session.scalar(select(StripePayment).where(
            StripePayment.checkout_session_id == request.args.get('session_id', '')[:255]))
        return render_template('stripe_result.html', title='Donation received', success=True,
                               payment=payment)

    @app.get('/stripe/cancel')
    def stripe_cancel():
        return render_template('stripe_result.html', title='Donation not completed', success=False,
                               payment=None)

    @app.post('/stripe/webhook')
    def stripe_webhook():
        if not app.config['STRIPE_WEBHOOK_SECRET']:
            abort(503, 'Stripe webhooks are not configured.')
        try:
            event = construct_webhook_event(request.get_data(), request.headers.get('Stripe-Signature', ''),
                                            app.config['STRIPE_WEBHOOK_SECRET'])
        except Exception:
            abort(400, 'Invalid Stripe webhook signature.')
        event_id, event_type = stripe_value(event, 'id', ''), stripe_value(event, 'type', '')
        if not event_id or db.session.get(StripeEvent, event_id):
            return {'received': True}
        obj = stripe_value(stripe_value(event, 'data', {}), 'object', {})
        metadata = stripe_value(obj, 'metadata', {}) or {}
        if event_type.startswith('invoice.') and not metadata:
            parent = stripe_value(obj, 'parent', {}) or {}
            subscription_details = stripe_value(parent, 'subscription_details', {}) or {}
            if not subscription_details:
                subscription_details = stripe_value(obj, 'subscription_details', {}) or {}
            metadata = stripe_value(subscription_details, 'metadata', {}) or {}
        payment_id = stripe_value(metadata, 'yazory_payment_id', '')
        try:
            payment = db.session.get(StripePayment, int(payment_id)) if payment_id else None
        except (TypeError, ValueError):
            payment = None
        if payment is None and event_type == 'checkout.session.completed':
            payment = db.session.scalar(select(StripePayment).where(
                StripePayment.checkout_session_id == stripe_value(obj, 'id', '')))
        if payment is None and event_type.startswith('invoice.'):
            invoice_subscription = stripe_value(obj, 'subscription', '')
            if not invoice_subscription:
                invoice_parent = stripe_value(obj, 'parent', {}) or {}
                invoice_subscription = stripe_value(
                    stripe_value(invoice_parent, 'subscription_details', {}) or {},
                    'subscription', '')
            if invoice_subscription:
                payment = db.session.scalar(select(StripePayment).where(
                    StripePayment.subscription_id == invoice_subscription))
        if payment is None and event_type == 'checkout.session.completed':
            try:
                contact_id = int(stripe_value(metadata, 'contact_id', ''))
                family_id = int(stripe_value(metadata, 'family_id', ''))
                amount_cents = int(stripe_value(metadata, 'amount_cents', ''))
            except (TypeError, ValueError):
                contact_id = family_id = amount_cents = 0
            frequency = stripe_value(metadata, 'frequency', '')
            contact = db.session.get(Contact, contact_id) if contact_id else None
            if (contact and contact.family_id == family_id and amount_cents > 0 and
                    frequency in PLEDGE_FREQUENCIES):
                payment = StripePayment(
                    contact_id=contact.id, family_id=family_id,
                    amount_cents=amount_cents, currency=app.config['STRIPE_CURRENCY'],
                    frequency=frequency,
                    checkout_session_id=stripe_value(obj, 'id', ''), status='open')
                db.session.add(payment)
                db.session.flush()
        if event_type == 'checkout.session.completed' and payment:
            payment.checkout_session_id = stripe_value(obj, 'id', payment.checkout_session_id)
            payment.payment_intent_id = stripe_value(obj, 'payment_intent', '') or ''
            payment.subscription_id = stripe_value(obj, 'subscription', '') or ''
            payment.customer_id = stripe_value(obj, 'customer', '') or ''
            payment.status = 'active' if payment.subscription_id else 'paid'
            payment.completed_at = utcnow()
            if not payment.subscription_id:
                details = stripe_value(obj, 'customer_details', {}) or {}
                _, created = stripe_receipt(payment.contact, payment.amount_cents,
                                            f'stripe:{payment.payment_intent_id or payment.checkout_session_id}',
                                            stripe_value(details, 'email', '') or '')
                if created:
                    payment.successful_charges += 1
                    payment.last_paid_at = utcnow()
        elif event_type == 'invoice.paid' and payment:
            payment.status = 'active'
            payment.subscription_id = stripe_value(obj, 'subscription', payment.subscription_id) or payment.subscription_id
            _, created = stripe_receipt(payment.contact, stripe_value(obj, 'amount_paid', payment.amount_cents),
                                        f'stripe-invoice:{stripe_value(obj, "id", event_id)}',
                                        stripe_value(obj, 'customer_email', '') or '')
            if created:
                payment.successful_charges += 1
                payment.last_paid_at = utcnow()
        elif event_type in ('invoice.payment_failed', 'customer.subscription.paused') and payment:
            payment.status = 'past_due'
        elif event_type == 'customer.subscription.deleted' and payment:
            payment.status = 'cancelled'
        elif event_type == 'account.updated':
            recipient = db.session.scalar(select(StripeRecipient).where(
                StripeRecipient.stripe_account_id == stripe_value(obj, 'id', '')))
            if recipient:
                recipient.details_submitted = bool(stripe_value(obj, 'details_submitted', False))
                recipient.payouts_enabled = bool(stripe_value(obj, 'payouts_enabled', False))
                recipient.status = 'ready' if recipient.payouts_enabled else ('restricted' if recipient.details_submitted else 'onboarding')
                recipient.updated_at = utcnow()
        db.session.add(StripeEvent(id=event_id, event_type=event_type))
        db.session.commit()
        return {'received': True}

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            import time
            time.sleep(1)
            email = email_field()
            ensure_bootstrap_owner()
            user = db.session.scalar(select(StaffUser).where(StaffUser.email == email.lower()))
            if user and app.extensions['workflows']['active_user'](user) and check_password_hash(user.password_hash, request.form.get('password', '')):
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
        statement = select(Family).options(
            selectinload(Family.children), selectinload(Family.intake_record)
        ).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(statement).all()
        family_ids = [family.id for family in families]
        budget_records = {record.family_id: record for record in db.session.scalars(
            select(HouseholdBudget).where(HouseholdBudget.family_id.in_(family_ids))).all()
        } if family_ids else {}
        month = datetime.now().strftime('%Y-%m')
        expenses = db.session.scalars(select(Expense).where(Expense.month == month, Expense.family_id.in_(family_ids))).all()
        network_visible = organization_admin() or bool(current_user() and current_user().role in ('family_admin', 'fundraiser'))
        active_family_ids = select(Family.id).where(Family.status == 'Active', Family.id.in_(family_ids))
        pledged = unique_pledged_total(active_family_ids) if network_visible else 0
        if app.extensions['workflows']['enforced']() and network_visible:
            pledged = app.extensions['workflows']['monthly_pledged'](family_ids=[f.id for f in families if f.status=='Active'])
        requested_statement = select(Expense).where(Expense.status == 'Requested').order_by(Expense.id.desc())
        if not organization_admin():
            requested_statement = requested_statement.where(Expense.family_id.in_(
                select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        requested = db.session.scalars(requested_statement).all()
        received = db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.family_id.in_(family_ids))) if family_ids and network_visible else 0
        return render_template('dashboard.html', title='Overview', families=families, active=sum(f.status=='Active' for f in families), pledged=pledged, received=received, network_visible=network_visible, shortfall=sum(budget_totals(f, budget_records.get(f.id))['shortfall'] for f in families), approved=sum(e.amount_cents for e in expenses if e.status in ('Approved','Paid')), paid=sum(e.amount_cents for e in expenses if e.status=='Paid'), requested=requested)

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
            ('name','spouse','phone','address','city','state','zip_code','father','inlaws','inlaws_maiden_name','inlaws_family','rabbi','rabbi_phone','weekday_shul','shabbos_shul','yeshivah','shul_gabbai','shul_gabbai_phone','circumstances')} if family else {})
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
        shul_names = db.session.scalars(select(Institution.name).where(
            Institution.kind == 'Shul').distinct().order_by(Institution.name)).all()
        yeshivah_names = db.session.scalars(select(Institution.name).where(
            Institution.kind == 'Yeshivah').distinct().order_by(Institution.name)).all()
        if error and 'yeshivah_name' in request.form:
            names = request.form.getlist('yeshivah_name')
            grades = request.form.getlist('yeshivah_grade')
            years_in = request.form.getlist('yeshivah_year_from')
            years_out = request.form.getlist('yeshivah_year_to')
            yeshivah_history = [
                {'name': name, 'grade': grades[index] if index < len(grades) else '',
                 'year_from': years_in[index] if index < len(years_in) else '',
                 'year_to': years_out[index] if index < len(years_out) else ''}
                for index, name in enumerate(names)
            ] or [{'name': '', 'grade': '', 'year_from': '', 'year_to': ''}]
        elif family:
            affiliations = db.session.scalars(select(PersonAffiliation).join(Institution).where(
                PersonAffiliation.person_type == 'family',
                PersonAffiliation.person_id == family.id,
                Institution.kind == 'Yeshivah').order_by(PersonAffiliation.year_from,
                                                         PersonAffiliation.id)).all()
            yeshivah_history = [
                {'name': row.institution.name, 'grade': row.grade,
                 'year_from': row.year_from or '', 'year_to': row.year_to or ''}
                for row in affiliations
            ]
            if not yeshivah_history and family.yeshivah:
                yeshivah_history = [{'name': family.yeshivah, 'grade': '',
                                      'year_from': '', 'year_to': ''}]
        else:
            yeshivah_history = []
        return render_template('family_form.html', family=family, title=title,
            values=values, budget=budget, intake_error=error,
            shul_names=shul_names, yeshivah_names=yeshivah_names,
            yeshivah_history=yeshivah_history)

    def submitted_yeshivah_history():
        """Validate the applicant's repeatable, structured yeshivah history."""
        if 'yeshivah_name' not in request.form:
            return None
        columns = {key: request.form.getlist(key) for key in (
            'yeshivah_name', 'yeshivah_grade', 'yeshivah_year_from',
            'yeshivah_year_to')}
        histories = []
        for index, raw_name in enumerate(columns['yeshivah_name']):
            values = {key: (rows[index].strip() if index < len(rows) else '')
                      for key, rows in columns.items()}
            if not any(values.values()):
                continue
            if not all(values.values()):
                raise ValueError('For every yeshivah, enter the name, class entered, year in, and year out.')
            if len(values['yeshivah_name']) > 160 or len(values['yeshivah_grade']) > 80:
                raise ValueError('Yeshivah information is too long.')
            try:
                year_from = int(values['yeshivah_year_from'])
                year_to = int(values['yeshivah_year_to'])
            except ValueError:
                raise ValueError('Enter valid yeshivah years.')
            if not 1900 <= year_from <= 2100 or not 1900 <= year_to <= 2100:
                raise ValueError('Enter valid yeshivah years.')
            if year_from > year_to:
                raise ValueError('The year out must not be before the year in.')
            histories.append({'name': values['yeshivah_name'],
                              'grade': values['yeshivah_grade'],
                              'year_from': year_from, 'year_to': year_to})
        return histories

    def institution_field(key):
        selected = request.form.get(key, '').strip()
        if selected == '__new__':
            selected = request.form.get(key + '_new', '').strip()
        if len(selected) > 160:
            abort(400, 'Value is too long.')
        return selected

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
                yeshivah_history = submitted_yeshivah_history()
            except ValueError as exc:
                return intake_form(None, 'New family intake', str(exc)), 400
            limits = {'address':300, 'city':120, 'state':80, 'zip_code':20, 'phone':80, 'rabbi_phone':80, 'shul_gabbai_phone':80, 'inlaws_family':1000}
            family = Family(name=field('name', True), **{k: field(k, limit=limits.get(k, 160)) for k in ['spouse','phone','address','city','state','zip_code','father','inlaws','inlaws_maiden_name','inlaws_family','rabbi','rabbi_phone','weekday_shul','shabbos_shul','yeshivah','shul_gabbai','shul_gabbai_phone']}, circumstances=field('circumstances', limit=5000))
            for key in ('yeshivah', 'weekday_shul', 'shabbos_shul'):
                setattr(family, key, institution_field(key))
            if yeshivah_history is not None:
                family.yeshivah = yeshivah_history[0]['name'] if yeshivah_history else ''
            db.session.add(family)
            db.session.flush()
            connect_family_profile_directories(family, yeshivah_history)
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
                yeshivah_history = submitted_yeshivah_history()
            except ValueError as exc:
                return intake_form(family, 'Edit family profile', str(exc)), 400
            limits = {'circumstances':5000, 'inlaws_family':1000, 'address':300, 'city':120, 'state':80, 'zip_code':20, 'phone':80, 'rabbi_phone':80, 'shul_gabbai_phone':80}
            for key in ['name','spouse','phone','address','city','state','zip_code','father','inlaws','inlaws_maiden_name','inlaws_family','rabbi','rabbi_phone','weekday_shul','shabbos_shul','yeshivah','shul_gabbai','shul_gabbai_phone','circumstances']:
                setattr(family, key, field(key, required=key=='name', limit=limits.get(key, 160)))
            for key in ('yeshivah', 'weekday_shul', 'shabbos_shul'):
                setattr(family, key, institution_field(key))
            if yeshivah_history is not None:
                family.yeshivah = yeshivah_history[0]['name'] if yeshivah_history else ''
            connect_family_profile_directories(family, yeshivah_history)
            save_intake(family, intake_data)
            audit('Updated family profile', family.id)
            db.session.commit()
            flash('Profile updated.')
            return redirect(url_for('family_detail', family_id=family.id))
        return intake_form(family, 'Edit family profile')

    @app.get('/families/<int:family_id>')
    def family_detail(family_id):
        require_capability(('family_admin', 'office_employee'))
        if not can_access_family(family_id):
            abort(403, 'You are not assigned to this family.')
        family = db.session.scalar(select(Family).options(
            selectinload(Family.children), selectinload(Family.contacts).selectinload(Contact.nested_supporters),
            selectinload(Family.expenses), selectinload(Family.documents),
            selectinload(Family.gabbais), selectinload(Family.intake_record)
        ).where(Family.id == family_id))
        if family is None:
            abort(404)
        if current_user() and current_user().role == 'office_employee':
            return render_template('family_office_with_documents.html', title=family.name, family=family)
        activity = db.session.scalars(select(Audit).where(Audit.family_id==family.id).order_by(Audit.id.desc()).limit(30)).all()
        supporter_keys = {contact.supporter_key for contact in family.contacts if contact.supporter_key}
        connected_counts = dict(db.session.execute(select(
            Contact.supporter_key, func.count(func.distinct(Contact.family_id))
        ).where(Contact.supporter_key.in_(supporter_keys)).group_by(Contact.supporter_key)).all()) if supporter_keys else {}
        for contact in family.contacts:
            contact.connected_cases = connected_counts.get(contact.supporter_key, 1)
        # Keep each supporter's household together in the profile table.  A
        # supporter linked as a son or son-in-law belongs immediately beneath
        # the selected parent instead of appearing elsewhere in the flat list.
        top_level_contacts = [contact for contact in family.contacts if not contact.parent_contact_id]
        included_contact_ids = set()
        contact_rows = []
        def add_contact_branch(contact, depth=0):
            if contact.id in included_contact_ids:
                return
            included_contact_ids.add(contact.id)
            contact_rows.append((contact, depth))
            for nested in sorted(contact.nested_supporters, key=lambda row: row.name.lower()):
                add_contact_branch(nested, depth + 1)
        for contact in top_level_contacts:
            add_contact_branch(contact)
        # Preserve access to legacy/orphaned records whose parent is unavailable.
        contact_rows.extend((contact, False) for contact in family.contacts
                            if contact.parent_contact_id and contact.id not in included_contact_ids)
        return render_template('family.html', title=family.name, family=family, activity=activity,
                               contact_rows=contact_rows,
                               budget=budget_totals(family),
                               pledged=sum(c.monthly_equivalent_cents for c in family.contacts if c.status=='Pledged') if not app.extensions['workflows']['enforced']() else app.extensions['workflows']['monthly_pledged'](family.id))

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
                     if app.extensions['workflows']['document_allowed'](document) and matches(document.filename, document.content_type)]
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

    @app.post('/families/<int:family_id>/provider-accounts')
    def add_provider_account(family_id):
        require_capability(('family_admin', 'office_employee'))
        family = accessible_family_or_404(family_id)
        kind = field('kind', True)
        if kind not in ('utility', 'grocery', 'mosdos', 'other'):
            abort(400, 'Choose an account type.')
        treatment = field('budget_treatment')
        if treatment not in ('', 'additional', 'food', 'rent'):
            abort(400, 'Invalid account or assistance entry.')
        monthly_bill = amount('monthly_bill')
        record = db.session.get(HouseholdIntake, family_id)
        if record is None:
            record = HouseholdIntake(family_id=family_id, data={})
            db.session.add(record)
        data = dict(record.data or {})
        accounts = list(data.get('accounts') or [])
        accounts.append({
            'kind': kind,
            'provider': field('provider', True, 300),
            'account': field('account', limit=300),
            'phone': field('phone', limit=300),
            'child': field('child', limit=300),
            'monthly_bill': monthly_bill,
            'budget_treatment': treatment,
        })
        data['accounts'] = accounts
        record.data = data
        audit('Added provider account expense', family_id)
        db.session.commit()
        flash('Provider expense added.')
        return redirect(url_for('family_detail', family_id=family.id) + '#provider-expenses')

    @app.post('/families/<int:family_id>/status')
    def family_status(family_id):
        require_organization_admin()
        family = accessible_family_or_404(family_id)
        status = field('status', True)
        if app.extensions['workflows']['enforced']():
            return app.extensions['workflows']['legacy_status'](family_id, status)
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
        child = Child(family_id=family_id, name=field('name', True), age=age,
            grade=field('grade', limit=80), school=field('school'), tuition_contact=field('tuition_contact', limit=300),
            married=request.form.get('married') == 'yes', spouse_name=field('spouse_name'))
        db.session.add(child)
        db.session.flush()
        connect_child_profile_directory(child)
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
        connect_child_profile_directory(child)
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
                Contact.family_id == family_id))
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
            Contact.family_id == family_id, Contact.supporter_key == key)) if key.startswith('phone:') else None
        if duplicate_case:
            abort(400, 'This supporter is already connected to this case.')
        if existing and key.startswith('phone:'):
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
        if app.extensions['workflows']['enforced']():
            app.extensions['workflows']['contact_allowed'](contact, edit=True)
            flash('Record confirmed commitments through the pledge workflow.')
            return redirect(url_for('operations', family_id=contact.family_id, kind='pledge'))
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
        if app.extensions['workflows']['enforced']():
            app.extensions['workflows']['contact_allowed'](contact, edit=request.method=='POST')
            return redirect(url_for('supporter_network',family_id=contact.family_id,edit=contact.id))
        possible_parents = db.session.scalars(select(Contact).where(
            Contact.family_id == contact.family_id,
            Contact.id != contact.id
        ).order_by(Contact.name)).all()
        descendants, pending = set(), [contact.id]
        while pending:
            found = db.session.scalars(select(Contact.id).where(Contact.parent_contact_id.in_(pending))).all()
            pending = [row_id for row_id in found if row_id not in descendants]
            descendants.update(pending)
        possible_parents = [row for row in possible_parents if row.id not in descendants]
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
            new_key = supporter_key(name, phone, contact.supporter_key)
            linked = db.session.scalars(select(Contact).where(
                Contact.supporter_key == contact.supporter_key)).all() if contact.supporter_key else [contact]
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
        parent_connection = field('parent_connection') or 'Son'
        if parent_connection not in ('Son', 'Son-in-law'):
            abort(400, 'Choose whether this person is a son or son-in-law of the selected supporter.')
        spouse_connection = 'Son-in-law' if parent_connection == 'Son' else 'Son'
        db.session.add(Contact(
            family_id=contact.family_id, name=name, relationship='Nephew',
            phone=phone, supporter_key=supporter_key(name, phone),
            parent_contact_id=contact.id, parent_connection=parent_connection,
            monthly_cents=0, pledge_frequency='Monthly', status='To contact'))
        if spouse_name:
            db.session.add(Contact(
                family_id=contact.family_id, name=spouse_name, relationship='Nephew',
                phone='', supporter_key=supporter_key(spouse_name, ''),
                parent_contact_id=contact.id, parent_connection=spouse_connection,
                monthly_cents=0, pledge_frequency='Monthly', status='To contact'))
        audit(f'Added child as supporter under: {contact.name}', contact.family_id)
        db.session.commit()
        return redirect(url_for('fundraising_detail' if current_user() and current_user().role == 'fundraiser' else 'family_detail', family_id=contact.family_id))

    @app.post('/contacts/<int:contact_id>/delete')
    def delete_contact(contact_id):
        require_capability(('family_admin', 'fundraiser'))
        contact = db.session.scalar(scoped_contacts_statement().where(Contact.id == contact_id))
        if contact is None:
            abort(403, 'You are not assigned to this family.')
        work_model=app.extensions['workflows']['models']['WorkItem']
        if any(w.data.get('contact_id')==contact.id for w in db.session.scalars(select(work_model).where(work_model.family_id==contact.family_id))):
            abort(400,'This supporter has workflow history. Pause outreach instead of deleting the record.')
        link_model=app.extensions['workflows']['models']['SupporterLink']
        if db.session.get(link_model,contact.id) or db.session.scalar(select(link_model.contact_id).where(link_model.parent_id==contact.id)):
            abort(400,'This supporter has workflow history. Pause outreach instead of deleting the record.')
        if contact.receipts:
            abort(400, 'This supporter cannot be deleted because donation receipts are recorded.')
        family_id = contact.family_id
        name = contact.name
        child_ids = [child.id for child in contact.children]
        db.session.execute(db.delete(PersonAffiliation).where(
            ((PersonAffiliation.person_type == 'supporter') & (PersonAffiliation.person_id == contact.id)) |
            ((PersonAffiliation.person_type.in_(('supporter_child', 'supporter_child_spouse'))) &
             (PersonAffiliation.person_id.in_(child_ids)))))
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
        if not app.config['DEMO']:
            app.extensions['workflows']['document_access'](document)
            app.extensions['workflows']['emit'](None, 'Document downloaded', {'document_id': document.id})
            db.session.commit()
        return send_file(BytesIO(document.data), mimetype=document.content_type,
                         as_attachment=True, download_name=document.filename,
                         max_age=0)

    @app.post('/documents/<int:document_id>/delete')
    def delete_document(document_id):
        require_capability(('family_admin', 'office_employee'))
        document = accessible_document_or_403(document_id)
        if app.extensions['workflows']['enforced']():
            app.extensions['workflows']['protect_document_delete'](document)
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
        statement = select(Family).options(
            selectinload(Family.children), selectinload(Family.intake_record)
        ).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(statement).all()
        # Each case still shows the supporter commitment attributed to it. The
        # organization dashboard/billing rollup de-duplicates the shared person.
        family_ids = [family.id for family in families]
        budget_records = {record.family_id: record for record in db.session.scalars(
            select(HouseholdBudget).where(HouseholdBudget.family_id.in_(family_ids))).all()
        } if family_ids else {}
        monthly_pledge = case(
            (Contact.pledge_frequency == 'Weekly', Contact.monthly_cents * 52 / 12),
            (Contact.pledge_frequency == 'One time', 0),
            else_=Contact.monthly_cents,
        )
        pledged = {family_id: total for family_id, total in db.session.execute(select(
            Contact.family_id, func.round(func.coalesce(func.sum(monthly_pledge), 0))
        ).where(Contact.family_id.in_(family_ids), Contact.status == 'Pledged').group_by(Contact.family_id)).all()}
        if app.extensions['workflows']['enforced']():
            pledged = {f.id: app.extensions['workflows']['monthly_pledged'](f.id,current_user()) for f in families}
        received = {family_id: total for family_id, total in db.session.execute(select(
            Receipt.family_id, func.coalesce(func.sum(Receipt.amount_cents), 0)
        ).where(Receipt.family_id.in_(family_ids)).group_by(Receipt.family_id)).all()}
        pledged = {family_id: pledged.get(family_id, 0) for family_id in family_ids}
        received = {family_id: received.get(family_id, 0) for family_id in family_ids}
        # Fundraisers receive no target/shortfall: even an aggregate may disclose
        # confidential household budget information. Authorized family/admin users
        # may use the saved shortfall as an internal planning target.
        show_targets = not (current_user() and current_user().role == 'fundraiser')
        targets = ({family.id: budget_totals(family, budget_records.get(family.id))['shortfall'] for family in families}
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
        if app.extensions['workflows']['enforced']() and current_user().role == 'fundraiser':
            link = app.extensions['workflows']['models']['SupporterLink']
            ids = set(db.session.scalars(select(link.contact_id).where(link.assigned_to == current_user().id)))
            contacts = [c for c in contacts if c.id in ids]
        pledged = sum(contact.monthly_cents for contact in contacts if contact.status == 'Pledged') if not app.extensions['workflows']['enforced']() else app.extensions['workflows']['monthly_pledged'](family_id,current_user())
        for contact in contacts:
            contact.connected_cases = linked_contact_count(contact)
        return render_template('fundraising_detail.html', title='Fundraising workspace', family=family,
                               contacts=contacts, pledged=pledged, approved_story=(app.extensions['workflows']['approved']('fundraising_plan',family_id).data.get('disclosure','') if app.extensions['workflows']['approved']('fundraising_plan',family_id) else ''))

    def contact_visible(contact):
        if not app.extensions['workflows']['enforced']() or not current_user() or current_user().role!='fundraiser':return True
        link=db.session.get(app.extensions['workflows']['models']['SupporterLink'],contact.id)
        return bool(can_access_family(contact.family_id) and link and link.assigned_to==current_user().id)

    def scoped_contacts_statement():
        statement = select(Contact).options(
            selectinload(Contact.family), selectinload(Contact.parent_supporter)
        ).order_by(Contact.id.desc())
        if not organization_admin():
            statement = statement.where(Contact.family_id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        if app.extensions['workflows']['enforced']() and current_user().role == 'fundraiser':
            link = app.extensions['workflows']['models']['SupporterLink']
            statement = statement.where(Contact.id.in_(select(link.contact_id).where(link.assigned_to == current_user().id)))
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
            Receipt.contact_id.in_([c.id for c in contacts]),
            Receipt.received_on >= month_start, Receipt.received_on < month_end
        ).order_by(Receipt.received_on.desc(), Receipt.id.desc())).all() if family_ids else []
        received_by_contact = {}
        for receipt in receipts:
            received_by_contact[receipt.contact_id] = received_by_contact.get(receipt.contact_id, 0) + receipt.amount_cents
        contact_ids = [contact.id for contact in contacts]
        lifetime_by_contact = {contact_id: total for contact_id, total in db.session.execute(select(
            Receipt.contact_id, func.coalesce(func.sum(Receipt.amount_cents), 0)
        ).where(Receipt.contact_id.in_(contact_ids)).group_by(Receipt.contact_id)).all()} if contact_ids else {}
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
        relationship_group = request.args.get('relationship_group', '').strip()
        relationship = request.args.get('relationship', '').strip()
        supporter_status = request.args.get('status', '').strip()
        pledge_frequency = request.args.get('pledge_frequency', '').strip()
        relationship_filters = {
            'siblings': ('Sibling',),
            'nephews': ('Nephew','Child of sibling'),
        }
        if relationship_group and relationship_group not in relationship_filters:
            abort(400, 'Choose a valid supporter list.')
        if relationship and relationship not in RELATIONSHIPS + list(LEGACY_RELATIONSHIPS):
            abort(400, 'Choose a valid relationship.')
        if supporter_status and supporter_status not in CONTACT_STATUSES:
            abort(400, 'Choose a valid follow-up status.')
        if pledge_frequency and pledge_frequency not in PLEDGE_FREQUENCIES:
            abort(400, 'Choose a valid donation frequency.')
        statement = scoped_contacts_statement()
        if family_id:
            if not can_access_family(family_id):
                abort(403, 'You are not assigned to this family.')
            statement = statement.where(Contact.family_id == family_id)
        if query:
            statement = statement.where(or_(
                Contact.name.icontains(query, autoescape=True),
                Contact.phone.icontains(query, autoescape=True)))
        if relationship:
            statement = statement.where(Contact.relationship == relationship)
        elif relationship_group:
            statement = statement.where(
                Contact.relationship.in_(relationship_filters[relationship_group]))
        if supporter_status:
            statement = statement.where(Contact.status == supporter_status)
        if pledge_frequency:
            statement = statement.where(Contact.pledge_frequency == pledge_frequency)
        contacts = db.session.scalars(statement).all()
        # Never show a matching son or son-in-law as an orphaned top-level row.
        # Include his parent as context, then keep nested supporters immediately
        # beneath their parent in the organization-wide directory too.
        contact_ids = {contact.id for contact in contacts}
        missing_parent_ids = {
            contact.parent_contact_id for contact in contacts
            if contact.parent_contact_id and contact.parent_contact_id not in contact_ids
        } if not relationship_group else set()
        if missing_parent_ids:
            parents = db.session.scalars(scoped_contacts_statement().where(
                Contact.id.in_(missing_parent_ids))).all()
            contacts.extend(parent for parent in parents if not family_id or parent.family_id == family_id)
        children_by_parent = {}
        roots = []
        available_ids = {contact.id for contact in contacts}
        for contact in contacts:
            if contact.parent_contact_id and contact.parent_contact_id in available_ids:
                children_by_parent.setdefault(contact.parent_contact_id, []).append(contact)
            else:
                roots.append(contact)
        contacts = []
        included_ids = set()
        def add_branch(parent):
            if parent.id in included_ids:
                return
            included_ids.add(parent.id)
            contacts.append(parent)
            for child in sorted(children_by_parent.get(parent.id, []), key=lambda row: row.name.lower()):
                add_branch(child)
        for parent in sorted(roots, key=lambda row: (row.family.name.lower(), row.name.lower())):
            add_branch(parent)
        family_statement = select(Family).order_by(Family.name)
        if not organization_admin():
            family_statement = family_statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(family_statement).all()
        family_ids = [family.id for family in families]
        possible_parents = db.session.scalars(scoped_contacts_statement().where(
            Contact.family_id.in_(family_ids)
        ).order_by(Contact.family_id, Contact.name)).all() if family_ids else []
        contact_ids = [contact.id for contact in contacts]
        totals = {contact_id: total for contact_id, total in db.session.execute(select(
            Receipt.contact_id, func.coalesce(func.sum(Receipt.amount_cents), 0)
        ).where(Receipt.contact_id.in_(contact_ids)).group_by(Receipt.contact_id)).all()} if contact_ids else {}
        return render_template('supporters.html', title='Supporters', contacts=contacts,
                               received=totals, query=query, families=families,
                               selected_family_id=family_id, possible_parents=possible_parents,
                               relationship_group=relationship_group,
                               selected_relationship=relationship,
                               selected_status=supporter_status,
                               selected_pledge_frequency=pledge_frequency)

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
        hierarchy_groups = []
        seen_hierarchy_roots = set()
        for linked_contact in linked_contacts:
            root = linked_contact.parent_supporter if linked_contact.parent_supporter and contact_visible(linked_contact.parent_supporter) else linked_contact
            if root.id in seen_hierarchy_roots:
                continue
            seen_hierarchy_roots.add(root.id)
            hierarchy_groups.append({
                'family': root.family,
                'root': root,
                'children': sorted(
                    [c for c in root.nested_supporters if contact_visible(c)],
                    key=lambda row: row.name.casefold()),
            })
        contact_ids = [row.id for row in linked_contacts]
        receipts = db.session.scalars(select(Receipt).where(
            Receipt.contact_id.in_(contact_ids)
        ).order_by(Receipt.received_on.desc(), Receipt.id.desc())).all() if contact_ids else []
        payments = db.session.scalars(select(StripePayment).where(
            StripePayment.contact_id.in_(contact_ids)
        ).order_by(StripePayment.created_at.desc())).all() if contact_ids else []
        return render_template('supporter_detail.html', title='Supporter history',
                               supporter=contact, linked_contacts=linked_contacts,
                               hierarchy_groups=hierarchy_groups,
                               receipts=receipts, payments=payments,
                               total_received=sum(receipt.amount_cents for receipt in receipts))

    @app.get('/approvals')
    def approvals():
        require_organization_admin()
        expenses = db.session.scalars(select(Expense).where(Expense.status == 'Requested').order_by(Expense.id.desc())).all()
        return render_template('approvals.html', title='Approvals', expenses=expenses)

    @app.get('/reports')
    def reports():
        require_organization_admin()
        families = db.session.scalars(select(Family).options(
            selectinload(Family.children), selectinload(Family.contacts),
            selectinload(Family.intake_record)
        ).order_by(Family.name)).all()
        family_ids = [family.id for family in families]
        budget_records = {record.family_id: record for record in db.session.scalars(
            select(HouseholdBudget).where(HouseholdBudget.family_id.in_(family_ids))).all()
        } if family_ids else {}
        received_totals = dict(db.session.execute(select(
            Receipt.family_id, func.coalesce(func.sum(Receipt.amount_cents), 0)
        ).where(Receipt.family_id.in_(family_ids)).group_by(Receipt.family_id)).all()) if family_ids else {}
        expense_totals = {(family_id, status, is_org): total
            for family_id, status, is_org, total in db.session.execute(select(
                Expense.family_id, Expense.status,
                case((Expense.category == 'Organization expense', True), else_=False).label('is_org'),
                func.coalesce(func.sum(Expense.amount_cents), 0),
            ).where(Expense.family_id.in_(family_ids)).group_by(
                Expense.family_id, Expense.status,
                case((Expense.category == 'Organization expense', True), else_=False)
            )).all()} if family_ids else {}
        rows = []
        for family in families:
            totals = budget_totals(family, budget_records.get(family.id))
            pledged = sum(c.monthly_equivalent_cents for c in family.contacts if c.status == 'Pledged')
            received = received_totals.get(family.id, 0)
            approved = expense_totals.get((family.id, 'Approved', False), 0)
            paid = expense_totals.get((family.id, 'Paid', False), 0)
            org_costs = expense_totals.get((family.id, 'Paid', True), 0)
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

    @app.get('/community-directories')
    def community_directories():
        require_organization_admin()
        kind = request.args.get('kind', 'Shul')
        if kind not in ('Shul', 'Yeshivah'):
            abort(400, 'Choose a valid directory.')
        query = request.args.get('q', '').strip()[:160]
        family_id = request.args.get('family_id', type=int)
        families = db.session.scalars(select(Family).order_by(Family.name)).all()
        if family_id and not any(family.id == family_id for family in families):
            abort(404)
        statement = select(Institution).where(Institution.kind == kind).order_by(Institution.name)
        if query:
            statement = statement.where(Institution.name.icontains(query, autoescape=True))
        people = directory_people()
        hierarchy = directory_person_hierarchy()
        phone_by_key = {}
        for family in families:
            phone_by_key[('family', family.id)] = family.phone
            phone_by_key[('spouse', family.id)] = family.phone
        for supporter in db.session.scalars(select(Contact)).all():
            phone_by_key[('supporter', supporter.id)] = supporter.phone
        for child in db.session.scalars(select(ContactChild)).all():
            phone_by_key[('supporter_child', child.id)] = child.phone
            phone_by_key[('supporter_child_spouse', child.id)] = child.phone
        for user in db.session.scalars(select(StaffUser)).all():
            phone_by_key[('staff', user.id)] = user.phone
        people_by_key = {(person_type, person_id): {
            'name': name, 'role': role, 'context': context,
            'phone': phone_by_key.get((person_type, person_id), ''),
            **hierarchy.get((person_type, person_id), {
                'depth': 0, 'parent_name': '',
                'sort_key': (context.lower(), name.lower()),
            }),
        } for person_type, person_id, name, role, context in people}
        institutions = db.session.scalars(statement).all()
        allowed_people = None
        if family_id:
            child_ids = set(db.session.scalars(select(Child.id).where(
                Child.family_id == family_id)).all())
            supporter_ids = set(db.session.scalars(select(Contact.id).where(
                Contact.family_id == family_id)).all())
            supporter_child_ids = set(db.session.scalars(select(ContactChild.id).where(
                ContactChild.contact_id.in_(supporter_ids))).all()) if supporter_ids else set()
            allowed_people = {('family', family_id), ('spouse', family_id)}
            allowed_people.update((person_type, child_id) for child_id in child_ids
                                  for person_type in ('child', 'child_spouse'))
            allowed_people.update(('supporter', supporter_id) for supporter_id in supporter_ids)
            allowed_people.update((person_type, child_id) for child_id in supporter_child_ids
                                  for person_type in ('supporter_child', 'supporter_child_spouse'))
        visible_institutions = []
        for institution in institutions:
            rows = [row for row in institution.affiliations
                    if allowed_people is None or (row.person_type, row.person_id) in allowed_people]
            if family_id and not rows:
                continue
            rows = sorted(rows, key=lambda row: (
                people_by_key.get((row.person_type, row.person_id), {}).get(
                    'sort_key', ('zz', row.id))))
            if kind == 'Yeshivah':
                applicant_rows = {
                    row.person_id: row for row in rows
                    if row.person_type == 'family' and row.year_from is not None
                    and row.year_to is not None
                }
                for row in rows:
                    row.applicant_overlap = None
                    if row.person_type != 'supporter':
                        continue
                    supporter = db.session.get(Contact, row.person_id)
                    applicant = applicant_rows.get(supporter.family_id) if supporter else None
                    if applicant is None or row.year_from is None or row.year_to is None:
                        row.applicant_overlap = {'status': 'missing'}
                        continue
                    overlap_from = max(row.year_from, applicant.year_from)
                    overlap_to = min(row.year_to, applicant.year_to)
                    row.applicant_overlap = ({
                        'status': 'overlap', 'year_from': overlap_from,
                        'year_to': overlap_to,
                    } if overlap_from <= overlap_to else {'status': 'none'})
                grades = {}
                for row in rows:
                    grades.setdefault(row.grade, []).append(row)
                institution.directory_groups = sorted(
                    grades.items(), key=lambda item: item[0].lower())
            else:
                institution.directory_groups = [('', rows)]
            institution.directory_count = len(rows)
            visible_institutions.append(institution)
        return render_template('directories.html', title=f'{kind} list', kind=kind,
                               institutions=visible_institutions, families=families,
                               selected_family_id=family_id, people=people,
                               people_by_key=people_by_key, query=query)

    @app.post('/community-directories/institutions')
    def add_institution():
        require_organization_admin()
        kind = field('kind', True, 20)
        if kind not in ('Shul', 'Yeshivah'):
            abort(400, 'Choose a valid directory.')
        name = field('name', True)
        city = field('city', limit=120)
        duplicate = db.session.scalar(select(Institution.id).where(
            Institution.kind == kind, func.lower(Institution.name) == name.lower()))
        if duplicate:
            abort(400, 'This institution is already in the list.')
        db.session.add(Institution(kind=kind, name=name, city=city,
            address=field('address', limit=240), state=field('state', limit=80),
            phone=field('phone', limit=80)))
        audit(f'Added {kind.lower()}: {name}')
        db.session.commit()
        flash('Institution added.')
        return redirect(url_for('community_directories', kind=kind))

    @app.post('/community-directories/affiliations')
    def add_person_affiliation():
        require_organization_admin()
        institution = db.get_or_404(Institution, request.form.get('institution_id', type=int))
        person_value = field('person', True, 60)
        try:
            person_type, person_id_text = person_value.split(':', 1)
            person_id = int(person_id_text)
        except (ValueError, TypeError):
            abort(400, 'Choose a valid person.')
        if person_type not in ('family', 'spouse', 'child', 'child_spouse', 'supporter',
                               'supporter_child', 'supporter_child_spouse', 'staff') or not valid_directory_person(person_type, person_id):
            abort(400, 'Choose a valid person.')
        grade = field('grade', required=institution.kind == 'Yeshivah', limit=80)
        def entered_year(name, required=False):
            value = request.form.get(name, '').strip()
            if not value:
                if required:
                    abort(400, 'Enter both the year in and year out.')
                return None
            try:
                year = int(value)
            except ValueError:
                abort(400, 'Enter a valid year.')
            if year < 1900 or year > 2100:
                abort(400, 'Enter a valid year.')
            return year
        years_required = institution.kind == 'Yeshivah'
        year_from = entered_year('year_from', years_required)
        year_to = entered_year('year_to', years_required)
        if year_from and year_to and year_from > year_to:
            abort(400, 'The ending year must not be before the starting year.')
        duplicate = db.session.scalar(select(PersonAffiliation.id).where(
            PersonAffiliation.institution_id == institution.id,
            PersonAffiliation.person_type == person_type,
            PersonAffiliation.person_id == person_id,
            PersonAffiliation.grade == grade,
            PersonAffiliation.year_from == year_from,
            PersonAffiliation.year_to == year_to))
        if duplicate:
            abort(400, 'This connection is already recorded.')
        note = field('note', limit=300)
        profile_placeholder = None
        if institution.kind == 'Yeshivah':
            profile_placeholder = db.session.scalar(select(PersonAffiliation).where(
                PersonAffiliation.institution_id == institution.id,
                PersonAffiliation.person_type == person_type,
                PersonAffiliation.person_id == person_id,
                PersonAffiliation.grade == '',
                PersonAffiliation.year_from.is_(None),
                PersonAffiliation.year_to.is_(None),
                PersonAffiliation.note.contains('Family profile')))
        if profile_placeholder:
            profile_placeholder.grade = grade
            profile_placeholder.year_from = year_from
            profile_placeholder.year_to = year_to
            profile_placeholder.note = note or 'Applicant profile · Family profile'
        else:
            db.session.add(PersonAffiliation(institution_id=institution.id,
                person_type=person_type, person_id=person_id, grade=grade,
                year_from=year_from, year_to=year_to, note=note))
        audit(f'Connected person to {institution.kind.lower()}: {institution.name}')
        db.session.commit()
        flash('Person connected.')
        return redirect(url_for('community_directories', kind=institution.kind))

    @app.post('/community-directories/affiliations/<int:affiliation_id>/delete')
    def delete_person_affiliation(affiliation_id):
        require_organization_admin()
        affiliation = db.get_or_404(PersonAffiliation, affiliation_id)
        kind = affiliation.institution.kind
        db.session.delete(affiliation)
        db.session.commit()
        flash('Connection removed.')
        return redirect(url_for('community_directories', kind=kind))

    @app.post('/community-directories/institutions/<int:institution_id>/delete')
    def delete_institution(institution_id):
        require_organization_admin()
        institution = db.get_or_404(Institution, institution_id)
        if institution.affiliations:
            abort(400, 'Remove the connected people before deleting this institution.')
        kind = institution.kind
        db.session.delete(institution)
        db.session.commit()
        flash('Institution deleted.')
        return redirect(url_for('community_directories', kind=kind))

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

    @app.get('/payouts')
    def payouts():
        require_organization_admin()
        recipients = db.session.scalars(select(StripeRecipient).order_by(
            StripeRecipient.created_at.desc())).all()
        transfers = db.session.scalars(select(StripeTransfer).order_by(
            StripeTransfer.created_at.desc()).limit(250)).all()
        families = db.session.scalars(select(Family).order_by(Family.name)).all()
        approved_expenses = db.session.scalars(select(Expense).where(
            Expense.status == 'Approved').order_by(Expense.id.desc())).all()
        return render_template('payouts.html', title='Stripe payouts', recipients=recipients,
                               transfers=transfers, families=families,
                               approved_expenses=approved_expenses)

    @app.post('/payouts/recipients')
    def create_payout_recipient():
        require_organization_admin()
        if not app.config['STRIPE_SECRET_KEY']:
            abort(503, 'Stripe payments are not configured.')
        kind = field('kind', True, 20)
        if kind not in ('family', 'vendor'):
            abort(400, 'Choose family or vendor.')
        family = None
        if kind == 'family':
            family = db.session.get(Family, request.form.get('family_id', type=int))
            if family is None:
                abort(400, 'Choose a valid family.')
            recipient_name, recipient_key = family.name, str(family.id)
        else:
            recipient_name = field('name', True)
            recipient_key = recipient_name.casefold()
        recipient_email = email_field()
        existing = db.session.scalar(select(StripeRecipient).where(
            StripeRecipient.kind == kind, StripeRecipient.recipient_key == recipient_key))
        if existing:
            abort(400, 'This payout recipient already exists.')
        try:
            account = create_connected_account(app.config['STRIPE_SECRET_KEY'], {
                'type': 'express', 'country': app.config['STRIPE_CONNECT_COUNTRY'],
                'email': recipient_email, 'capabilities': {'transfers': {'requested': True}},
                'metadata': {'yazory_kind': kind, 'yazory_recipient_key': recipient_key}},
                f'yazory-recipient-{kind}-{recipient_key}')
        except Exception:
            abort(502, 'Stripe could not create the recipient account. Confirm that Connect is enabled and try again.')
        recipient = StripeRecipient(kind=kind, recipient_key=recipient_key,
            family_id=family.id if family else None, name=recipient_name, email=recipient_email,
            stripe_account_id=stripe_value(account, 'id', ''))
        db.session.add(recipient)
        audit(f'Created Stripe payout recipient: {recipient_name}', family.id if family else None)
        db.session.commit()
        flash('Recipient created. Continue to secure Stripe verification.')
        return redirect(url_for('payout_recipient_onboarding', recipient_id=recipient.id))

    @app.get('/payouts/recipients/<int:recipient_id>/onboarding')
    def payout_recipient_onboarding(recipient_id):
        require_organization_admin()
        recipient = db.get_or_404(StripeRecipient, recipient_id)
        try:
            link = create_account_link(app.config['STRIPE_SECRET_KEY'], {
                'account': recipient.stripe_account_id,
                'refresh_url': absolute_url('payout_recipient_onboarding', recipient_id=recipient.id),
                'return_url': absolute_url('payout_recipient_return', recipient_id=recipient.id),
                'type': 'account_onboarding'})
        except Exception:
            abort(502, 'Stripe could not open recipient verification. Try again shortly.')
        return redirect(stripe_value(link, 'url', ''), code=303)

    @app.get('/payouts/recipients/<int:recipient_id>/return')
    def payout_recipient_return(recipient_id):
        require_organization_admin()
        recipient = db.get_or_404(StripeRecipient, recipient_id)
        try:
            account = retrieve_connected_account(app.config['STRIPE_SECRET_KEY'],
                                                 recipient.stripe_account_id)
        except Exception:
            abort(502, 'Stripe could not refresh the verification status.')
        recipient.details_submitted = bool(stripe_value(account, 'details_submitted', False))
        recipient.payouts_enabled = bool(stripe_value(account, 'payouts_enabled', False))
        recipient.status = 'ready' if recipient.payouts_enabled else ('restricted' if recipient.details_submitted else 'onboarding')
        recipient.updated_at = utcnow()
        db.session.commit()
        flash('Stripe verification status refreshed.')
        return redirect(url_for('payouts'))

    @app.post('/expenses/<int:expense_id>/stripe-transfer')
    def stripe_expense_transfer(expense_id):
        require_organization_admin()
        if not app.config['STRIPE_SECRET_KEY']:
            abort(503, 'Stripe payments are not configured.')
        expense = db.get_or_404(Expense, expense_id)
        if expense.status != 'Approved':
            abort(400, 'Only an approved expense can be sent through Stripe.')
        if db.session.scalar(select(StripeTransfer.id).where(StripeTransfer.expense_id == expense.id)):
            abort(400, 'This expense was already sent through Stripe.')
        recipient = db.session.get(StripeRecipient, request.form.get('recipient_id', type=int))
        if recipient is None or not recipient.payouts_enabled:
            abort(400, 'Choose a Stripe-verified recipient with payouts enabled.')
        work = app.extensions['workflows']['prepare_stripe_release'](expense, recipient, app.config['STRIPE_CURRENCY']) if app.extensions['workflows']['enforced']() else None
        try:
            transfer = create_transfer(app.config['STRIPE_SECRET_KEY'], {
                'amount': expense.amount_cents, 'currency': app.config['STRIPE_CURRENCY'],
                'destination': recipient.stripe_account_id,
                'transfer_group': f'YAZORY_EXPENSE_{expense.id}',
                'metadata': {'yazory_expense_id': str(expense.id),
                             'yazory_family_id': str(expense.family_id)}},
                f'yazory-expense-{expense.id}')
        except Exception:
            abort(502, 'Stripe could not send this transfer. No Yazory payment record was changed.')
        transfer_id = stripe_value(transfer, 'id', '')
        db.session.add(StripeTransfer(expense_id=expense.id, recipient_id=recipient.id,
            stripe_transfer_id=transfer_id, amount_cents=expense.amount_cents,
            currency=app.config['STRIPE_CURRENCY']))
        if work:
            app.extensions['workflows']['finish_stripe_release'](work, transfer_id, recipient)
        expense.status = 'Paid'
        expense.payment_reference = transfer_id
        audit(f'Sent expense #{expense.id} through Stripe to {recipient.name}', expense.family_id)
        db.session.commit()
        flash('Funds were transferred to the recipient’s Stripe balance for payout.')
        return redirect(url_for('payouts'))

    @app.post('/expenses/<int:expense_id>/status')
    def expense_status(expense_id):
        require_organization_admin()
        expense = db.get_or_404(Expense, expense_id)
        if app.extensions['workflows']['enforced']():
            return app.extensions['workflows']['legacy_expense'](expense_id)
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
            user = StaffUser(email=email, name=name, phone=field('phone', limit=80),
                address=field('address', limit=240), city=field('city', limit=120),
                state=field('state', limit=80), zip_code=field('zip_code', limit=20),
                job_title=field('job_title', limit=120),
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
            if not app.config['DEMO']:app.extensions['workflows']['create_onboarding'](user)
            db.session.commit()
            flash('Invitation created, but email delivery failed. Check Email history.' if
                  user.status == 'pending' and message.status == 'failed' else
                  'Invitation created and email queued.')
            return redirect(url_for('staff'))
        owner = db.session.scalar(select(StaffUser).where(StaffUser.email == app.config['ADMIN_EMAIL'].strip().lower()))
        return render_template('staff.html', title='Staff & assignments', users=db.session.scalars(select(StaffUser).order_by(StaffUser.email)).all(), families=db.session.scalars(select(Family).order_by(Family.name)).all(), owner_user_id=owner.id if owner else None)

    @app.post('/staff/<int:user_id>/details')
    def staff_details(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        email = email_field()
        owner_email = app.config['ADMIN_EMAIL'].strip().lower()
        if user.email == owner_email and email != owner_email:
            abort(400, 'The owner email address cannot be changed here.')
        duplicate = db.session.scalar(select(StaffUser.id).where(
            StaffUser.email == email, StaffUser.id != user.id))
        if duplicate:
            abort(400, 'A staff account already uses this email.')
        old_email = user.email
        user.name = field('name')
        user.email = email
        user.phone = field('phone', limit=80)
        user.address = field('address', limit=240)
        user.city = field('city', limit=120)
        user.state = field('state', limit=80)
        user.zip_code = field('zip_code', limit=20)
        user.job_title = field('job_title', limit=120)
        audit(f'Updated staff details: {old_email}')
        db.session.commit()
        flash('Staff details updated.')
        return redirect(url_for('staff'))

    @app.post('/staff/<int:user_id>/delete')
    def delete_staff(user_id):
        require_organization_admin()
        user = db.get_or_404(StaffUser, user_id)
        if user.id == current_user().id or user.email == app.config['ADMIN_EMAIL'].strip().lower():
            abort(400, 'The owner account cannot be deleted.')
        if user.role == 'organization_admin':
            admin_count = db.session.scalar(select(func.count()).select_from(StaffUser).where(
                StaffUser.role == 'organization_admin'))
            if admin_count <= 1:
                abort(400, 'At least one organization administrator is required.')
        if app.extensions['workflows']['enforced']():
            abort(400,'Use the staff departure workflow to preserve access history.')
        models=app.extensions['workflows']['models']
        event=models['WorkflowEvent'];work=models['WorkItem']
        if db.session.scalar(select(event.id).where(event.actor_id==user.id)) or db.session.scalar(select(work.id).where((work.owner_id==user.id)|(work.created_by==user.id))):
            abort(400,'Use the staff departure workflow to preserve access history.')
        email = user.email
        db.session.execute(db.update(AccountToken).where(AccountToken.created_by == user.id).values(created_by=None))
        db.session.execute(db.delete(AccountToken).where(AccountToken.staff_user_id == user.id))
        db.session.execute(db.update(EmailMessage).where(EmailMessage.staff_user_id == user.id).values(staff_user_id=None))
        db.session.execute(db.update(Receipt).where(Receipt.recorded_by == user.id).values(recorded_by=None))
        db.session.execute(db.delete(FamilyAssignment).where(FamilyAssignment.staff_user_id == user.id))
        db.session.execute(db.delete(PersonAffiliation).where(
            PersonAffiliation.person_type == 'staff', PersonAffiliation.person_id == user.id))
        db.session.delete(user)
        audit(f'Deleted staff user: {email}')
        db.session.commit()
        flash('Staff account deleted.')
        return redirect(url_for('staff'))

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
        if not app.config['DEMO']:
            result=app.extensions['workflows']['queue_access_change'](user,role)
            if result:return result
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

    from abcharity import register_abcharity
    register_abcharity(app, db, CharityCampaign, CharityDonor, CharityDonation,
                      Family, Contact, Expense, require_capability,
                      require_organization_admin, accessible_family_or_404, audit)
    from donation_workflows import install_donation_workflows
    install_donation_workflows(app, db, CharityCampaign, CharityDonation, CharityDonor,
        dict(current_user=current_user, can_access_family=can_access_family))

    from receipt_workflows import install_receipt_workflows
    install_receipt_workflows(app, db, Receipt, dict(current_user=current_user, can_access_family=can_access_family))

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(409)
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

if 'Shul friend' not in RELATIONSHIPS:
    RELATIONSHIPS.insert(RELATIONSHIPS.index('Friend'), 'Shul friend')

if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
