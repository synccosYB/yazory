import re
import secrets
from datetime import datetime, timezone
from html import escape

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, select, text

import app_original as core
from email_service import deliver


class AssistanceApplication(core.db.Model):
    __tablename__ = 'assistance_application'
    id = core.db.Column(core.db.Integer, primary_key=True)
    public_token = core.db.Column(core.db.String(96), nullable=False, unique=True, index=True)
    status = core.db.Column(core.db.String(30), nullable=False, default='Draft', index=True)
    recipient_email = core.db.Column(core.db.String(254), nullable=False, default='', index=True)
    applicant_name = core.db.Column(core.db.String(160), nullable=False, default='')
    fund_name = core.db.Column(core.db.String(160), nullable=False, default='')
    preparer_name = core.db.Column(core.db.String(160), nullable=False, default='')
    preparer_role = core.db.Column(core.db.String(40), nullable=False, default='')
    data = core.db.Column(core.db.JSON, nullable=False, default=dict)
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    submitted_at = core.db.Column(core.db.DateTime, nullable=True)

    @property
    def number(self):
        return f'YA-{self.id:06d}' if self.id else 'YA-PENDING'


EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PUBLIC_ENDPOINTS = {'application_form', 'application_submitted', 'yazory_service_worker'}
REVIEW_STATUSES = ('Submitted', 'Missing information', 'Under review', 'Approved', 'Declined')
REVIEW_FIELDS = (
    ('Preparer role','preparer_role'),('Preparer name','preparer_name'),('Relationship to applicant','preparer_relationship'),
    ('Preparer phone','preparer_phone'),('Preparer email','preparer_email'),('Applicant / family name','applicant_name'),
    ('Spouse name','spouse_name'),('Address','address'),('City','city'),('State','state'),('ZIP code','zip_code'),
    ('Phone','phone'),('Email','email'),('Children at home','children_count'),('Married children','married_children_count'),
    ('Father','father'),('Father-in-law','father_in_law'),('Mother-in-law’s maiden family','mother_in_law_maiden_family'),
    ('In-law family / network','in_law_family_network'),('Kehillah / community','kehillah'),
    ('Family Rav','family_rav'),('Family Rav phone','family_rav_phone'),('Rav’s gabbai','rav_gabbai'),
    ('Rav’s gabbai phone','rav_gabbai_phone'),('Weekday shul','weekday_shul'),('Weekday shul Rav','weekday_shul_rav'),
    ('Weekday shul gabbai','weekday_shul_gabbai'),('Weekday shul gabbai phone','weekday_shul_gabbai_phone'),
    ('Same shul on weekdays and Shabbos','same_shul'),('Shabbos shul','shabbos_shul'),('Shabbos shul Rav','shabbos_shul_rav'),
    ('Shabbos shul gabbai','shabbos_shul_gabbai'),('Shabbos shul gabbai phone','shabbos_shul_gabbai_phone'),
    ('Applicant employment','employment'),('Spouse employment','spouse_employment'),
    ('Total monthly income','monthly_income'),('Housing','housing'),('Food','food'),('Tuition','tuition'),('Utilities','utilities'),
    ('Medical','medical'),('Debt payments','debt_payments'),('Other expenses','other_expenses'),('Current assistance','current_help'),
    ('Approximate amount needed','requested_amount'),('Frequency','requested_frequency'),
)


def _data_from_form(existing):
    data = dict(existing or {})
    keys = (
        'preparer_role', 'preparer_name', 'preparer_relationship', 'preparer_phone', 'preparer_email',
        'applicant_name', 'spouse_name', 'address', 'city', 'state', 'zip_code', 'phone', 'email',
        'children_count', 'married_children_count', 'father', 'father_in_law',
        'mother_in_law_maiden_family', 'in_law_family_network', 'kehillah', 'family_rav',
        'family_rav_phone', 'rav_gabbai', 'rav_gabbai_phone', 'weekday_shul',
        'weekday_shul_rav', 'weekday_shul_gabbai', 'weekday_shul_gabbai_phone', 'shabbos_shul',
        'shabbos_shul_rav', 'shabbos_shul_gabbai', 'shabbos_shul_gabbai_phone',
        'employment', 'spouse_employment', 'monthly_income',
        'housing', 'food', 'tuition', 'utilities', 'medical', 'debt_payments', 'other_expenses',
        'current_help', 'circumstances', 'requested_amount', 'requested_frequency', 'other_request',
    )
    for key in keys:
        if key in request.form:
            data[key] = request.form.get(key, '').strip()[:5000]
    data['same_shul'] = request.form.get('same_shul') == 'yes'
    if data['same_shul']:
        data['shabbos_shul'] = data.get('weekday_shul', '')
        data['shabbos_shul_rav'] = data.get('weekday_shul_rav', '')
        data['shabbos_shul_gabbai'] = data.get('weekday_shul_gabbai', '')
        data['shabbos_shul_gabbai_phone'] = data.get('weekday_shul_gabbai_phone', '')
    data['assistance_types'] = request.form.getlist('assistance_types')
    data['certified'] = request.form.get('certified') == 'yes'
    return data


