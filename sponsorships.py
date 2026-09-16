import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import UniqueConstraint, select

import app_original as core


class MonthlySponsorship(core.db.Model):
    __tablename__ = 'monthly_sponsorship'
    __table_args__ = (UniqueConstraint('month', 'page_key', name='uq_monthly_sponsorship_month_page'),)
    id = core.db.Column(core.db.Integer, primary_key=True)
    month = core.db.Column(core.db.String(7), nullable=False, index=True)
    page_key = core.db.Column(core.db.String(80), nullable=False, index=True)
    company_name = core.db.Column(core.db.String(160), nullable=False, default='')
    donor_name = core.db.Column(core.db.String(160), nullable=False, default='')
    memorial_one = core.db.Column(core.db.String(300), nullable=False, default='')
    memorial_two = core.db.Column(core.db.String(300), nullable=False, default='')
    contact_name = core.db.Column(core.db.String(160), nullable=False, default='')
    contact_phone = core.db.Column(core.db.String(80), nullable=False, default='')
    contact_email = core.db.Column(core.db.String(254), nullable=False, default='')
    amount_cents = core.db.Column(core.db.Integer, nullable=False, default=0)
    paid_cents = core.db.Column(core.db.Integer, nullable=False, default=0)
    status = core.db.Column(core.db.String(20), nullable=False, default='Reserved', index=True)
    notes = core.db.Column(core.db.Text, nullable=False, default='')
    logo_data = core.db.Column(core.db.LargeBinary, nullable=True)
    logo_mime = core.db.Column(core.db.String(80), nullable=False, default='')
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    @property
    def balance_cents(self):
        return max(0, self.amount_cents - self.paid_cents)


PAGE_SLOTS = (
    ('overview', 'Overview'), ('cases', 'Cases'), ('family_profile', 'Family profile'),
    ('applications', 'Applications'), ('online_application', 'Online application'),
    ('printed_application', 'Printed application'), ('tasks', 'Tasks'),
    ('supporters', 'Supporters'), ('communications', 'Communications'),
    ('fundraising', 'Fundraising'), ('collections', 'Collections'),
    ('expenses', 'Expenses'), ('approvals', 'Approvals'), ('payouts', 'Payouts'),
    ('reports', 'Reports'), ('operations', 'Operations'),
    ('organization_reports', 'Organization reports'),
    ('community_directories', 'Community directories'),
    ('people_access', 'People & access'), ('controls', 'Controls'),
)
PAGE_LABELS = dict(PAGE_SLOTS)
ENDPOINT_PAGE = {
    'dashboard': 'overview', 'families': 'cases', 'cases': 'cases', 'new_family': 'cases',
    'family_detail': 'family_profile', 'edit_family': 'family_profile',
    'family_print': 'family_profile', 'family_expense_report': 'family_profile',
    'applications': 'applications', 'request_application': 'applications',
    'application_review': 'applications', 'application_form': 'online_application',
    'application_submitted': 'online_application', 'print_application': 'printed_application',
    'print_blank_application': 'printed_application', 'tasks': 'tasks', 'task_detail': 'tasks',
    'supporters': 'supporters', 'supporter_detail': 'supporters', 'edit_contact': 'supporters',
    'communications': 'communications', 'fundraising': 'fundraising',
    'fundraising_detail': 'fundraising', 'collections': 'collections',
    'record_receipt': 'collections', 'expenses': 'expenses', 'approvals': 'approvals',
    'payouts': 'payouts', 'reports': 'reports', 'operations': 'operations',
    'operating_reports': 'organization_reports', 'community_directories': 'community_directories',
    'staff': 'people_access', 'people_access': 'people_access', 'controls': 'controls',
}
STATUSES = ('Reserved', 'Confirmed', 'Published', 'Expired')
MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}


def _month_now():
    return datetime.now(core.timezone.utc).astimezone(core.ZoneInfo('America/New_York')).strftime('%Y-%m')


def _money_cents(name):
    raw = request.form.get(name, '').strip() or '0'
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0 or value > 1_000_000 or value.as_tuple().exponent < -2:
            raise ValueError
        return int(value * 100)
    except (InvalidOperation, ValueError):
        abort(400, f'Enter a valid {name.replace("_", " ")} with up to two decimal places.')


def _field(name, limit):
    value = request.form.get(name, '').strip()
    if len(value) > limit:
        abort(400, f'{name.replace("_", " ").title()} is too long.')
    return value


