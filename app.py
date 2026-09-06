import os
import secrets
import hmac
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, func
from werkzeug.security import check_password_hash

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
    if production and (demo or len(secret) < 32 or not admin_email or not database.startswith('postgresql+psycopg://')):
        raise RuntimeError('Production requires PostgreSQL DATABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD_HASH and SESSION_SECRET (32+ characters).')
    app.config.update(SECRET_KEY=secret or secrets.token_hex(32), SQLALCHEMY_DATABASE_URI=database, SQLALCHEMY_TRACK_MODIFICATIONS=False, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=production, PERMANENT_SESSION_LIFETIME=timedelta(minutes=30), MAX_CONTENT_LENGTH=64*1024, DEMO=demo, ADMIN_EMAIL=admin_email, ADMIN_PASSWORD_HASH=password_hash)
    if test_config:
        app.config.update(test_config)
    if app.config['DEMO'] and not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        raise RuntimeError('Demo mode must use a local SQLite database, never a shared production database.')
    db.init_app(app)

    @app.template_filter('money')
    def money(cents):
        return f'${(cents or 0)/100:,.2f}'

    @app.context_processor
    def common():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return dict(csrf=session['csrf'], demo=app.config['DEMO'], categories=CATEGORIES, relationships=RELATIONSHIPS, contact_statuses=CONTACT_STATUSES, family_transitions=FAMILY_TRANSITIONS, expense_transitions=EXPENSE_TRANSITIONS, current_month=datetime.now().strftime('%Y-%m'))

    @app.before_request
    def security():
        if request.endpoint in ('static', 'health'):
            return
        if request.method == 'POST' and not hmac.compare_digest(session.get('csrf', ''), request.form.get('csrf', '')):
            abort(400, 'Your form expired. Reload the page and try again.')
        if request.method == 'POST' and not session.get('csrf'):
            abort(400)
        if not app.config['DEMO'] and not session.get('user') and request.endpoint != 'login':
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
        db.session.add(Audit(actor=session.get('user', 'Demo user'), action=action, family_id=family_id))

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

    @app.get('/health')
    def health():
        db.session.execute(select(1))
        return {'status': 'ok'}

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            # A fixed delay makes bulk password guessing expensive; staff auth will be replaced by per-user accounts.
            import time
            time.sleep(1)
            email = field('email', True)
            if email.lower() == app.config['ADMIN_EMAIL'].lower() and check_password_hash(app.config['ADMIN_PASSWORD_HASH'], request.form.get('password', '')):
                session.clear()
                session['user'] = email
                session.permanent = True
                return redirect(url_for('dashboard'))
            flash('Email or password is incorrect.', 'error')
        return render_template('login.html', title='Staff sign in')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    def dashboard():
        families = db.session.scalars(select(Family).order_by(Family.id.desc())).all()
        month = datetime.now().strftime('%Y-%m')
        expenses = db.session.scalars(select(Expense).where(Expense.month == month)).all()
        pledged = db.session.scalar(select(func.coalesce(func.sum(Contact.monthly_cents), 0)).where(Contact.status == 'Pledged', Contact.family_id.in_(select(Family.id).where(Family.status == 'Active'))))
        requested = db.session.scalars(select(Expense).where(Expense.status == 'Requested').order_by(Expense.id.desc())).all()
        return render_template('dashboard.html', title='Overview', families=families, active=sum(f.status=='Active' for f in families), pledged=pledged, approved=sum(e.amount_cents for e in expenses if e.status in ('Approved','Paid')), paid=sum(e.amount_cents for e in expenses if e.status=='Paid'), requested=requested)

    @app.get('/families')
    def families():
        query = request.args.get('q', '').strip()[:160]
        statement = select(Family).order_by(Family.id.desc())
        if query:
            statement = statement.where(Family.name.icontains(query, autoescape=True))
        return render_template('families.html', title='Families', families=db.session.scalars(statement).all(), query=query)

    @app.route('/families/new', methods=['GET', 'POST'])
    def new_family():
        if request.method == 'POST':
            family = Family(name=field('name', True), **{k: field(k, limit=300 if k=='address' else 80 if k=='phone' else 160) for k in ['spouse','phone','address','father','inlaws','rabbi','weekday_shul','shabbos_shul']}, circumstances=field('circumstances', limit=5000))
            db.session.add(family)
            db.session.flush()
            audit('Created family intake', family.id)
            db.session.commit()
            flash('Family intake saved.')
            return redirect(url_for('family_detail', family_id=family.id))
        return render_template('family_form.html', title='New family intake', family=None)

    @app.route('/families/<int:family_id>/edit', methods=['GET', 'POST'])
    def edit_family(family_id):
        family = db.get_or_404(Family, family_id)
        if request.method == 'POST':
            for key in ['name','spouse','phone','address','father','inlaws','rabbi','weekday_shul','shabbos_shul','circumstances']:
                setattr(family, key, field(key, required=key=='name', limit=5000 if key=='circumstances' else 300 if key=='address' else 80 if key=='phone' else 160))
            audit('Updated family profile', family.id)
            db.session.commit()
            flash('Profile updated.')
            return redirect(url_for('family_detail', family_id=family.id))
        return render_template('family_form.html', title='Edit family profile', family=family)

    @app.get('/families/<int:family_id>')
    def family_detail(family_id):
        family = db.get_or_404(Family, family_id)
        activity = db.session.scalars(select(Audit).where(Audit.family_id==family.id).order_by(Audit.id.desc()).limit(30)).all()
        return render_template('family.html', title=family.name, family=family, activity=activity, pledged=sum(c.monthly_cents for c in family.contacts if c.status=='Pledged'))

    @app.post('/families/<int:family_id>/status')
    def family_status(family_id):
        family = db.get_or_404(Family, family_id)
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
        db.get_or_404(Family, family_id)
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
        db.get_or_404(Family, family_id)
        relationship = field('relationship', True)
        status = field('status', True)
        if relationship not in RELATIONSHIPS or status not in CONTACT_STATUSES: abort(400)
        pledge = amount('monthly', allow_zero=status!='Pledged')
        db.session.add(Contact(family_id=family_id, name=field('name', True), relationship=relationship, phone=field('phone', limit=80), monthly_cents=pledge, status=status))
        audit('Added donor network contact', family_id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=family_id))

    @app.post('/contacts/<int:contact_id>')
    def update_contact(contact_id):
        contact = db.get_or_404(Contact, contact_id)
        status = field('status', True)
        if status not in CONTACT_STATUSES: abort(400)
        contact.status = status
        contact.monthly_cents = amount('monthly', allow_zero=status!='Pledged')
        audit(f'Updated donor pledge: {status}', contact.family_id)
        db.session.commit()
        return redirect(url_for('family_detail', family_id=contact.family_id))

    @app.post('/families/<int:family_id>/expenses')
    def add_expense(family_id):
        family = db.get_or_404(Family, family_id)
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

    @app.get('/expenses')
    def expenses():
        status = request.args.get('status', '')
        statement = select(Expense).order_by(Expense.id.desc())
        if status:
            if status not in EXPENSE_TRANSITIONS: abort(400)
            statement = statement.where(Expense.status==status)
        return render_template('expenses.html', title='Expenses & approvals', expenses=db.session.scalars(statement).all(), selected_status=status)

    @app.post('/expenses/<int:expense_id>/status')
    def expense_status(expense_id):
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
        return render_template('activity.html', title='Activity log', activity=db.session.scalars(select(Audit).order_by(Audit.id.desc()).limit(200)).all())

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error(exc):
        return render_template('error.html', title='Unable to complete request', message=exc.description), exc.code

    @app.cli.command('init-db')
    def init_db():
        db.create_all()
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
