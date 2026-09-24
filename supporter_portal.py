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
from receipt_pdf import (build_abcharity_payment_pdf, build_donor_receipt_pdf,
                         build_pledge_acknowledgment_pdf)
from twilio_service import deliver_message, normalize_phone


class SupporterTicket(core.db.Model):
    __tablename__ = 'supporter_ticket'
    id = core.db.Column(core.db.Integer, primary_key=True)
    supporter_key = core.db.Column(core.db.String(200), nullable=False, index=True)
    contact_id = core.db.Column(core.db.Integer, core.db.ForeignKey('contact.id'), nullable=False)
    title = core.db.Column(core.db.String(160), nullable=False)
    request_text = core.db.Column(core.db.Text, nullable=False)
    preferred_method = core.db.Column(core.db.String(20), nullable=False)
    status = core.db.Column(core.db.String(20), nullable=False, default='Open')
    public_update = core.db.Column(core.db.Text, nullable=False, default='')
    delivery_status = core.db.Column(core.db.String(20), nullable=False, default='pending')
    created_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    contact = core.db.relationship('Contact')


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


def create_supporter_sms_signin_link(app, contact):
    """Issue a one-time portal link to a mobile number tied to one identity."""
    phone = normalize_phone(contact.cell_phone or contact.phone)
    if not contact.supporter_key:
        raise ValueError('This donor has no portal identity.')
    for row in core.db.session.scalars(select(core.Contact).where(
            core.Contact.supporter_key != '')).all():
        if row.supporter_key == contact.supporter_key:
            continue
        try:
            other_phone = normalize_phone(row.cell_phone or row.phone)
        except ValueError:
            continue
        if other_phone == phone:
            raise ValueError('This mobile number belongs to more than one donor account.')
    raw = secrets.token_urlsafe(32)
    core.db.session.add(SupporterLoginToken(
        supporter_key=contact.supporter_key, email='',
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=_utcnow() + timedelta(minutes=30)))
    base = app.config.get('APP_BASE_URL', '').rstrip('/')
    return phone, (base + url_for('supporter_login_link', token=raw) if base else
                   url_for('supporter_login_link', token=raw, _external=True))


