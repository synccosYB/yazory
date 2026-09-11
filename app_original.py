Warning: truncated output (original token count: 53962)
Total output lines: 3736

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
from abcharity import decrypt_api_key, encrypt_api_key
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

    @property
    def reported_children_count(self):
        """The intake total; child detail rows may contain only married children."""
        if not self.intake_record:
            return None
        return (self.intake_record.data or {}).get('children_count')

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
    email = db.Column(db.String(254), default='')
    home_phone = db.Column(db.String(80), default='')
    cell_phone = db.Column(db.String(80), default='')
    home_address = db.Column(db.String(240), default='')
    city = db.Column(db.String(120), default='')
    state = db.Column(db.String(80), default='')
    zip_code = db.Column(db.String(20), default='')
    workplace = db.Column(db.String(160), default='')
    work_phone = db.Column(db.String(80), default='')
    notes = db.Column(db.Text, default='')
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
    family = db.relationship('Family')


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


class CheckBankAccount(db.Model):
    """An encrypted check-writing account with its own number sequence."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    bank_name = db.Column(db.String(160), nullable=False)
    routing_number_encrypted = db.Column(db.Text, nullable=False)
    account_number_encrypted = db.Column(db.Text, nullable=False)
    account_last4 = db.Column(db.String(4), nullable=False, default='')
    next_check_number = db.Column(db.String(12), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ApplicantPayout(db.Model):
    """A direct family payout and, for checks, its complete lifecycle."""
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)
    method = db.Column(db.String(20), nullable=False, default='check', index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    payee_name = db.Column(db.String(160), nullable=False)
    mailing_address = db.Column(db.Text, nullable=False, default='')
    memo = db.Column(db.String(160), nullable=False, default='')
    check_number = db.Column(db.String(40), nullable=False, default='', index=True)
    check_date = db.Column(db.Date, nullable=True)
    stripe_reference = db.Column(db.String(255), nullable=False, default='', index=True)
    routing_number_encrypted = db.Column(db.Text, nullable=False, default='')
    account_number_encrypted = db.Column(db.Text, nullable=False, default='')
    check_bank_account_id = db.Column(db.Integer, db.ForeignKey('check_bank_account.id'), nullable=True, index=True)
    check_bank_account_name = db.Column(db.String(160), nullable=False, default='')
    check_bank_name = db.Column(db.String(160), nullable=False, default='')
    prior_case_check_count = db.Column(db.Integer, nullable=False, default=0)
    recipient_message = db.Column(db.String(500), nullable=False, default='')
    status = db.Column(db.String(30), nullable=False, default='created', index=True)
    mailed_at = db.Column(db.DateTime, nullable=True)
    cleared_at = db.Column(db.DateTime, nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True)
    family = db.relationship('Family', backref=db.backref('applicant_payouts', lazy=True))
    creator = db.relationship('StaffUser')
    check_bank_account = db.relationship('CheckBankAccount')

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
    # Retained for campaigns connected before profile-managed encrypted keys.
    key_env = db.Column(db.String(100), nullable=False, unique=True)
    api_key_encrypted = db.Column(db.Text, nullable=False, default='')
    public_url = db.Column(db.String(1000), nullable=False, default='')
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
    # Tests must stay isolated from Replit's production environment variables.
    # Otherwise production cookies are unusable in Flask's local test client
    # and demo fixtures are not created in the requested in-memory database.
    if app.config.get('TESTING'):
        app.config['SESSION_COOKIE_SECURE'] = False
        if not test_config or 'DEMO' not in test_config:
            app.config['DEMO'] = True
        if not test_config or 'APP_BASE_URL' not in test_config:
            app.config['APP_BASE_URL'] = 'http://localhost'
    if app.config['DEMO'] and not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        raise RuntimeError('Demo mode must use a local SQLite database, never a shared production database.')
    db.init_app(app)
    app.jinja_env.globals['_'] = translate
    app.jinja_env.globals['_audit'] = translate_audit

    @app.template_filter('money')
    def money(cents):
        return f'${(cents or 0)/100:,.2f}'

    @app.template_filter('currency_money')
    def currency_money(cents, currency='USD'):
        """Use dollar notation for USD and an explicit code for other currencies."""
        amount = (cents or 0) / 100
        currency = (currency or 'USD').upper()
        return f'${amount:,.2f}' if currency == 'USD' else f'{currency} {amount:,.2f}'

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
            r'<a href="\1" dir="ltr" style="display:inline-block;direction:ltr;unicode-bidi:embed;background:#b49a52;color:#172f4c;font-weight:700;line-height:1.4;text-decoration:none;padding:11px 17px;border-radius:5px;word-break:break-word">\1</a>',
            safe_body)
        # Email clients do not inherit the application's page direction. Infer
        # it from the actual message so a Yiddish/Hebrew draft remains RTL even
        # when it was composed while the staff interface was in English.
        rtl_letters = len(re.findall(r'[\u0590-\u05ff]', body))
        latin_letters = len(re.findall(r'[A-Za-z]', body))
        email_direction = 'rtl' if rtl_letters > latin_letters else 'ltr'
        email_align = 'right' if email_direction == 'rtl' else 'left'
        paragraphs = ''.join(
            f'<p dir="{email_direction}" style="direction:{email_direction};text-align:{email_align};margin:0 0 18px;color:#17385f;font-size:16px;line-height:1.65">'
            f'{paragraph.replace(chr(10), "<br>")}</p>'
            for paragraph in safe_body.split('\n\n') if paragraph
        )
        logo_url = absolute_url('static', filename='yazory-logo.png')
        html = f'''<!doctype html>
<html dir="{email_direction}"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body dir="{email_direction}" style="direction:{email_direction};margin:0;padding:0;background:#f8f7f3;font-family:Arial,'Segoe UI',sans-serif;color:#17385f">
<table dir="{email_direction}" role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="direction:{email_direction};background:#f8f7f3">
<tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:620px;background:#ffffff;border:1px solid #e3e5e9;border-radius:8px;overflow:hidden">
<tr><td align="center" style="background:#ffffff;padding:24px 24px 18px;border-bottom:4px solid #b49a52">
<img src="{logo_url}" width="150" alt="Yazory · יעזורי" style="display:block;width:150px;max-width:45%;height:auto;border:0">
</td></tr>
<tr><td dir="{email_direction}" align="{email_align}" style="direction:{email_direction};text-align:{email_align};padding:34px 38px 24px">{paragraphs}</td></tr>
<tr><td style="background:#173e66;padding:20px 28px;text-align:center;color:#ffffff">
<div style="font-size:14px;font-weight:700;letter-spacing:.3px">Yazory · יעזורי</div>
<div style="margin-top:6px;color:#d4dfeb;font-size:12px;line-height:1.5">A circle of support.</div>
</td></tr>
</table>
</td></tr></table>
</body></html>'''
        if app.config['TESTING'] or app.config['DEMO']:
            message.status = 'preview'
            message.error = 'Email delivery is disabled in preview mode.'
            return message
        provider_id, error = deliver(app.config['RESEND_API_KEY'], app.config['EMAIL_FROM'],
                                     recipient, subject, html, body)
        message.provider_id = provider_id or ''
        message.error = error or ''
        message.status = 'failed' if error else 'sent'
        message.sent_at = None if error else utcnow()
        return message

    # Extension modules use the same branded, persisted delivery path. Keeping
    # one sender also keeps provider status and Email history authoritative.
    app.extensions['send_email'] = send_email

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

    def ensure_schema(run_data_migrations=False):
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
        if 'email' not in contact_columns:
            db.session.execute(text(
                "ALTER TABLE contact ADD COLUMN email VARCHAR(254) NOT NULL DEFAULT ''"
            ))
        for column, definition in {
            'home_phone': "VARCHAR(80) NOT NULL DEFAULT ''",
            'cell_phone': "VARCHAR(80) NOT NULL DEFAULT ''",
            'home_address': "VARCHAR(240) NOT NULL DEFAULT ''",
            'city': "VARCHAR(120) NOT NULL DEFAULT ''",
            'state': "VARCHAR(80) NOT NULL DEFAULT ''",
            'zip_code': "VARCHAR(20) NOT NULL DEFAULT ''",
            'workplace': "VARCHAR(160) NOT NULL DEFAULT ''",
            'work_phone': "VARCHAR(80) NOT NULL DEFAULT ''",
            'notes': "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in contact_columns:
                db.session.execute(text(f'ALTER TABLE contact ADD COLUMN {column} {definition}'))
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
        campaign_columns = {column['name'] for column in inspect(db.engine).get_columns('charity_campaign')}
        if 'api_key_encrypted' not in campaign_columns:
            db.session.execute(text(
                "ALTER TABLE charity_campaign ADD COLUMN api_key_encrypted TEXT NOT NULL DEFAULT ''"))
        if 'public_url' not in campaign_columns:
            db.session.execute(text(
                "ALTER TABLE charity_campaign ADD COLUMN public_url VARCHAR(1000) NOT NULL DEFAULT ''"))
        # PostgreSQL's full SQLAlchemy reflection query calls
        # pg_get_serial_sequence() for every column and can wait indefinitely
        # behind an otherwise harmless lock held by a live deployment.  This
        # lightweight catalog lookup is sufficient for additive migrations.
        if db.engine.dialect.name == 'postgresql':
            payout_columns = set(db.session.scalars(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'applicant_payout'"
            )).all())
        else:
            payout_columns = {column['name'] for column in inspect(db.engine).get_columns(
                'applicant_payout')}
        for column in ('routing_number_encrypted', 'account_number_encrypted'):
            if column not in payout_columns:
                db.session.execute(text(
                    f"ALTER TABLE applicant_payout ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"))
        if db.engine.dialect.name == 'postgresql':
            payout_columns = set(db.session.scalars(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'applicant_payout'"
            )).all())
        else:
            payout_columns = {column['name'] for column in inspect(db.engine).get_columns(
                'applicant_payout')}
        for column, definition in {
            'check_bank_account_id': 'INTEGER REFERENCES check_bank_account(id)',
            'check_bank_account_name': "VARCHAR(160) NOT NULL DEFAULT ''",
            'check_bank_name': "VARCHAR(160) NOT NULL DEFAULT ''",
            'prior_case_check_count': 'INTEGER NOT NULL DEFAULT 0',
            'recipient_message': "VARCHAR(500) NOT NULL DEFAULT ''",
        }.items():
            if column not in payout_columns:
                db.session.execute(text(f'ALTER TABLE applicant_payout ADD COLUMN {column} {definition}'))
        # This historical backfill used to rescan every family and child on
        # every Gunicorn worker start.  That made autoscale cold starts slower
        # as real data accumulated. Existing installations with a populated
        # institution directory have already completed it; a genuinely legacy
        # database (profile data but no directory rows) still gets migrated.
        directory_marker = db.session.get(
            OrganizationSetting, 'profile_directory_backfill_v1')
        if directory_marker is None or run_data_migrations:
            has_directory = db.session.scalar(select(Institution.id).limit(1)) is not None
            has_legacy_family_data = db.session.scalar(select(Family.id).where(or_(
                Family.weekday_shul != '', Family.shabbos_shul != '',
                Family.yeshivah != '')).limit(1)) is not None
            has_legacy_child_data = db.session.scalar(select(Child.id).where(
                Child.school != '').limit(1)) is not None
            if run_data_migrations or (
                    not has_directory and (has_legacy_family_data or has_legacy_child_data)):
                for family in db.session.scalars(select(Family)).all():
                    connect_family_profile_directories(family)
                for child in db.session.scalars(select(Child)).all():
                    connect_child_profile_directory(child)
                merge_duplicate_institutions()
            if directory_marker is None:
                db.session.add(OrganizationSetting(
                    key='profile_directory_backfill_v1', value={'completed': True}))
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
        return {'income': report['earnings'], 'assistance': report['usable_help'],
                'children_count': intake.get('children_count'),
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

    @app.template_filter('american_date')
    def american_date(value):
        """Render a date or timestamp in the application's standard format."""
        if value is None:
            return ''
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value[:10])
            except ValueError:
                return value
        return value.strftime('%m/%d/%Y')
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
        language=session.get('language', 'en')
        eastern_today=datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
        from jewish_calendar import calendar_line
        return dict(language=language, languages=LANGUAGES, direction='rtl' if language in ('he','yi') else 'ltr', csrf=session['csrf'], demo=app.config['DEMO'], stripe_enabled=bool(app.config['STRIPE_SECRET_KEY']), categories=expense_categories(), relationships=RELATIONSHIPS, contact_statuses=CONTACT_STATUSES, pledge_frequencies=PLEDGE_FREQUENCIES, family_transitions=FAMILY_TRANSITIONS, expense_transitions=EXPENSE_TRANSITIONS, current_month=datetime.now().strftime('%Y-%m'), hebrew_calendar=calendar_line(eastern_today,language), document_allowed=app.extensions['workflows']['document_allowed'], contact_visible=contact_visible, current_staff=user, is_org_admin=organization_admin(), can_manage_household=can_manage_household(), can_manage_supporters=can_manage_supporters(), is_fundraiser=bool(user and user.role == 'fundraiser'))

    @app.before_request
    def security():
        public_endpoints = ('static', 'health', 'set_language', 'login', 'forgot_password',
                            'reset_password', 'accept_invitation', 'about', 'privacy',
                            'terms', 'donation_policy', 'stripe_webhook',
                            'stripe_success', 'stripe_cancel', 'supporter_login',
                            'supporter_login_link', 'supporter_portal',
                            'supporter_logout', 'supporter_portal_update_pledge',
                            'supporter_portal_donate', 'supporter_portal_manage_payment',
                            'supporter_portal_receipt',
                            'native_payment_submit', 'native_payment_success')
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

    def optional_email_field(name='email'):
        value = field(name, limit=254).lower()
        if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
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

    def case_fund_totals(family_id):
        """Cash received, committed/disbursed, and the remaining case balance."""
        # Fetch all four independent totals in one database round trip. On the
        # hosted Postgres connection, network latency made the former four
        # sequential scalar queries noticeably slow on every profile visit.
        manual_receipts = select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.family_id == family_id).scalar_subquery()
        charity_receipts = select(func.coalesce(func.sum(CharityDonation.net_cents), 0)).join(
            CharityCampaign, CharityCampaign.id == CharityDonation.campaign_id).where(
            CharityCampaign.family_id == family_id).scalar_subquery()
        paid = select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
            Expense.family_id == family_id, Expense.status == 'Paid').scalar_subquery()
        payouts = select(func.coalesce(func.sum(ApplicantPayout.amount_cents), 0)).where(
            ApplicantPayout.family_id == family_id,
            ApplicantPayout.status != 'voided').scalar_subquery()
        manual_collected, abcharity_collected, paid_expenses, direct_payouts = \
            db.session.execute(select(
                manual_receipts, charity_receipts, paid, payouts)).one()
        collected = manual_collected + abcharity_collected
        given_out = paid_expenses + direct_payouts
        return {'collected': collected, 'given_out': given_out,
                'available': collected - given_out}

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
        receipt_email = donor_email or contact.email
        if receipt_email:
            send_email('donation_receipt', receipt_email, 'Your Yazory donation receipt',
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
        # Do not write…13962 tokens truncated….extensions['workflows']['models']['SupporterLink']
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
        family_statement = select(Family).order_by(Family.name)
        if not organization_admin():
            family_statement = family_statement.where(Family.id.in_(
                select(FamilyAssignment.family_id).where(
                    FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(family_statement).all()
        return render_template('collections.html', title='Collections', contacts=contacts,
                               receipts=receipts, received_by_contact=received_by_contact,
                               lifetime_by_contact=lifetime_by_contact, month=month,
                               families=families)

    @app.post('/collections/receipts')
    def record_receipt():
        require_capability(('family_admin', 'fundraiser'))
        contact_value = request.form.get('contact_id', '')
        if contact_value == '__new__':
            family_id = request.form.get('family_id', type=int)
            family = db.session.get(Family, family_id)
            if family is None:
                abort(400, 'Choose a family for the new donor.')
            if not can_access_family(family.id):
                abort(403, 'You are not assigned to this family.')
            donor_name = field('donor_name', True, 160)
            donor_phone = field('donor_phone', limit=80)
            donor_key = supporter_key(donor_name, donor_phone)
            contact = db.session.scalar(select(Contact).where(
                Contact.family_id == family.id,
                Contact.supporter_key == donor_key))
            if contact is None:
                contact = Contact(
                    family_id=family.id, name=donor_name, phone=donor_phone,
                    relationship='Other', supporter_key=donor_key,
                    monthly_cents=0, pledge_frequency='One time',
                    status='Contacted')
                db.session.add(contact)
                db.session.flush()
                audit(f'Added supporter from manual donation: {donor_name}', family.id)
        else:
            contact_id = request.form.get('contact_id', type=int)
            if not contact_id:
                abort(400, 'Choose a supporter or enter a new donor.')
            contact = db.session.scalar(scoped_contacts_statement().where(
                Contact.id == contact_id))
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
        possible_parents = db.session.scalars(select(Contact).where(
            Contact.family_id == contact.family_id,
            Contact.id != contact.id
        ).order_by(Contact.name)).all()
        descendants, pending = set(), [contact.id]
        while pending:
            found = db.session.scalars(select(Contact.id).where(Contact.parent_contact_id.in_(pending))).all()
            pending = [row_id for row_id in found if row_id not in descendants]
            descendants.update(pending)
        possible_parents = [row for row in possible_parents
                            if row.id not in descendants and contact_visible(row)]
        return render_template('supporter_detail.html', title='Supporter history',
                               supporter=contact, linked_contacts=linked_contacts,
                               hierarchy_groups=hierarchy_groups,
                               receipts=receipts, payments=payments,
                               possible_parents=possible_parents,
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
        network_id = request.args.get('network_id', type=int)
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
        selected_institution = next((institution for institution in visible_institutions
                                     if institution.id == network_id), None)
        if network_id is not None and selected_institution is None:
            abort(404)
        if selected_institution is None and visible_institutions:
            selected_institution = visible_institutions[0]
        return render_template('directories.html', title=f'{kind} list', kind=kind,
                               institutions=visible_institutions, families=families,
                               selected_family_id=family_id, people=people,
                               people_by_key=people_by_key, query=query,
                               selected_institution=selected_institution)

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
        return redirect(url_for('community_directories', kind=institution.kind,
                                network_id=institution.id))

    @app.post('/community-directories/people')
    def add_directory_person():
        """Create a supporter from inside a directory and connect them immediately."""
        require_organization_admin()
        institution = db.get_or_404(Institution, request.form.get('institution_id', type=int))
        family_id = request.form.get('family_id', type=int)
        family = db.session.get(Family, family_id) if family_id else None
        if family is None:
            abort(400, 'Choose a valid applicant.')
        name = field('name', True)
        phone = field('phone', limit=80)
        relationship = field('relationship', True)
        if relationship not in set(RELATIONSHIPS) | LEGACY_RELATIONSHIPS:
            abort(400, 'Choose a valid relationship.')
        key = supporter_key(name, phone)
        if key.startswith('phone:') and db.session.scalar(select(Contact.id).where(
                Contact.family_id == family.id, Contact.supporter_key == key)):
            abort(400, 'This supporter is already connected to this case.')
        contact = Contact(family_id=family.id, name=name, phone=phone,
                          relationship=relationship, supporter_key=key,
                          monthly_cents=0, pledge_frequency='Monthly',
                          status='To contact')
        db.session.add(contact)
        db.session.flush()
        grade = field('grade', required=institution.kind == 'Yeshivah', limit=80)
        year_from = year_to = None
        if institution.kind == 'Yeshivah':
            try:
                year_from = int(field('year_from', True, 4))
                year_to = int(field('year_to', True, 4))
            except ValueError:
                abort(400, 'Enter a valid year.')
            if not (1900 <= year_from <= year_to <= 2100):
                abort(400, 'Enter valid attendance years.')
        db.session.add(PersonAffiliation(
            institution_id=institution.id, person_type='supporter', person_id=contact.id,
            grade=grade, year_from=year_from, year_to=year_to,
            note=field('note', limit=300)))
        audit(f'Added and connected supporter to {institution.kind.lower()}: {institution.name}',
              family.id)
        db.session.commit()
        flash('New person added and connected.')
        return redirect(url_for('community_directories', kind=institution.kind,
                                family_id=family.id, network_id=institution.id))

    @app.post('/community-directories/affiliations/<int:affiliation_id>/delete')
    def delete_person_affiliation(affiliation_id):
        require_organization_admin()
        affiliation = db.get_or_404(PersonAffiliation, affiliation_id)
        kind = affiliation.institution.kind
        institution_id = affiliation.institution_id
        db.session.delete(affiliation)
        db.session.commit()
        flash('Connection removed.')
        return redirect(url_for('community_directories', kind=kind,
                                network_id=institution_id))

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
        applicant_payouts = db.session.scalars(select(ApplicantPayout).order_by(
            ApplicantPayout.created_at.desc()).limit(250)).all()
        bank_accounts = db.session.scalars(select(CheckBankAccount).where(
            CheckBankAccount.active.is_(True)).order_by(CheckBankAccount.name)).all()
        family_funds = {family.id: case_fund_totals(family.id) for family in families}
        download_id = request.args.get('download', type=int)
        newly_created_check = (db.session.get(ApplicantPayout, download_id)
                               if download_id else None)
        if (newly_created_check is not None and
                (newly_created_check.method != 'check' or
                 newly_created_check.status == 'voided')):
            newly_created_check = None
        return render_template('payouts.html', title='Payouts', recipients=recipients,
                               transfers=transfers, families=families,
                               approved_expenses=approved_expenses,
                               applicant_payouts=applicant_payouts, today=date.today(),
                               bank_accounts=bank_accounts, family_funds=family_funds,
                               newly_created_check=newly_created_check)

    @app.post('/payouts/check-accounts')
    def save_check_account():
        require_organization_admin()
        account_name = field('account_name', True, 160)
        bank_name = field('bank_name', True, 160)
        routing_number = re.sub(r'\D', '', field('routing_number', True, 20))
        account_number = re.sub(r'\D', '', field('account_number', True, 30))
        next_check_number = field('next_check_number', True, 12)
        if len(routing_number) != 9 or sum(int(digit) * weight for digit, weight in
                zip(routing_number, (3, 7, 1, 3, 7, 1, 3, 7, 1))) % 10:
            abort(400, 'Enter a valid 9-digit ABA routing number.')
        if not 4 <= len(account_number) <= 17:
            abort(400, 'Enter a valid bank account number.')
        if not next_check_number.isdigit():
            abort(400, 'Enter a valid starting check number.')
        bank_account = CheckBankAccount(
            name=account_name, bank_name=bank_name,
            routing_number_encrypted=encrypt_api_key(routing_number, app.config['SECRET_KEY']),
            account_number_encrypted=encrypt_api_key(account_number, app.config['SECRET_KEY']),
            account_last4=account_number[-4:], next_check_number=next_check_number)
        db.session.add(bank_account)
        audit(f'Added secure check-writing account: {account_name}')
        db.session.commit()
        flash('Check-writing account saved securely.')
        return redirect(url_for('payouts'))

    @app.post('/payouts/checks')
    def create_check_payout():
        require_organization_admin()
        family = db.session.get(Family, request.form.get('family_id', type=int))
        if family is None:
            abort(400, 'Choose a valid family.')
        if family.status != 'Active':
            abort(400, 'Payouts can only be created for an active family.')
        bank_account_id = request.form.get('check_bank_account_id', type=int)
        bank_account = db.session.execute(select(CheckBankAccount).where(
            CheckBankAccount.id == bank_account_id,
            CheckBankAccount.active.is_(True)).with_for_update()).scalar_one_or_none()
        if bank_account is None:
            abort(400, 'Choose a valid issuing account.')
        try:
            routing_number = decrypt_api_key(bank_account.routing_number_encrypted, app.config['SECRET_KEY'])
            account_number = decrypt_api_key(bank_account.account_number_encrypted, app.config['SECRET_KEY'])
        except Exception:
            abort(400, 'Save the issuing account details again.')
        check_number = bank_account.next_check_number
        if not check_number.isdigit():
            abort(400, 'Set the next automatic check number in bank information.')
        existing = db.session.scalar(select(ApplicantPayout.id).where(
            ApplicantPayout.method == 'check', ApplicantPayout.check_bank_account_id == bank_account.id,
            ApplicantPayout.check_number == check_number,
            ApplicantPayout.status != 'voided'))
        if existing:
            abort(409, 'The next automatic check number is already in use for this account.')
        try:
            check_date = date.fromisoformat(field('check_date', True, 10))
        except ValueError:
            abort(400, 'Enter a valid check date.')
        locality = ', '.join(part for part in (family.city, family.state) if part)
        if family.zip_code:
            locality = f'{locality} {family.zip_code}'.strip()
        mailing_address = '\n'.join(part for part in (family.address, locality) if part)
        if not mailing_address:
            abort(400, 'Add the applicant mailing address before creating a check.')
        payee_name = field('payee_name', True)
        if not re.search(r'[A-Za-z]', payee_name) or re.search(r'[^A-Za-z0-9 .,&\'()-]', payee_name):
            abort(400, 'Enter the check payee name in English.')
        payout_amount = amount('amount')
        available = case_fund_totals(family.id)['available']
        if payout_amount > available:
            abort(400, 'This check is greater than the amount available for this case.')
        payout = ApplicantPayout(
            family_id=family.id, method='check', amount_cents=payout_amount,
            payee_name=payee_name, mailing_address=mailing_address,
            memo=field('memo', limit=160), check_number=check_number,
            recipient_message=field('recipient_message', limit=500),
            check_date=check_date, status='created',
            routing_number_encrypted=encrypt_api_key(routing_number, app.config['SECRET_KEY']),
            account_number_encrypted=encrypt_api_key(account_number, app.config['SECRET_KEY']),
            check_bank_account_id=bank_account.id, check_bank_account_name=bank_account.name,
            check_bank_name=bank_account.bank_name,
            prior_case_check_count=db.session.scalar(select(db.func.count(ApplicantPayout.id)).where(
                ApplicantPayout.family_id == family.id, ApplicantPayout.method == 'check',
                ApplicantPayout.status != 'voided')) or 0,
            created_by=current_user().id if current_user() else None)
        db.session.add(payout)
        db.session.flush()
        bank_account.next_check_number = str(int(check_number) + 1).zfill(len(check_number))
        bank_account.updated_at = utcnow()
        audit(f'Created applicant payout check #{check_number} for ${payout.amount_cents / 100:,.2f}', family.id)
        db.session.commit()
        flash('Check created and added to manual check history.')
        return redirect(url_for('payouts', panel=3, download=payout.id))

    @app.post('/payouts/stripe')
    def create_stripe_payout():
        require_organization_admin()
        if not app.config['STRIPE_SECRET_KEY']:
            abort(503, 'Stripe payments are not configured.')
        family = db.session.get(Family, request.form.get('family_id', type=int))
        recipient = db.session.get(StripeRecipient, request.form.get('recipient_id', type=int))
        if family is None or family.status != 'Active':
            abort(400, 'Choose an active family.')
        if (recipient is None or recipient.kind != 'family' or
                recipient.family_id != family.id or not recipient.payouts_enabled):
            abort(400, 'Choose the verified Stripe recipient for this family.')
        payout = ApplicantPayout(
            family_id=family.id, method='stripe', amount_cents=amount('amount'),
            payee_name=recipient.name, mailing_address='', memo=field('memo', limit=160),
            status='processing', created_by=current_user().id if current_user() else None)
        db.session.add(payout)
        db.session.flush()
        try:
            transfer = create_transfer(app.config['STRIPE_SECRET_KEY'], {
                'amount': payout.amount_cents, 'currency': app.config['STRIPE_CURRENCY'],
                'destination': recipient.stripe_account_id,
                'transfer_group': f'YAZORY_PAYOUT_{payout.id}',
                'metadata': {'yazory_payout_id': str(payout.id),
                             'yazory_family_id': str(family.id)}},
                f'yazory-payout-{payout.id}')
        except Exception:
            db.session.rollback()
            abort(502, 'Stripe could not send this payout. No Yazory payout record was created.')
        payout.stripe_reference = stripe_value(transfer, 'id', '')
        if not payout.stripe_reference:
            db.session.rollback()
            abort(502, 'Stripe did not return a payout reference. No Yazory payout record was created.')
        payout.status = 'sent'
        audit(f'Sent applicant payout #{payout.id} through Stripe: {payout.stripe_reference}', family.id)
        db.session.commit()
        flash('Applicant payout sent through Stripe.')
        return redirect(url_for('payouts'))

    @app.get('/payouts/<int:payout_id>/check.pdf')
    def download_payout_check(payout_id):
        require_organization_admin()
        payout = db.get_or_404(ApplicantPayout, payout_id)
        if payout.method != 'check' or payout.status == 'voided':
            abort(400, 'This check cannot be printed.')
        from check_pdf import build_check_pdf
        try:
            routing_number = decrypt_api_key(payout.routing_number_encrypted, app.config['SECRET_KEY'])
            account_number = decrypt_api_key(payout.account_number_encrypted, app.config['SECRET_KEY'])
        except Exception:
            abort(400, 'The saved bank details for this check cannot be read.')
        return send_file(build_check_pdf(payout, routing_number, account_number, payout.check_bank_name),
                         mimetype='application/pdf', as_attachment=True,
                         download_name=f'Yazory-check-{secure_filename(payout.check_number)}.pdf')

    @app.post('/payouts/<int:payout_id>/status')
    def update_payout_status(payout_id):
        require_organization_admin()
        payout = db.get_or_404(ApplicantPayout, payout_id)
        next_status = field('status', True, 30)
        transitions = {'created': {'mailed', 'voided'}, 'mailed': {'cleared', 'voided'},
                       'cleared': set(), 'voided': set()}
        if next_status not in transitions.get(payout.status, set()):
            abort(400, 'This payout status change is not allowed.')
        changed_at = utcnow()
        payout.status = next_status
        if next_status == 'mailed':
            payout.mailed_at = changed_at
        elif next_status == 'cleared':
            payout.cleared_at = changed_at
        elif next_status == 'voided':
            payout.voided_at = changed_at
        audit(f'Applicant payout check #{payout.check_number}: {next_status}', payout.family_id)
        db.session.commit()
        flash({'mailed': 'Check marked as mailed.', 'cleared': 'Check marked as cleared.',
               'voided': 'Check voided.'}[next_status])
        return redirect(url_for('payouts', panel=3))

    @app.post('/payouts/<int:payout_id>/delete')
    def delete_voided_payout_check(payout_id):
        require_organization_admin()
        payout = db.get_or_404(ApplicantPayout, payout_id)
        if payout.method != 'check' or payout.status != 'voided':
            abort(400, 'Only a voided check can be deleted.')
        check_number, family_id = payout.check_number, payout.family_id
        db.session.delete(payout)
        audit(f'Deleted voided applicant payout check #{check_number}', family_id)
        db.session.commit()
        flash('Voided check deleted.')
        return redirect(url_for('payouts', panel=3))

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
        # Explicit maintenance remains the place for full idempotent data
        # repair. Normal web-worker startup uses the lightweight path below.
        ensure_schema(run_data_migrations=True)
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
        for hook in app.extensions.get('init_db_hooks', ()):
            hook()
        ensure_bootstrap_owner()
        print('Database initialized. Existing records preserved.')

    @app.cli.command('migrate-db')
    def migrate_db():
        """Add tables absent from a legacy deployment; never drop or rewrite data."""
        db.create_all()
        print('Database migration completed. Existing records preserved.')

    with app.app_context():
        # Production schema work is performed explicitly with `flask init-db`
        # before publishing. Running reflection, DDL and legacy backfills while
        # every Gunicorn worker boots can hold the worker past Replit's short
        # health-check window, so production startup must remain read-only and
        # fast. Demo/test databases are disposable and still self-initialize.
        if app.config['DEMO'] or app.config.get('TESTING'):
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
