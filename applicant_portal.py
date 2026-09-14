"""Private applicant portal and case-scoped two-way messaging."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import select

import app_original as core


class ApplicantLoginToken(core.db.Model):
    __tablename__ = 'applicant_login_token'
    id = core.db.Column(core.db.Integer, primary_key=True)
    family_id = core.db.Column(core.db.Integer, core.db.ForeignKey('family.id'), nullable=False, index=True)
    email = core.db.Column(core.db.String(254), nullable=False, index=True)
    token_hash = core.db.Column(core.db.String(64), nullable=False, unique=True, index=True)
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: _utcnow())
    expires_at = core.db.Column(core.db.DateTime, nullable=False)
    used_at = core.db.Column(core.db.DateTime, nullable=True)


class ApplicantMessage(core.db.Model):
    __tablename__ = 'applicant_message'
    id = core.db.Column(core.db.Integer, primary_key=True)
    family_id = core.db.Column(core.db.Integer, core.db.ForeignKey('family.id'), nullable=False, index=True)
    staff_user_id = core.db.Column(core.db.Integer, core.db.ForeignKey('staff_user.id'), nullable=True, index=True)
    direction = core.db.Column(core.db.String(20), nullable=False, index=True)
    status = core.db.Column(core.db.String(20), nullable=False, default='handled', index=True)
    body = core.db.Column(core.db.Text, nullable=False)
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: _utcnow(), index=True)
    family = core.db.relationship('Family')
    staff_user = core.db.relationship('StaffUser')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _family_for_staff(family_id):
    family = core.db.get_or_404(core.Family, family_id)
    user = core.db.session.get(core.StaffUser, session.get('user_id'))
    if not user or user.role not in ('organization_admin', 'family_admin', 'office_employee'):
        abort(403)
    if user.role != 'organization_admin' and not core.db.session.scalar(select(
            core.FamilyAssignment.id).where(
                core.FamilyAssignment.staff_user_id == user.id,
                core.FamilyAssignment.family_id == family_id)):
        abort(403, 'You are not assigned to this family.')
    return family, user


def _portal_family():
    family_id = session.get('applicant_family_id')
    family = core.db.session.get(core.Family, family_id) if family_id else None
    if not family:
        session.pop('applicant_family_id', None)
    return family


def register_applicant_portal(app):
    def ensure_schema():
        ApplicantLoginToken.__table__.create(core.db.engine, checkfirst=True)
        ApplicantMessage.__table__.create(core.db.engine, checkfirst=True)
        columns = {column['name'] for column in core.inspect(
            core.db.engine).get_columns('applicant_message')}
        if 'status' not in columns:
            core.db.session.execute(core.text(
                "ALTER TABLE applicant_message ADD COLUMN status "
                "VARCHAR(20) NOT NULL DEFAULT 'handled'"))
            core.db.session.commit()

    app.extensions.setdefault('init_db_hooks', []).append(ensure_schema)
    if app.config.get('DEMO') or app.config.get('TESTING'):
        with app.app_context():
            ensure_schema()

    @app.route('/applicant/login', methods=['GET', 'POST'])
    def applicant_login():
        if request.method == 'POST':
            email = (request.form.get('email') or '').strip().lower()[:254]
            app.extensions['consume_throttle']('applicant_login_link', email, 3, 60 * 60)
            families = core.db.session.scalars(select(core.Family).where(
                core.db.func.lower(core.Family.email) == email).order_by(core.Family.id)).all() if email else []
            # Never guess when one address is attached to multiple cases.
            if len(families) == 1:
                family = families[0]
                raw = secrets.token_urlsafe(32)
                core.db.session.add(ApplicantLoginToken(
                    family_id=family.id, email=email,
                    token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                    expires_at=_utcnow() + timedelta(minutes=30)))
                base = app.config.get('APP_BASE_URL', '').rstrip('/')
                path = url_for('applicant_login_link', token=raw)
                link = base + path if base else url_for('applicant_login_link', token=raw, _external=True)
                app.extensions['send_email'](
                    'applicant_login', email, 'Your secure Yazory applicant portal link',
                    f'Hello {family.name},\n\nOpen your private Yazory applicant portal here:\n{link}\n\nThis one-time link expires after 30 minutes.',
                    family_id=family.id)
                core.db.session.commit()
            flash('If that email belongs to an applicant, a secure sign-in link was sent.', 'success')
            return redirect(url_for('applicant_login'))
        return render_template('applicant_login.html', title='Applicant sign in')

    @app.get('/applicant/login/<token>')
    def applicant_login_link(token):
        record = core.db.session.scalar(select(ApplicantLoginToken).where(
            ApplicantLoginToken.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            ApplicantLoginToken.used_at.is_(None), ApplicantLoginToken.expires_at > _utcnow()))
        if not record:
            abort(400, 'This sign-in link has expired or was already used.')
        record.used_at = _utcnow()
        language = session.get('language', 'en')
        csrf = session.get('csrf') or secrets.token_hex(32)
        session.clear()
        session.update(language=language, csrf=csrf,
                       applicant_family_id=record.family_id, permanent=True)
        core.db.session.commit()
        return redirect(url_for('applicant_portal'))

    @app.get('/applicant')
    def applicant_portal():
        family = _portal_family()
        if not family:
            return redirect(url_for('applicant_login'))
        messages = core.db.session.scalars(select(ApplicantMessage).where(
            ApplicantMessage.family_id == family.id).order_by(
                ApplicantMessage.created_at, ApplicantMessage.id)).all()
        return render_template('applicant_portal.html', title='My Yazory portal',
                               family=family, messages=messages)

    @app.post('/applicant/messages')
    def applicant_send_message():
        family = _portal_family()
        if not family:
            return redirect(url_for('applicant_login'))
        body = (request.form.get('body') or '').strip()[:5000]
        if not body:
            abort(400, 'Enter a message.')
        core.db.session.add(ApplicantMessage(
            family_id=family.id, direction='applicant', status='unread', body=body))
        staff = core.db.session.scalars(select(core.StaffUser).join(
            core.FamilyAssignment).where(
                core.FamilyAssignment.family_id == family.id,
                core.StaffUser.status == 'active',
                core.StaffUser.role.in_(('family_admin', 'office_employee')))).all()
        staff_url = (app.config.get('APP_BASE_URL', '').rstrip('/') +
                     url_for('staff_applicant_messages', family_id=family.id))
        for user in staff:
            app.extensions['send_email'](
                'applicant_message_staff_notice', user.email,
                f'New applicant message: {family.name}',
                f'{family.name} sent a new private portal message.\n\nOpen the conversation:\n{staff_url}',
                staff_user_id=user.id, family_id=family.id)
        core.db.session.add(core.Audit(actor=f'Applicant: {family.email}',
                                      action='Applicant sent portal message', family_id=family.id))
        core.db.session.commit()
        flash('Your message was sent to Yazory.', 'success')
        return redirect(url_for('applicant_portal'))

    @app.post('/applicant/logout')
    def applicant_logout():
        language = session.get('language', 'en')
        session.clear()
        session['language'] = language
        return redirect(url_for('applicant_login'))

    @app.get('/families/<int:family_id>/messages')
    def staff_applicant_messages(family_id):
        family, _ = _family_for_staff(family_id)
        messages = core.db.session.scalars(select(ApplicantMessage).where(
            ApplicantMessage.family_id == family.id).order_by(
                ApplicantMessage.created_at, ApplicantMessage.id)).all()
        return render_template('applicant_messages.html', title='Applicant messages',
                               family=family, messages=messages)

    @app.post('/families/<int:family_id>/messages')
    def staff_send_applicant_message(family_id):
        family, user = _family_for_staff(family_id)
        if not family.email:
            abort(400, 'Enter the applicant email address first.')
        body = (request.form.get('body') or '').strip()[:5000]
        if not body:
            abort(400, 'Enter a message.')
        core.db.session.add(ApplicantMessage(
            family_id=family.id, staff_user_id=user.id,
            direction='staff', status='sent', body=body))
        portal_url = app.config.get('APP_BASE_URL', '').rstrip('/') + url_for('applicant_portal')
        app.extensions['send_email'](
            'applicant_portal_message', family.email,
            'You have a new private message from Yazory',
            f'Hello {family.name},\n\nYazory sent you a new private message. Sign in to read and reply:\n{portal_url}',
            staff_user_id=user.id, family_id=family.id)
        core.db.session.add(core.Audit(actor=user.email,
                                      action='Sent applicant portal message', family_id=family.id))
        core.db.session.commit()
        flash('Message sent to the applicant portal.', 'success')
        return redirect(url_for('staff_applicant_messages', family_id=family.id))

    @app.post('/communications/applicant-messages/<int:message_id>/handled')
    def handle_applicant_message(message_id):
        message = core.db.get_or_404(ApplicantMessage, message_id)
        _family_for_staff(message.family_id)
        if message.direction != 'applicant':
            abort(404)
        message.status = 'handled'
        core.db.session.commit()
        flash('Applicant message marked as handled.', 'success')
        return redirect(url_for('communications', _anchor='applicant-messages'))

    return app