def install(app):
    def migrate_application_fund_name():
        if not inspect(core.db.engine).has_table('assistance_application'):
            return
        columns = {column['name'] for column in inspect(core.db.engine).get_columns('assistance_application')}
        if 'fund_name' not in columns:
            core.db.session.execute(text("ALTER TABLE assistance_application ADD COLUMN fund_name VARCHAR(160) NOT NULL DEFAULT ''"))
        core.db.session.commit()

    app.extensions.setdefault('init_db_hooks', []).append(migrate_application_fund_name)
    guards = app.before_request_funcs.get(None, [])
    for index, guard in enumerate(list(guards)):
        if getattr(guard, '__name__', '') != 'security':
            continue
        def public_aware_security(guard=guard):
            if request.endpoint in PUBLIC_ENDPOINTS:
                if request.method == 'POST':
                    posted = request.form.get('csrf', '')
                    stored = session.get('csrf', '')
                    if not stored or not secrets.compare_digest(stored, posted):
                        abort(400, 'Your form expired. Reload the page and try again.')
                return None
            return guard()
        guards[index] = public_aware_security
        break

    @app.get('/applications')
    def applications():
        rows = core.db.session.scalars(select(AssistanceApplication).order_by(AssistanceApplication.id.desc())).all()
        return render_template('applications.html', title='Applications', applications=rows)

    @app.route('/applications/request', methods=['GET', 'POST'])
    def request_application():
        if request.method == 'POST':
            email = request.form.get('recipient_email', '').strip().lower()
            applicant_name = request.form.get('applicant_name', '').strip()[:160]
            fund_name = request.form.get('fund_name', '').strip()[:160]
            if not EMAIL_RE.match(email):
                flash('Enter a valid email address.', 'error')
                return render_template('application_request.html', title='Send application')
            if not fund_name:
                flash('Enter the sponsor קרן name.', 'error')
                return render_template('application_request.html', title='Send application')
            row = AssistanceApplication(public_token=secrets.token_urlsafe(36), recipient_email=email,
                                        applicant_name=applicant_name, fund_name=fund_name, status='Sent',
                                        data={'applicant_name': applicant_name, 'fund_name': fund_name})
            core.db.session.add(row)
            core.db.session.flush()
            base = app.config.get('APP_BASE_URL', '').rstrip('/')
            link = f"{base}{url_for('application_form', token=row.public_token)}"
            logo = f"{base}{url_for('static', filename='yazory-logo-corrected.png')}"
            subject = 'Yazory family assistance application'
            text = f'You have been asked to complete a Yazory family assistance application.\n\nOpen the application: {link}\n\nApplication: {row.number}'
            html = (f'<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto">'
                    f'<img src="{escape(logo)}" alt="Yazory" style="max-width:180px;height:auto">'
                    f'<h2>Family assistance application</h2><p>You have been asked to complete an application for family assistance.</p>'
                    f'<p><a href="{escape(link)}" style="display:inline-block;padding:12px 20px;background:#173f35;color:white;text-decoration:none;border-radius:8px">Open application</a></p>'
                    f'<p>Application <strong>{row.number}</strong></p></div>')
            provider_id, error = deliver(app.config.get('RESEND_API_KEY', ''), app.config.get('EMAIL_FROM', ''), email, subject, html, text)
            if error:
                core.db.session.rollback()
                flash(f'Application was not sent: {error}', 'error')
                return render_template('application_request.html', title='Send application')
            core.db.session.add(core.EmailMessage(kind='application_invitation', recipient=email, subject=subject,
                                                   text_body=text, status='sent', provider_id=provider_id or '',
                                                   sent_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            core.db.session.commit()
            flash(f'Application {row.number} sent to {email}.', 'success')
            return redirect(url_for('applications'))
        return render_template('application_request.html', title='Send application')

    @app.route('/apply/<token>', methods=['GET', 'POST'])
    def application_form(token):
        row = core.db.session.scalar(select(AssistanceApplication).where(AssistanceApplication.public_token == token))
        if row is None:
            abort(404)
        if row.status in ('Approved', 'Declined'):
            return redirect(url_for('application_submitted', token=token))
        if request.method == 'POST':
            data = _data_from_form(row.data)
            row.data = data
            row.applicant_name = data.get('applicant_name', '')[:160]
            row.preparer_name = data.get('preparer_name', '')[:160]
            row.preparer_role = data.get('preparer_role', '')[:40]
            action = request.form.get('action', 'save')
            if action == 'submit':
                if not row.applicant_name:
                    flash('Applicant name is required before submitting.', 'error')
                elif not data.get('certified'):
                    flash('Please confirm that the information is accurate before submitting.', 'error')
                else:
                    row.status = 'Submitted'
                    row.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    core.db.session.add(core.Audit(
                        actor=f'Applicant: {row.preparer_name or row.recipient_email}',
                        action=f'New application submitted: {row.number}'))
                    core.db.session.commit()
                    return redirect(url_for('application_submitted', token=token))
            else:
                row.status = 'In progress'
            core.db.session.commit()
            if action != 'submit':
                flash('Application saved. You can continue later from this same link.', 'success')
        return render_template('application_form_public.html', title='Family assistance application', application=row, data=row.data or {})

    @app.get('/apply/<token>/submitted')
    def application_submitted(token):
        row = core.db.session.scalar(select(AssistanceApplication).where(AssistanceApplication.public_token == token))
        if row is None:
            abort(404)
        return render_template('application_submitted.html', title='Application received', application=row)

    @app.get('/applications/<int:application_id>')
    def application_review(application_id):
        row = core.db.get_or_404(AssistanceApplication, application_id)
        return render_template('application_review.html', title=f'Review {row.number}', application=row,
                               data=row.data or {}, fields=REVIEW_FIELDS, statuses=REVIEW_STATUSES)

    @app.post('/applications/<int:application_id>/review')
    def application_review_action(application_id):
        row = core.db.get_or_404(AssistanceApplication, application_id)
        status = request.form.get('status', '').strip()
        if status not in REVIEW_STATUSES:
            abort(400, 'Invalid application status.')
        data = dict(row.data or {})
        data['review_note'] = request.form.get('review_note', '').strip()[:5000]
        row.data = data
        row.status = status
        core.db.session.commit()
        flash(f'{row.number} updated to {status}.', 'success')
        return redirect(url_for('application_review', application_id=row.id))

    @app.post('/applications/<int:application_id>/question')
    def application_requester_question(application_id):
        row = core.db.get_or_404(AssistanceApplication, application_id)
        if not EMAIL_RE.match(row.recipient_email or ''):
            abort(400, 'This application does not have a valid requester email address.')
        subject = request.form.get('subject', '').strip()[:300]
        question = request.form.get('message', '').strip()[:5000]
        if not subject or not question:
            flash('Enter a subject and message before sending.', 'error')
            return redirect(url_for('application_review', application_id=row.id,
                                    _anchor='requester-question'))
        staff_id = session.get('user_id')
        staff = core.db.session.get(core.StaffUser, staff_id) if staff_id else None
        body = f'{question}\n\nApplication: {row.number}'
        email = app.extensions['send_email'](
            'application_question', row.recipient_email, subject, body,
            staff_user_id=staff.id if staff else None)
        core.db.session.add(core.Audit(
            actor=staff.email if staff else 'Demo user',
            action=(f'Application question {"sent" if email.status in ("sent", "preview") else "failed"}: '
                    f'{row.number} to {row.recipient_email}')))
        core.db.session.commit()
        if email.status == 'failed':
            flash(f'Message could not be sent: {email.error}', 'error')
        else:
            flash(f'Question sent to {row.recipient_email}.', 'success')
        return redirect(url_for('application_review', application_id=row.id,
                                _anchor='requester-question'))

    @app.get('/applications/<int:application_id>/print')
    def print_application(application_id):
        row = core.db.get_or_404(AssistanceApplication, application_id)
        return render_template('application_print.html', title=f'Application {row.number}', application=row, data=row.data or {})

    @app.get('/applications/blank/print')
    def print_blank_application():
        return render_template('application_print.html', title='Blank family assistance application', application=None, data={})

    app.extensions['application_intake'] = {'model': AssistanceApplication}
