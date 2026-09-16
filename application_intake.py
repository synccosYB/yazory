import re
import secrets
from datetime import datetime, timezone
from html import escape

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import select

import app_original as core
from email_service import deliver


class AssistanceApplication(core.db.Model):
    __tablename__ = 'assistance_application'
    id = core.db.Column(core.db.Integer, primary_key=True)
    public_token = core.db.Column(core.db.String(96), nullable=False, unique=True, index=True)
    status = core.db.Column(core.db.String(30), nullable=False, default='Draft', index=True)
    recipient_email = core.db.Column(core.db.String(254), nullable=False, default='', index=True)
    applicant_name = core.db.Column(core.db.String(160), nullable=False, default='')
    preparer_name = core.db.Column(core.db.String(160), nullable=False, default='')
    preparer_role = core.db.Column(core.db.String(40), nullable=False, default='')
    data = core.db.Column(core.db.JSON, nullable=False, default=dict)
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    submitted_at = core.db.Column(core.db.DateTime, nullable=True)

    @property
    def number(self):
        return f'YA-{self.id:06d}' if self.id else 'YA-PENDING'


EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PUBLIC_ENDPOINTS = {'application_form', 'application_submitted'}


def _data_from_form(existing):
    data = dict(existing or {})
    keys = (
        'preparer_role', 'preparer_name', 'preparer_relationship', 'preparer_phone', 'preparer_email',
        'applicant_name', 'spouse_name', 'address', 'city', 'state', 'zip_code', 'phone', 'email',
        'children_count', 'married_children_count', 'father', 'father_in_law', 'family_rav',
        'weekday_shul', 'shabbos_shul', 'employment', 'spouse_employment', 'monthly_income',
        'housing', 'food', 'tuition', 'utilities', 'medical', 'debt_payments', 'other_expenses',
        'current_help', 'circumstances', 'requested_amount', 'requested_frequency', 'other_request',
    )
    for key in keys:
        if key in request.form:
            data[key] = request.form.get(key, '').strip()[:5000]
    data['assistance_types'] = request.form.getlist('assistance_types')
    data['certified'] = request.form.get('certified') == 'yes'
    return data


def install(app):
    # The core authentication guard predates this public application. Wrap it so
    # only these token-protected application pages bypass staff authentication;
    # CSRF protection remains active for every POST.
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
            if not EMAIL_RE.match(email):
                flash('Enter a valid email address.', 'error')
                return render_template('application_request.html', title='Send application')
            row = AssistanceApplication(public_token=secrets.token_urlsafe(36), recipient_email=email,
                                        applicant_name=applicant_name, data={'applicant_name': applicant_name})
            core.db.session.add(row)
            core.db.session.flush()
            base = app.config.get('APP_BASE_URL', '').rstrip('/')
            link = f"{base}{url_for('application_form', token=row.public_token)}"
            logo = f"{base}{url_for('static', filename='yazory-logo.png')}"
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
                    core.db.session.commit()
                    return redirect(url_for('application_submitted', token=token))
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

    @app.get('/applications/<int:application_id>/print')
    def print_application(application_id):
        row = core.db.get_or_404(AssistanceApplication, application_id)
        return render_template('application_print.html', title=f'Application {row.number}', application=row, data=row.data or {})

    @app.get('/applications/blank/print')
    def print_blank_application():
        return render_template('application_print.html', title='Blank family assistance application', application=None, data={})

    app.extensions['application_intake'] = {'model': AssistanceApplication}
