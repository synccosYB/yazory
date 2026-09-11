"""Passwordless supporter account spanning every case for one real donor."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import func, select, text, inspect

import app_original as core
from stripe_gateway import create_billing_portal_session
from receipt_pdf import build_donor_receipt_pdf


class SupporterLoginToken(core.db.Model):
    __tablename__ = 'supporter_login_token'
    id = core.db.Column(core.db.Integer, primary_key=True)
    supporter_key = core.db.Column(core.db.String(200), nullable=False, index=True)
    email = core.db.Column(core.db.String(254), nullable=False, index=True)
    token_hash = core.db.Column(core.db.String(64), nullable=False, unique=True, index=True)
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = core.db.Column(core.db.DateTime, nullable=False)
    used_at = core.db.Column(core.db.DateTime, nullable=True)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _portal_contact(contact_id):
    contact = core.db.session.get(core.Contact, contact_id)
    key = session.get('supporter_key', '')
    if not contact or not key or not contact.supporter_key or not hmac.compare_digest(contact.supporter_key, key):
        abort(403, 'This supporter record is not part of your account.')
    return contact


def register_supporter_portal(app):
    def ensure_schema():
        SupporterLoginToken.__table__.create(core.db.engine, checkfirst=True)

    app.extensions.setdefault('init_db_hooks', []).append(ensure_schema)
    if app.config.get('DEMO') or app.config.get('TESTING'):
        with app.app_context():
            ensure_schema()

    @app.route('/donor/login', methods=['GET', 'POST'])
    def supporter_login():
        if request.method == 'POST':
            email = (request.form.get('email') or '').strip().lower()[:254]
            contacts = core.db.session.scalars(select(core.Contact).where(
                func.lower(core.Contact.email) == email,
                core.Contact.supporter_key != '',
            ).order_by(core.Contact.id)).all() if email else []
            # One email can only open one real-person identity. If legacy data has
            # conflicting identities, do not guess and accidentally disclose both.
            keys = {row.supporter_key for row in contacts}
            if len(keys) == 1:
                supporter = contacts[0]
                raw = secrets.token_urlsafe(32)
                core.db.session.add(SupporterLoginToken(
                    supporter_key=supporter.supporter_key,
                    email=email,
                    token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                    expires_at=_utcnow() + timedelta(minutes=30),
                ))
                base = app.config.get('APP_BASE_URL', '').rstrip('/')
                link = (base + url_for('supporter_login_link', token=raw)) if base else url_for(
                    'supporter_login_link', token=raw, _external=True)
                language = session.get('language', 'en')
                subject = {
                    'yi': 'אייער זיכערער יעזורי לאגאין לינק',
                    'he': 'קישור הכניסה המאובטח שלך ליעזורי',
                }.get(language, 'Your secure Yazory sign-in link')
                body = {
                    'yi': (f'שלום {supporter.name},\n\nעפנט אייער זיכערער יעזורי דאנאר אקאונט דא:\n'
                           f'{link}\n\nדער איינמאליגער לינק לויפט אפ נאך 30 מינוט.'),
                    'he': (f'שלום {supporter.name},\n\nפתחו כאן את חשבון התורם המאובטח שלכם ביעזורי:\n'
                           f'{link}\n\nהקישור החד־פעמי יפוג לאחר 30 דקות.'),
                }.get(language, (f'Hello {supporter.name},\n\nOpen your secure Yazory donor account here:\n'
                                 f'{link}\n\nThis one-time link expires in 30 minutes.'))
                app.extensions['send_email'](
                    'supporter_login', email, subject, body,
                    family_id=supporter.family_id)
                core.db.session.commit()
            flash('If that email belongs to a donor account, a secure sign-in link was sent.', 'success')
            return redirect(url_for('supporter_login'))
        return render_template('supporter_login.html', title='Donor sign in')

    @app.get('/donor/login/<token>')
    def supporter_login_link(token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        record = core.db.session.scalar(select(SupporterLoginToken).where(
            SupporterLoginToken.token_hash == digest,
            SupporterLoginToken.used_at.is_(None),
            SupporterLoginToken.expires_at > _utcnow(),
        ))
        if not record:
            abort(400, 'This sign-in link has expired or was already used.')
        record.used_at = _utcnow()
        language = session.get('language', 'en')
        csrf = session.get('csrf') or secrets.token_hex(32)
        session.clear()
        session['language'] = language
        session['csrf'] = csrf
        session['supporter_key'] = record.supporter_key
        session.permanent = True
        core.db.session.commit()
        return redirect(url_for('supporter_portal'))

    @app.get('/donor')
    def supporter_portal():
        key = session.get('supporter_key', '')
        if not key:
            return redirect(url_for('supporter_login'))
        contacts = core.db.session.scalars(select(core.Contact).where(
            core.Contact.supporter_key == key).order_by(core.Contact.family_id, core.Contact.id)).all()
        if not contacts:
            session.pop('supporter_key', None)
            return redirect(url_for('supporter_login'))
        contact_ids = [row.id for row in contacts]
        receipts = core.db.session.scalars(select(core.Receipt).where(
            core.Receipt.contact_id.in_(contact_ids)).order_by(
                core.Receipt.received_on.desc(), core.Receipt.id.desc())).all()
        payments = core.db.session.scalars(select(core.StripePayment).where(
            core.StripePayment.contact_id.in_(contact_ids)).order_by(
                core.StripePayment.created_at.desc())).all()
        return render_template('supporter_portal.html', title='My donor account',
                               supporter=contacts[0], contacts=contacts,
                               receipts=receipts, payments=payments)

    @app.post('/donor/pledges/<int:contact_id>')
    def supporter_portal_update_pledge(contact_id):
        contact = _portal_contact(contact_id)
        frequency = (request.form.get('frequency') or '').strip()
        if frequency not in core.PLEDGE_FREQUENCIES:
            abort(400, 'Choose a valid donation frequency.')
        try:
            entered = Decimal((request.form.get('amount') or '').strip())
            if not entered.is_finite() or entered < 0 or entered > 1000000 or entered.as_tuple().exponent < -2:
                raise ValueError
            cents = int(entered * 100)
        except (InvalidOperation, ValueError):
            abort(400, 'Enter a valid pledge amount.')
        contact.monthly_cents = cents
        contact.pledge_frequency = frequency
        contact.status = 'Pledged' if cents else 'Paused'
        core.db.session.add(core.Audit(actor=f'Donor: {contact.email}',
            action='Donor updated pledge', family_id=contact.family_id))
        core.db.session.commit()
        flash('Your pledge was updated.', 'success')
        return redirect(url_for('supporter_portal'))

    @app.get('/donor/donate/<int:contact_id>')
    def supporter_portal_donate(contact_id):
        contact = _portal_contact(contact_id)
        return render_template('supporter_donation_checkout.html', title='Donation checkout',
            supporter=contact, donor_portal=True,
            default_amount=contact.monthly_cents / 100 if contact.monthly_cents >= 100 else 1,
            default_frequency='One time',
            stripe_publishable_key=app.config['STRIPE_PUBLISHABLE_KEY'])

    @app.get('/donor/payments/<int:payment_id>/manage')
    def supporter_portal_manage_payment(payment_id):
        payment = core.db.get_or_404(core.StripePayment, payment_id)
        _portal_contact(payment.contact_id)
        if not payment.subscription_id or not payment.customer_id:
            flash('This donation does not have an active recurring billing account.', 'error')
            return redirect(url_for('supporter_portal'))
        try:
            portal = create_billing_portal_session(app.config['STRIPE_SECRET_KEY'],
                payment.customer_id,
                app.config.get('APP_BASE_URL', '').rstrip('/') + url_for('supporter_portal'))
        except Exception as exc:
            app.logger.exception('Could not open donor billing portal')
            flash(getattr(exc, 'user_message', None) or
                  'Stripe could not open recurring-donation management.', 'error')
            return redirect(url_for('supporter_portal'))
        url = portal.get('url', '') if isinstance(portal, dict) else getattr(portal, 'url', '')
        return redirect(url, code=303)

    @app.get('/donor/receipts/<int:receipt_id>.pdf')
    def supporter_portal_receipt(receipt_id):
        receipt = core.db.get_or_404(core.Receipt, receipt_id)
        _portal_contact(receipt.contact_id)
        return send_file(build_donor_receipt_pdf(receipt), mimetype='application/pdf',
                         as_attachment=True, download_name=f'Yazory-receipt-{receipt.id:06d}.pdf')

    @app.post('/donor/logout')
    def supporter_logout():
        language = session.get('language', 'en')
        session.clear()
        session['language'] = language
        return redirect(url_for('supporter_login'))

    return app