def install(app):
    def require_admin():
        if app.config['DEMO']:
            return
        user_id = session.get('user_id')
        user = core.db.session.get(core.StaffUser, user_id) if user_id else None
        if user is None or user.role != 'organization_admin':
            abort(403, 'Organization administrator access is required.')

    def current_sponsorship(page_key=None, month=None):
        key = page_key or ENDPOINT_PAGE.get(request.endpoint)
        if not key:
            return None
        return core.db.session.scalar(select(MonthlySponsorship).where(
            MonthlySponsorship.month == (month or _month_now()),
            MonthlySponsorship.page_key == key, MonthlySponsorship.status == 'Published'))

    @app.context_processor
    def sponsor_context():
        return {'current_sponsor': current_sponsorship(), 'sponsorship_page_labels': PAGE_LABELS}

    @app.get('/sponsorships')
    def sponsorships():
        require_admin()
        month = request.args.get('month', _month_now()).strip()
        if not MONTH_RE.fullmatch(month):
            abort(400, 'Choose a valid sponsorship month.')
        records = core.db.session.scalars(select(MonthlySponsorship).where(
            MonthlySponsorship.month == month).order_by(MonthlySponsorship.page_key)).all()
        by_page = {row.page_key: row for row in records}
        totals = {'contracted': sum(row.amount_cents for row in records),
                  'paid': sum(row.paid_cents for row in records),
                  'published': sum(row.status == 'Published' for row in records),
                  'available': len(PAGE_SLOTS) - len(records)}
        return render_template('sponsorships.html', title='Monthly sponsorships', month=month,
                               page_slots=PAGE_SLOTS, by_page=by_page, totals=totals, statuses=STATUSES)

    @app.route('/sponsorships/<page_key>', methods=['GET', 'POST'])
    def sponsorship_edit(page_key):
        require_admin()
        if page_key not in PAGE_LABELS:
            abort(404)
        month = request.values.get('month', _month_now()).strip()
        if not MONTH_RE.fullmatch(month):
            abort(400, 'Choose a valid sponsorship month.')
        row = core.db.session.scalar(select(MonthlySponsorship).where(
            MonthlySponsorship.month == month, MonthlySponsorship.page_key == page_key))
        if request.method == 'POST':
            status = _field('status', 20)
            if status not in STATUSES:
                abort(400, 'Choose a valid sponsorship status.')
            email = _field('contact_email', 254).lower()
            if email and not EMAIL_RE.fullmatch(email):
                abort(400, 'Enter a valid contact email address.')
            if row is None:
                row = MonthlySponsorship(month=month, page_key=page_key)
                core.db.session.add(row)
            row.company_name, row.donor_name = _field('company_name', 160), _field('donor_name', 160)
            row.memorial_one, row.memorial_two = _field('memorial_one', 300), _field('memorial_two', 300)
            row.contact_name, row.contact_phone, row.contact_email = _field('contact_name', 160), _field('contact_phone', 80), email
            row.amount_cents, row.paid_cents = _money_cents('amount'), _money_cents('paid')
            if row.paid_cents > row.amount_cents:
                abort(400, 'The amount paid cannot exceed the sponsorship amount.')
            row.status, row.notes = status, _field('notes', 5000)
            logo = request.files.get('logo')
            if logo and logo.filename:
                data, mime = logo.read(2 * 1024 * 1024 + 1), (logo.mimetype or '').lower()
                if mime not in IMAGE_MIMES or not data or len(data) > 2 * 1024 * 1024:
                    abort(400, 'Upload a PNG, JPG, WebP, or GIF logo no larger than 2 MB.')
                row.logo_data, row.logo_mime = data, mime
            if request.form.get('remove_logo') == 'yes':
                row.logo_data, row.logo_mime = None, ''
            if status == 'Published' and (not row.company_name or not row.donor_name or not row.logo_data):
                abort(400, 'Company name, donor name, and company logo are required before publishing.')
            core.db.session.flush()
            user_id = session.get('user_id')
            user = core.db.session.get(core.StaffUser, user_id) if user_id else None
            core.db.session.add(core.Audit(actor=user.email if user else 'Demo user', action=f'Updated {month} sponsorship for {PAGE_LABELS[page_key]}'))
            core.db.session.commit()
            flash('Monthly sponsorship saved.', 'success')
            return redirect(url_for('sponsorships', month=month))
        return render_template('sponsorship_form.html', title='Edit monthly sponsorship', month=month,
                               page_key=page_key, page_label=PAGE_LABELS[page_key], sponsor=row, statuses=STATUSES)

    @app.post('/sponsorships/<int:sponsorship_id>/delete')
    def sponsorship_delete(sponsorship_id):
        require_admin()
        row = core.db.get_or_404(MonthlySponsorship, sponsorship_id)
        month = row.month
        core.db.session.delete(row)
        core.db.session.commit()
        flash('Monthly sponsorship removed. The page is available again.', 'success')
        return redirect(url_for('sponsorships', month=month))

    @app.get('/sponsorships/<int:sponsorship_id>/logo')
    def sponsorship_logo(sponsorship_id):
        row = core.db.get_or_404(MonthlySponsorship, sponsorship_id)
        if not row.logo_data or row.logo_mime not in IMAGE_MIMES:
            abort(404)
        return send_file(core.BytesIO(row.logo_data), mimetype=row.logo_mime, download_name=f'sponsor-{row.id}-logo')

    app.extensions['sponsorships'] = {'model': MonthlySponsorship, 'current': current_sponsorship, 'pages': PAGE_SLOTS}
