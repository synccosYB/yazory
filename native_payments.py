"""Native Yazory donation flow using Stripe Elements tokenization.

The application owns the checkout UI. Raw card details are entered into Stripe
Elements in the browser and never pass through or get stored by Yazory.
"""
from datetime import datetime, timezone

from flask import abort, current_app, redirect, render_template, request, session, url_for
from sqlalchemy import select

import app_original as core
from stripe_gateway import (
    construct_webhook_event,
    create_customer,
    create_payment_intent,
    create_subscription,
    retrieve_charge,
    retrieve_payment_intent,
)


class StripeSettlement(core.db.Model):
    """Actual processor economics for each successful Stripe charge."""
    __tablename__ = 'stripe_settlement'
    id = core.db.Column(core.db.Integer, primary_key=True)
    payment_id = core.db.Column(core.db.Integer, core.db.ForeignKey('stripe_payment.id'), nullable=False, index=True)
    stripe_charge_id = core.db.Column(core.db.String(255), nullable=False, default='', index=True)
    balance_transaction_id = core.db.Column(core.db.String(255), nullable=False, unique=True, index=True)
    gross_cents = core.db.Column(core.db.Integer, nullable=False, default=0)
    fee_cents = core.db.Column(core.db.Integer, nullable=False, default=0)
    net_cents = core.db.Column(core.db.Integer, nullable=False, default=0)
    currency = core.db.Column(core.db.String(3), nullable=False, default='usd')
    created_at = core.db.Column(core.db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    payment = core.db.relationship(
        'StripePayment',
        backref=core.db.backref('settlements', lazy=True, order_by='StripeSettlement.id'),
    )


def _value(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _authorized_contact(contact_id):
    contact = core.db.session.get(core.Contact, contact_id)
    if contact is None:
        abort(404)
    if current_app.config.get('DEMO'):
        return contact
    user = core.db.session.get(core.StaffUser, session.get('user_id'))
    if user is None or user.status != 'active' or user.role not in ('organization_admin', 'family_admin', 'fundraiser'):
        abort(403, 'You do not have access to collect this donation.')
    if user.role != 'organization_admin':
        assigned = core.db.session.scalar(select(core.FamilyAssignment.id).where(
            core.FamilyAssignment.staff_user_id == user.id,
            core.FamilyAssignment.family_id == contact.family_id,
        ))
        if not assigned:
            abort(403, 'You are not assigned to this family.')
    return contact


def _parse_amount(value):
    try:
        cents = round(float(value) * 100)
    except (TypeError, ValueError):
        cents = 0
    if cents < 100 or cents > 100000000:
        abort(400, 'Enter a donation between $1.00 and $1,000,000.00.')
    return cents


def _payment_for_event(event_type, obj):
    metadata = _value(obj, 'metadata', {}) or {}
    payment_id = metadata.get('yazory_payment_id') if isinstance(metadata, dict) else _value(metadata, 'yazory_payment_id', '')
    if payment_id:
        try:
            payment = core.db.session.get(core.StripePayment, int(payment_id))
            if payment:
                return payment
        except (TypeError, ValueError):
            pass
    payment_intent_id = _value(obj, 'id', '') if event_type.startswith('payment_intent.') else _value(obj, 'payment_intent', '')
    if payment_intent_id:
        payment = core.db.session.scalar(select(core.StripePayment).where(
            core.StripePayment.payment_intent_id == payment_intent_id))
        if payment:
            return payment
    subscription_id = _value(obj, 'subscription', '')
    if not subscription_id:
        parent = _value(obj, 'parent', {}) or {}
        details = _value(parent, 'subscription_details', {}) or {}
        subscription_id = _value(details, 'subscription', '')
    if subscription_id:
        return core.db.session.scalar(select(core.StripePayment).where(
            core.StripePayment.subscription_id == subscription_id))
    return None


def _record_settlement(payment, *, payment_intent_id='', charge_id=''):
    """Fetch Stripe's actual balance transaction and persist gross/fee/net."""
    secret = current_app.config['STRIPE_SECRET_KEY']
    charge = None
    if charge_id:
        charge = retrieve_charge(secret, charge_id)
    elif payment_intent_id:
        intent = retrieve_payment_intent(secret, payment_intent_id)
        charge = _value(intent, 'latest_charge')
        if isinstance(charge, str) and charge:
            charge = retrieve_charge(secret, charge)
    if not charge:
        return
    balance = _value(charge, 'balance_transaction')
    if isinstance(balance, str) and balance:
        return
    if not balance:
        return
    balance_id = _value(balance, 'id', '')
    if not balance_id or core.db.session.scalar(select(StripeSettlement.id).where(
            StripeSettlement.balance_transaction_id == balance_id)):
        return
    core.db.session.add(StripeSettlement(
        payment_id=payment.id,
        stripe_charge_id=_value(charge, 'id', '') or '',
        balance_transaction_id=balance_id,
        gross_cents=int(_value(balance, 'amount', payment.amount_cents) or 0),
        fee_cents=int(_value(balance, 'fee', 0) or 0),
        net_cents=int(_value(balance, 'net', 0) or 0),
        currency=(_value(balance, 'currency', payment.currency) or payment.currency).lower(),
    ))


def register_native_payments(app):
    """Replace every Checkout entry point with Yazory UI + Stripe Elements."""
    legacy_webhook = app.view_functions.get('stripe_webhook')

    def native_payment_submit(contact_id):
        contact = _authorized_contact(contact_id)
        if not app.config.get('STRIPE_SECRET_KEY') or not app.config.get('STRIPE_PUBLISHABLE_KEY'):
            return {'error': 'Stripe card processing is not configured.'}, 503
        amount_cents = _parse_amount(request.form.get('amount'))
        frequency = (request.form.get('frequency') or '').strip()
        if frequency not in core.PLEDGE_FREQUENCIES:
            return {'error': 'Choose a valid donation frequency.'}, 400
        payment_method_id = (request.form.get('payment_method_id') or '').strip()
        if not payment_method_id.startswith('pm_'):
            return {'error': 'The secure card token is missing. Re-enter the card and try again.'}, 400
        billing_name = (request.form.get('billing_name') or contact.name).strip()[:160]
        billing_email = (request.form.get('billing_email') or '').strip().lower()[:254]

        payment = core.StripePayment(
            contact_id=contact.id,
            family_id=contact.family_id,
            amount_cents=amount_cents,
            currency=app.config['STRIPE_CURRENCY'],
            frequency=frequency,
            status='creating',
        )
        core.db.session.add(payment)
        core.db.session.commit()
        metadata = {
            'yazory_payment_id': str(payment.id),
            'contact_id': str(contact.id),
            'family_id': str(contact.family_id),
            'amount_cents': str(amount_cents),
            'frequency': frequency,
        }
        try:
            if frequency == 'One time':
                intent = create_payment_intent(app.config['STRIPE_SECRET_KEY'], {
                    'amount': amount_cents,
                    'currency': app.config['STRIPE_CURRENCY'],
                    'payment_method': payment_method_id,
                    'payment_method_types': ['card'],
                    'confirm': True,
                    'description': 'Yazory donation',
                    'metadata': metadata,
                    'receipt_email': billing_email or None,
                }, f'yazory-native-payment-{payment.id}')
                payment.payment_intent_id = _value(intent, 'id', '') or ''
                payment.status = _value(intent, 'status', 'processing') or 'processing'
                client_secret = _value(intent, 'client_secret', '') or ''
            else:
                customer = create_customer(app.config['STRIPE_SECRET_KEY'], {
                    'name': billing_name or contact.name,
                    'email': billing_email or None,
                    'payment_method': payment_method_id,
                    'invoice_settings': {'default_payment_method': payment_method_id},
                    'metadata': metadata,
                }, f'yazory-native-customer-{payment.id}')
                payment.customer_id = _value(customer, 'id', '') or ''
                subscription = create_subscription(app.config['STRIPE_SECRET_KEY'], {
                    'customer': payment.customer_id,
                    'items': [{'price_data': {
                        'currency': app.config['STRIPE_CURRENCY'],
                        'product_data': {'name': 'Yazory donation'},
                        'unit_amount': amount_cents,
                        'recurring': {'interval': 'week' if frequency == 'Weekly' else 'month'},
                    }}],
                    'payment_behavior': 'default_incomplete',
                    'payment_settings': {'save_default_payment_method': 'on_subscription'},
                    'expand': ['latest_invoice.payment_intent'],
                    'metadata': metadata,
                }, f'yazory-native-subscription-{payment.id}')
                payment.subscription_id = _value(subscription, 'id', '') or ''
                latest_invoice = _value(subscription, 'latest_invoice', {}) or {}
                intent = _value(latest_invoice, 'payment_intent', {}) or {}
                payment.payment_intent_id = _value(intent, 'id', '') or ''
                payment.status = _value(subscription, 'status', 'incomplete') or 'incomplete'
                client_secret = _value(intent, 'client_secret', '') or ''
            core.db.session.commit()
        except Exception as exc:
            core.db.session.rollback()
            payment = core.db.session.get(core.StripePayment, payment.id)
            if payment:
                payment.status = 'failed'
                core.db.session.commit()
            app.logger.exception('Native Stripe payment creation failed')
            return {'error': getattr(exc, 'user_message', None) or 'Stripe could not process the card. Please check the card details and try again.'}, 502

        return {
            'payment_id': payment.id,
            'status': payment.status,
            'client_secret': client_secret,
            'success_url': url_for('native_payment_success', payment_id=payment.id),
        }

    def native_payment_success(payment_id):
        payment = core.db.session.get(core.StripePayment, payment_id)
        if payment is None:
            abort(404)
        _authorized_contact(payment.contact_id)
        return render_template('stripe_result.html', title='Donation received', success=True, payment=payment)

    def legacy_checkout_redirect(contact_id):
        _authorized_contact(contact_id)
        return redirect(url_for('supporter_donation', contact_id=contact_id), code=303)

    def wrapped_webhook():
        event = None
        try:
            if app.config.get('STRIPE_WEBHOOK_SECRET'):
                event = construct_webhook_event(
                    request.get_data(),
                    request.headers.get('Stripe-Signature', ''),
                    app.config['STRIPE_WEBHOOK_SECRET'],
                )
        except Exception:
            event = None
        response = legacy_webhook() if legacy_webhook else ({'received': True}, 200)
        if not event:
            return response
        event_type = _value(event, 'type', '') or ''
        obj = _value(_value(event, 'data', {}) or {}, 'object', {}) or {}
        payment = _payment_for_event(event_type, obj)
        if not payment:
            return response
        try:
            if event_type == 'payment_intent.succeeded':
                payment.payment_intent_id = _value(obj, 'id', payment.payment_intent_id) or payment.payment_intent_id
                payment.status = 'paid'
                payment.completed_at = payment.completed_at or datetime.now(timezone.utc)
                if payment.frequency == 'One time' and payment.successful_charges == 0:
                    payment.successful_charges = 1
                    if not core.db.session.scalar(select(core.Receipt.id).where(
                            core.Receipt.reference == payment.payment_intent_id)):
                        core.db.session.add(core.Receipt(
                            contact_id=payment.contact_id,
                            family_id=payment.family_id,
                            amount_cents=payment.amount_cents,
                            received_on=datetime.now(timezone.utc).date(),
                            reference=payment.payment_intent_id,
                            note='Stripe card payment',
                        ))
                _record_settlement(
                    payment,
                    payment_intent_id=payment.payment_intent_id,
                    charge_id=_value(obj, 'latest_charge', '') or '',
                )
            elif event_type == 'invoice.paid':
                payment.status = 'active'
                _record_settlement(
                    payment,
                    payment_intent_id=_value(obj, 'payment_intent', '') or '',
                    charge_id=_value(obj, 'charge', '') or '',
                )
            core.db.session.commit()
        except Exception:
            core.db.session.rollback()
            app.logger.exception('Could not store Stripe processor fee details')
        return response

    app.add_url_rule('/supporters/<int:contact_id>/native-payment', 'native_payment_submit', native_payment_submit, methods=['POST'])
    app.add_url_rule('/stripe/native-success/<int:payment_id>', 'native_payment_success', native_payment_success, methods=['GET'])
    if 'embedded_checkout_session' in app.view_functions:
        app.view_functions['embedded_checkout_session'] = native_payment_submit
    if 'stripe_checkout' in app.view_functions:
        app.view_functions['stripe_checkout'] = legacy_checkout_redirect
    if legacy_webhook:
        app.view_functions['stripe_webhook'] = wrapped_webhook
    return app
