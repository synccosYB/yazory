import os
import secrets
import hmac
import re
from io import BytesIO
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, func, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from translations import LANGUAGES, translate, translate_audit

from intake import validate_intake, intake_for_form

db = SQLAlchemy()

class Family(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    spouse = db.Column(db.String(160), default='')
    phone = db.Column(db.String(80), default='')
    address = db.Column(db.String(300), default='')
    father = db.Column(db.String(160), default='')
    inlaws = db.Column(db.String(160), default='')
    rabbi = db.Column(db.String(160), default='')
    weekday_shul = db.Column(db.String(160), default='')
    shabbos_shul = db.Column(db.String(160), default='')
    circumstances = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='Intake', nullable=False)
    children = db.relationship('Child', backref='family', lazy=True)
    contacts = db.relationship('Contact', backref='family', lazy=True)
    expenses = db.relationship('Expense', backref='family', lazy=True)
    documents = db.relationship('Document', backref='family', lazy=True, cascade='all, delete-orphan')
    assignments = db.relationship('FamilyAssignment', backref='family', lazy=True, cascade='all, delete-orphan')

class HouseholdIntake(db.Model):
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), primary_key=True)
    data = db.Column(db.JSON, nullable=False, default=dict)
    family = db.relationship('Family', backref=db.backref('intake_record', uselist=False))


class StaffUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='family_admin')
    assignments = db.relationship('FamilyAssignment', backref='staff_user', lazy=True, cascade='all, delete-orphan')

class FamilyAssignment(db.Model):
    __table_args__ = (UniqueConstraint('staff_user_id', 'family_id', name='uq_family_assignment'),)
    id = db.Column(db.Integer, primary_key=True)
    staff_user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)