def register_supporter_portal(app):
    def ensure_schema():
        SupporterLoginToken.__table__.create(core.db.engine, checkfirst=True)
        SupporterTicket.__table__.create(core.db.engine, checkfirst=True)

    app.extensions.setdefault('init_db_hooks', []).append(ensure_schema)
    if app.config.get('DEMO') or app.config.get('TESTING'):
        with app.app_context():
            ensure_schema()

    @app.route('/donor/login', methods=['GET', 'POST'])
    def supporter_login():
        if request.method == 'POST':
            email = (request.form.get('email') or '').strip().lower()[:254]
            app.extensions['consume_throttle'](
                'supporter_login_link', email, 3, 60 * 60)
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
                    'yi': 'אייער זיכערער יעזורו לאגאין לינק',
                    'he': 'קישור הכניסה המאובטח שלך ליעזורו',
                }.get(language, 'Your secure Yazory sign-in link')
                body = {
                    'yi': (f'שלום {supporter.name},\n\nעפנט אייער זיכערער יעזורו דאנאר אקאונט דא:\n'
                           f'{link}\n\nדער איינמאליגער לינק לויפט אפ נאך 30 מינוט.'),
                    'he': (f'שלום {supporter.name},\n\nפתחו כאן את חשבון התורם המאובטח שלכם ביעזורו:\n'
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
        charity_donations = core.db.session.scalars(select(core.CharityDonation).join(
            core.CharityDonor, core.CharityDonor.id == core.CharityDonation.donor_id
        ).where(core.CharityDonor.contact_id.in_(contact_ids)).order_by(
            core.CharityDonation.donation_time.desc())).all()
        donations = ([{'kind': 'Yazory', 'date': row.received_on, 'family': row.family,
                       'amount_cents': row.amount_cents,
                       'reference': row.reference or f'YZ-{row.id:06d}',
                       'url': url_for('supporter_portal_receipt', receipt_id=row.id)}
                      for row in receipts] +
                     [{'kind': 'ABCharity', 'date': row.donation_time.date(),
                       'family': next(c.family for c in contacts if c.id == row.donor.contact_id),
                       'amount_cents': row.amount_cents,
                       'reference': f'ABCharity #{row.external_id}',
                       'url': url_for('supporter_portal_abcharity_payment', donation_id=row.id)}
                      for row in charity_donations])
        donations.sort(key=lambda row: row['date'], reverse=True)
        payments = core.db.session.scalars(select(core.StripePayment).where(
            core.StripePayment.contact_id.in_(contact_ids)).order_by(
                core.StripePayment.created_at.desc())).all()
        tickets = core.db.session.scalars(select(SupporterTicket).where(
            SupporterTicket.supporter_key == key).order_by(SupporterTicket.id.desc())).all()
        return render_template('supporter_portal.html', title='My donor account',
                               supporter=contacts[0], contacts=contacts,
                               receipts=receipts, donations=donations,
                               payments=payments, tickets=tickets)

    @app.post('/donor/requests')
    def supporter_create_request():
        contact = _portal_contact(request.form.get('contact_id', type=int))
        title = (request.form.get('title') or '').strip()[:160]
        body = (request.form.get('request_text') or '').strip()[:5000]
        method = request.form.get('preferred_method')
        if not title or not body or method not in ('SMS', 'Email', 'Portal'):
            abort(400, 'Enter a request and choose how to receive updates.')
        if method == 'SMS' and not (contact.cell_phone or contact.phone):
            abort(400, 'A mobile number is needed for text updates.')
        if method == 'Email' and not contact.email:
            abort(400, 'An email address is needed for email updates.')
        ticket = SupporterTicket(supporter_key=contact.supporter_key,
            contact_id=contact.id, title=title, request_text=body,
            preferred_method=method)
        core.db.session.add(ticket)
        core.db.session.flush()
        core.db.session.add(core.Audit(actor=f'Donor: {contact.email or contact.name}',
            action=f'Created supporter request #{ticket.id}', family_id=contact.family_id))
        core.db.session.commit()
        flash('Your request was received.', 'success')
        return redirect(url_for('supporter_portal', _anchor='requests'))

    @app.get('/supporter-requests')
    def supporter_requests():
        user = core.db.session.get(core.StaffUser, session.get('user_id')) if session.get('user_id') else None
        if not user or user.role != 'organization_admin':
            abort(403)
        tickets = core.db.session.scalars(select(SupporterTicket).order_by(
            SupporterTicket.id.desc()).limit(200)).all()
        return render_template('supporter_requests.html', title='Supporter requests', tickets=tickets)

    @app.post('/supporter-requests/<int:ticket_id>')
    def supporter_request_update(ticket_id):
        user = core.db.session.get(core.StaffUser, session.get('user_id')) if session.get('user_id') else None
        if not user or user.role != 'organization_admin':
            abort(403)
        ticket = core.db.get_or_404(SupporterTicket, ticket_id)
        status = request.form.get('status')
        update = (request.form.get('public_update') or '').strip()[:1600]
        if status not in ('Open', 'In progress', 'Waiting', 'Resolved') or not update:
            abort(400, 'Choose a status and enter an update.')
        contact = ticket.contact
        notice = f'Yazory request #{ticket.id}: {status}. {update}'
        delivery = 'portal'
        if ticket.preferred_method == 'SMS':
            try:
                phone = normalize_phone(contact.cell_phone or contact.phone)
                if app.config.get('TESTING') or app.config.get('DEMO'):
                    delivery = 'preview'
                else:
                    _, error = deliver_message(app.config['TWILIO_ACCOUNT_SID'],
                        app.config['TWILIO_AUTH_TOKEN'], phone, notice, channel='sms',
                        sms_from=app.config['TWILIO_SMS_FROM'],
                        messaging_service_sid=app.config['TWILIO_MESSAGING_SERVICE_SID'])
                    delivery = 'failed' if error else 'sent'
            except ValueError:
                delivery = 'failed'
        elif ticket.preferred_method == 'Email':
            message = app.extensions['send_email']('supporter_request_update',
                contact.email, f'Yazory request #{ticket.id} update', notice,
                staff_user_id=user.id, family_id=contact.family_id)
            delivery = message.status
        ticket.status = status
        ticket.public_update = update
        ticket.delivery_status = delivery
        ticket.updated_at = _utcnow()
        core.db.session.add(core.Audit(actor=user.email,
            action=f'Updated supporter request #{ticket.id} ({delivery})', family_id=contact.family_id))
        core.db.session.commit()
        flash('Request updated.' if delivery not in ('failed', 'preview') else
              'Request updated in the portal; external delivery was not completed.',
              'success' if delivery not in ('failed', 'preview') else 'error')
        return redirect(url_for('supporter_requests'))

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
        if cents and contact.email:
            base = app.config.get('APP_BASE_URL', '').rstrip('/')
            link = (base + url_for('supporter_portal_pledge', contact_id=contact.id)
                    if base else url_for('supporter_portal_pledge', contact_id=contact.id, _external=True))
            app.extensions['send_email']('pledge_confirmation', contact.email,
                'Your Yazory pledge acknowledgment',
                f'Thank you for pledging ${cents / 100:,.2f} ({frequency}) '
                f'for {contact.family.name}.\n\n'
                f'Your pledge acknowledgment is available in your donor account: {link}\n\n'
                'A pledge is not a payment. A donation receipt is issued only after a donation is received.',
                family_id=contact.family_id)
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

    @app.get('/donor/abcharity/<int:donation_id>.pdf')
    def supporter_portal_abcharity_payment(donation_id):
        donation = core.db.get_or_404(core.CharityDonation, donation_id)
        if not donation.donor.contact_id:
            abort(403)
        contact = _portal_contact(donation.donor.contact_id)
        return send_file(build_abcharity_payment_pdf(donation, contact),
                         mimetype='application/pdf', as_attachment=True,
                         download_name=f'Yazory-ABCharity-{donation.external_id}.pdf')

    @app.get('/donor/pledges/<int:contact_id>.pdf')
    def supporter_portal_pledge(contact_id):
        contact = _portal_contact(contact_id)
        if contact.status != 'Pledged' or contact.monthly_cents <= 0:
            abort(404)
        return send_file(build_pledge_acknowledgment_pdf(contact), mimetype='application/pdf',
                         as_attachment=True, download_name=f'Yazory-pledge-{contact.id:06d}.pdf')

    @app.post('/donor/logout')
    def supporter_logout():
        language = session.get('language', 'en')
        session.clear()
        session['language'] = language
        return redirect(url_for('supporter_login'))

    return app
