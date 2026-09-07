import os
import secrets
import hmac
import re
from io import BytesIO
from datetime import datetime, timedelta, timezone
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
    receipts = db.relationship('Receipt', backref='contact', lazy=True)

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

    def ensure_schema():
        """Create missing tables and apply the additive legacy-schema upgrades."""
        db.create_all()
        family_columns = {column['name'] for column in inspect(db.engine).get_columns('family')}
        for column, definition in {
            'city': 'VARCHAR(120)',
            'state': 'VARCHAR(80)',
            'zip_code': 'VARCHAR(20)',
        }.items():
            if column not in family_columns:
                db.session.execute(text(
                    f"ALTER TABLE family ADD COLUMN {column} {definition} DEFAULT ''"
                ))
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
        return dict(language=session.get('language', 'en'), languages=LANGUAGES, direction='rtl' if session.get('language') in ('he','yi') else 'ltr', csrf=session['csrf'], demo=app.config['DEMO'], categories=expense_categories(), relationships=RELATIONSHIPS, contact_statuses=CONTACT_STATUSES, family_transitions=FAMILY_TRANSITIONS, expense_transitions=EXPENSE_TRANSITIONS, current_month=datetime.now().strftime('%Y-%m'), current_staff=user, is_org_admin=organization_admin(), can_manage_household=can_manage_household(), can_manage_supporters=can_manage_supporters(), is_fundraiser=bool(user and user.role == 'fundraiser'))

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
        statement = select(Family).order_by(Family.id.desc())
        if not organization_admin():
            statement = statement.where(Family.id.in_(select(FamilyAssignment.family_id).where(FamilyAssignment.staff_user_id == current_user().id)))
        families = db.session.scalars(statement).all()
        family_ids = [family.id for family in families]
        month = datetime.now().strftime('%Y-%m')
        expenses = db.session.scalars(select(Expense).where(Expense.month == month, Expense.family_id.in_(family_ids))).all()
        network_visible = organization_admin() or bool(current_user() and current_user().role in ('family_admin', 'fundraiser'))
        pledged = db.session.scalar(select(func.coalesce(func.sum(Contact.monthly_cents), 0)).where(Contact.status == 'Pledged', Contact.family_id.in_(select(Family.id).where(Family.status == 'Active', Family.id.in_(family_ids))))) if network_visible else 0
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
            ('name','spouse','phone','address','city','state','zip_code','father','inlaws','rabbi','weekday_shul','shabbos_shul','circumstances')} if family else {})
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
            family = Family(name=field('name', True), **{k: field(k, limit={'address':300, 'city':120, 'state':80, 'zip_code':20, 'phone':80}.get(k, 160)) for k in ['spouse','phone','address','city','state','zip_code','father','inlaws','rabbi','weekday_shul','shabbos_shul']}, circumstances=field('circumstances', limit=5000))
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
            limits = {'circumstances':5000, 'address':300, 'city':120, 'state':80, 'zip_code':20, 'phone':80}
            for key in ['name','spouse','phone','address','city','state','zip_code','father','inlaws','rabbi','weekday_shul','shabbos_shul','circumstances']:
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
        return render_template('family.html', title=family.name, family=family, activity=activity,
                               budget=budget_totals(family),
                               pledged=sum(c.monthly_cents for c in family.contacts if c.status=='Pledged'))

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
        db.session.add(Child(family_id=family_id, name=field('name', True), age=age, grade=field('grade', limit=80), school=field('school'), tuition_contact=field('tuition_contact', limit=300)))
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
        if category not in expense_categories(): abort(400)
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
        require_capability(('fundraiser', 'family_admin'))
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
        pledged = sum(contact.monthly_cents for contact in contacts if contact.status == 'Pledged')
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
        statement = scoped_contacts_statement()
        if query:
            statement = statement.where(Contact.name.icontains(query, autoescape=True))
        contacts = db.session.scalars(statement).all()
        totals = {c.id: db.session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.contact_id == c.id)) for c in contacts}
        return render_template('supporters.html', title='Supporters', contacts=contacts,
                               received=totals, query=query)

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
            pledged = sum(c.monthly_cents for c in family.contacts if c.status == 'Pledged')
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

    @app.get('/people-access')
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
        ensure_bootstrap_owner()
        print('Database initialized. Existing records preserved.')

    @app.cli.command('migrate-db')
    def migrate_db():
        """Add tables absent from a legacy deployment; never drop or rewrite data."""
        db.create_all()
        print('Database migration completed. Existing records preserved.')

    with app.app_context():
        if app.config['DEMO']:
            ensure_schema()
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