class Child(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    grade = db.Column(db.String(80), default='')
    school = db.Column(db.String(160), nullable=False)
    tuition_contact = db.Column(db.String(300), default='')

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    relationship = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(80), default='')
    monthly_cents = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(30), default='To contact', nullable=False)

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
CATEGORIES = ['Tuition', 'Groceries', 'Butcher', 'Rent / mortgage', 'Utilities', 'Transportation', 'Organization expense', 'Other']
RELATIONSHIPS = ['Sibling', 'Spouse’s sibling', 'First cousin', 'Second cousin', 'Yeshivah / school friend', 'Friend', 'Other']
CONTACT_STATUSES = ['To contact', 'Contacted', 'Pledged', 'Paused', 'Declined']

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
    app.config.update(SECRET_KEY=secret or secrets.token_hex(32), SQLALCHEMY_DATABASE_URI=database, SQLALCHEMY_TRACK_MODIFICATIONS=False, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=production, PERMANENT_SESSION_LIFETIME=timedelta(minutes=30), MAX_CONTENT_LENGTH=10*1024*1024, DEMO=demo, ADMIN_EMAIL=admin_email, ADMIN_PASSWORD_HASH=password_hash)
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
        return dict(language=session.get('language', 'en'), languages=LANGUAGES, direction='rtl' if session.get('language') in ('he','yi') else 'ltr', csrf=session['csrf'], demo=app.config['DEMO'], categories=CATEGORIES, relationships=RELATIONSHIPS, contact_statuses=CONTACT_STATUSES, family_transitions=FAMILY_TRANSITIONS, expense_transitions=EXPENSE_TRANSITIONS, current_month=datetime.now().strftime('%Y-%m'), current_staff=user, is_org_admin=organization_admin(), can_manage_household=can_manage_household(), can_manage_supporters=can_manage_supporters(), is_fundraiser=bool(user and user.role == 'fundraiser'))

    @app.before_request
    def security():
        if request.endpoint in ('static', 'health', 'set_language'):
            return
        if request.method == 'POST' and not hmac.compare_digest(session.get('csrf', ''), request.form.get('csrf', '')):
            abort(400, 'Your form expired. Reload the page and try again.')
        if request.method == 'POST' and not session.get('csrf'):
            abort(400)
        if not app.config['DEMO'] and request.endpoint != 'login':
            if not session.get('user_id'):
                return redirect(url_for('login'))
            if current_user() is None:
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
            email = field('email', True)
            ensure_bootstrap_owner()
            user = db.session.scalar(select(StaffUser).where(StaffUser.email == email.lower()))
            if user and check_password_hash(user.password_hash, request.form.get('password', '')):
                language = session.get('language', 'en')
                session.clear()
                session['language'] = language
                session['user_id'] = user.id
                session.permanent = True
                return redirect(url_for('dashboard'))
            flash('Email or password is incorrect.', 'error')
        return render_template('login.html', title='Staff sign in')

    @app.post('/logout')
    def logout():
        language = session.get('language', 'en')
        session.clear()
        session['language'] = language
        return redirect(url_for('login'))

    @app.get('/')
    def dashboard():
        if current_user() and current_user().role == 'fundraiser':
            return redirect(url_for('fundraising'))
        if current_user() and current_user().role == 'office_employee':
            return redirect(url_for('families'))
        statement = select(Family).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(statement).all()
        family_ids = [family.id for family in families]
        month = datetime.now().strftime('%Y-%m')
        expenses = db.session.scalars(select(Expense).where(Expense.month == month, Expense.family_id.in_(family_ids))).all()
        pledged = db.session.scalar(select(func.coalesce(func.sum(Contact.monthly_cents), 0)).where(Contact.status == 'Pledged', Contact.family_id.in_(select(Family.id).where(Family.status == 'Active', Family.id.in_(family_ids)))))
        requested_statement = select(Expense).where(Expense.status == 'Requested').order_by(Expense.id.desc())
        if not organization_admin():
            requested_statement = requested_statement.where(Expense.family_id.in_(
                select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        requested = db.session.scalars(requested_statement).all()
        return render_template('dashboard.html', title='Overview', families=families, active=sum(f.status=='Active' for f in families), pledged=pledged, approved=sum(e.amount_cents for e in expenses if e.status in ('Approved','Paid')), paid=sum(e.amount_cents for e in expenses if e.status=='Paid'), requested=requested)

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

    def intake_form(family, title, error=None):
        values = dict(request.form) if error else ({key: getattr(family, key) for key in
            ('name','spouse','phone','address','father','inlaws','rabbi','weekday_shul','shabbos_shul','circumstances')} if family else {})
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
            family = Family(name=field('name', True), **{k: field(k, limit=300 if k=='address' else 80 if k=='phone' else 160) for k in ['spouse','phone','address','father','inlaws','rabbi','weekday_shul','shabbos_shul']}, circumstances=field('circumstances', limit=5000))
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
            for key in ['name','spouse','phone','address','father','inlaws','rabbi','weekday_shul','shabbos_shul','circumstances']:
                setattr(family, key, field(key, required=key=='name', limit=5000 if key=='circumstances' else 300 if key=='address' else 80 if key=='phone' else 160))
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
        return render_template('family.html', title=family.name, family=family, activity=activity, pledged=sum(c.monthly_cents for c in family.contacts if c.status=='Pledged'))

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
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family.id))

    @app.post('/families/<int:family_id>/children')
    def add_child(family_id):
        require_capability(('family_admin', 'office_employee'))
        accessible_family_or_404(family_id)
        try:
            age = int(field('age', True))
            if not 0 <= age <= 30: raise ValueError()
        except ValueError:
            abort(400, 'Age must be between 0 and 30.')
        db.session.add(Child(family_id=family_id, name=field('name', True), age=age, grade=field('grade', limit=80), school=field('school', True), tuition_contact=field('tuition_contact', limit=300)))
        audit('Added child and school details', family_id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family_id))

    @app.post('/families/<int:family_id>/contacts')
    def add_contact(family_id):
        require_capability(('family_admin', 'fundraiser'))
        if not can_access_family(family_id):
            abort(403, 'You are not assigned to this family.')
        if db.session.get(Family, family_id) is None:
            abort(404)
        relationship = field('relationship', True)
        status = field('status', True)
        if relationship not in RELATIONSHIPS or status not in CONTACT_STATUSES: abort(400)
        pledge = amount('monthly', allow_zero=status!='Pledged')
        db.session.add(Contact(family_id=family_id, name=field('name', True), relationship=relationship, phone=field('phone', limit=80), monthly_cents=pledge, status=status))
        audit('Added donor network contact', family_id)
        db.session.commit()
        return redirect(url_for('fundraising_detail' if current_user() and current_user().role == 'fundraiser' else 'family_detail', family_id=family_id))

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
        contact.status = status
        contact.monthly_cents = amount('monthly', allow_zero=status!='Pledged')
        audit(f'Updated donor pledge: {status}', contact.family_id)
        db.session.commit()
        return redirect(url_for('fundraising_detail' if current_user() and current_user().role == 'fundraiser' else 'family_detail', family_id=contact.family_id))

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
        if category not in CATEGORIES: abort(400)
        month = field('month', True, 7)
        try:
            if datetime.strptime(month, '%Y-%m').strftime('%Y-%m') != month: raise ValueError()
        except ValueError:
            abort(400, 'Enter a valid month.')
        db.session.add(Expense(family_id=family_id, category=category, payee=field('payee', True), amount_cents=amount('amount'), month=month, note=field('note', limit=5000)))
        audit('Submitted expense request', family_id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family_id))

    @app.get('/fundraising')
    def fundraising():
        require_capability(('fundraiser',))
        statement = select(Family.id.label('id'), Family.name.label('name')).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(
                FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.execute(statement).all()
        pledged = {
            family.id: db.session.scalar(select(func.coalesce(func.sum(Contact.monthly_cents), 0)).where(
                Contact.family_id == family.id, Contact.status == 'Pledged'))
            for family in families
        }
        return render_template('fundraising.html', title='Fundraising workspace', families=families, pledged=pledged)

    @app.get('/fundraising/<int:family_id>')
    def fundraising_detail(family_id):
        require_capability(('fundraiser',))
        if not can_access_family(family_id):
            abort(403, 'You are not assigned to this family.')
        family = db.session.execute(select(Family.id.label('id'), Family.name.label('name')).where(
            Family.id == family_id)).one_or_none()
        if family is None:
            abort(404)
        contacts = db.session.scalars(select(Contact).where(Contact.family_id == family.id).order_by(Contact.id)).all()
        pledged = sum(contact.monthly_cents for contact in contacts if contact.status == 'Pledged')
        return render_template('fundraising_detail.html', title='Fundraising workspace', family=family,
                               contacts=contacts, pledged=pledged)

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
        db.session.commit()
        return redirect(url_for('expenses'))

    @app.get('/activity')
    def activity():
        require_organization_admin()
        return render_template('activity.html', title='Activity log', activity=db.session.scalars(select(Audit).order_by(Audit.id.desc()).limit(200)).all())

    @app.route('/staff', methods=['GET', 'POST'])
    def staff():
        require_organization_admin()
        if request.method == 'POST':
            email = field('email', True, 254).lower()
            role = field('role', True, 30)
            password = request.form.get('password', '')
            if role not in STAFF_ROLES or not 12 <= len(password) <= 256:
                abort(400, 'Choose a valid role and a password of at least 12 characters.')
            if db.session.scalar(select(StaffUser.id).where(StaffUser.email == email)):
                abort(400, 'A staff account already uses this email.')
            db.session.add(StaffUser(email=email, password_hash=generate_password_hash(password), role=role))
            db.session.commit()
            flash('Staff account created.')
            return redirect(url_for('staff'))
        owner = db.session.scalar(select(StaffUser).where(StaffUser.email == app.config['ADMIN_EMAIL'].strip().lower()))
        return render_template('staff.html', title='Staff & assignments', users=db.session.scalars(select(StaffUser).order_by(StaffUser.email)).all(), families=db.session.scalars(select(Family).order_by(Family.name)).all(), owner_user_id=owner.id if owner else None)

    @app.get('/settings')
    def settings():
        require_organization_admin()
        return redirect(url_for('staff'))

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
        db.session.commit()
        return redirect(url_for('staff'))

    from abcharity import register_abcharity
    register_abcharity(app, db, CharityCampaign, CharityDonor, CharityDonation,
                      Family, Contact, Expense, require_capability,
                      require_organization_admin, accessible_family_or_404, audit)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error(exc):
        return render_template('error.html', title='Unable to complete request', message=exc.description), exc.code

    @app.cli.command('init-db')
    def init_db():
        db.create_all()
        ensure_bootstrap_owner()
        print('Database initialized. Existing records preserved.')

    with app.app_context():
        if app.config['DEMO']:
            db.create_all()
            if not db.session.scalar(select(Family.id).limit(1)):
                family = Family(name='Sample family', spouse='Sample spouse', father='Sample father', inlaws='Sample in-laws', rabbi='Community rabbi', weekday_shul='Local shul', shabbos_shul='Local shul', circumstances='Fictional example: a household needs help with everyday expenses during illness.', status='Active')
                db.session.add(family)
                db.session.flush()
                db.session.add_all([Child(family_id=family.id, name='Sample child', age=9, grade='4', school='Sample school', tuition_contact='School tuition office'), Contact(family_id=family.id, name='Sample sibling', relationship='Sibling', monthly_cents=18000, status='Pledged'), Expense(family_id=family.id, category='Groceries', payee='Sample grocery', amount_cents=45000, month=datetime.now().strftime('%Y-%m'))])
                audit_entry = Audit(actor='System', action='Created fictional demo records', family_id=family.id)
                db.session.add(audit_entry)
                db.session.commit()
    return app

if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
