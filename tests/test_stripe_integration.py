import app as app_module
import native_payments as native_module
from app import (Contact, Expense, Family, Receipt, StripeEvent, StripePayment,
                 StripeRecipient, StripeTransfer, create_app, db)
from native_payments import StripeSettlement


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def make_app():
    return create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'stripe-tests',
        'STRIPE_SECRET_KEY': 'sk_test_yazory',
        'STRIPE_PUBLISHABLE_KEY': 'pk_test_yazory',
        'STRIPE_WEBHOOK_SECRET': 'whsec_yazory',
        'APP_BASE_URL': 'https://yazory.example',
    })


def test_native_one_time_payment_and_fee_settlement(monkeypatch):
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact = db.session.scalar(db.select(Contact))
        contact_id = contact.id

    page = client.get(f'/supporters/{contact_id}/donation').text
    assert 'card-element' in page
    assert 'Process donation' in page
    assert 'initEmbeddedCheckout' not in page

    monkeypatch.setattr(native_module, 'create_payment_intent', lambda *_args, **_kwargs: {
        'id': 'pi_native_1',
        'status': 'requires_action',
        'client_secret': 'pi_native_1_secret_test',
    })

    response = client.post(f'/supporters/{contact_id}/embedded-checkout-session', data={
        'csrf': csrf(client),
        'amount': '18.00',
        'frequency': 'One time',
        'billing_name': 'Test Donor',
        'billing_email': 'donor@example.test',
        'payment_method_id': 'pm_test_1',
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body['client_secret'] == 'pi_native_1_secret_test'

    with app.app_context():
        payment = db.session.scalar(db.select(StripePayment))
        assert payment.payment_intent_id == 'pi_native_1'
        payment_id = payment.id

    monkeypatch.setattr(native_module, 'retrieve_charge', lambda *_args, **_kwargs: {
        'id': 'ch_native_1',
        'balance_transaction': {
            'id': 'txn_native_1',
            'amount': 1800,
            'fee': 82,
            'net': 1718,
            'currency': 'usd',
        },
    })
    event = {
        'id': 'evt_native_1',
        'type': 'payment_intent.succeeded',
        'data': {'object': {
            'id': 'pi_native_1',
            'latest_charge': 'ch_native_1',
            'metadata': {'yazory_payment_id': str(payment_id)},
        }},
    }
    monkeypatch.setattr(native_module, 'construct_webhook_event', lambda *_args: event)
    monkeypatch.setattr(app_module, 'construct_webhook_event', lambda *_args: event)

    webhook_client = app.test_client()
    response = webhook_client.post('/stripe/webhook', data=b'{}',
                                   headers={'Stripe-Signature': 'test'})
    assert response.status_code == 200

    with app.app_context():
        payment = db.session.get(StripePayment, payment_id)
        settlement = db.session.scalar(db.select(StripeSettlement))
        assert payment.status == 'paid'
        assert payment.successful_charges == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(Receipt)) == 1
        assert settlement.gross_cents == 1800
        assert settlement.fee_cents == 82
        assert settlement.net_cents == 1718


def test_native_monthly_subscription_returns_invoice_payment_secret(monkeypatch):
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact_id = db.session.scalar(db.select(Contact.id))

    monkeypatch.setattr(native_module, 'create_customer', lambda *_args, **_kwargs: {
        'id': 'cus_native_1',
    })
    monkeypatch.setattr(native_module, 'create_subscription', lambda *_args, **_kwargs: {
        'id': 'sub_native_1',
        'status': 'incomplete',
        'latest_invoice': {
            'payment_intent': {
                'id': 'pi_subscription_1',
                'client_secret': 'pi_subscription_1_secret_test',
            },
        },
    })

    response = client.post(f'/supporters/{contact_id}/embedded-checkout-session', data={
        'csrf': csrf(client),
        'amount': '25.00',
        'frequency': 'Monthly',
        'billing_name': 'Recurring Donor',
        'billing_email': 'monthly@example.test',
        'payment_method_id': 'pm_test_monthly',
    })
    assert response.status_code == 200
    assert response.get_json()['client_secret'] == 'pi_subscription_1_secret_test'

    with app.app_context():
        payment = db.session.scalar(db.select(StripePayment))
        assert payment.subscription_id == 'sub_native_1'
        assert payment.customer_id == 'cus_native_1'
        assert payment.payment_intent_id == 'pi_subscription_1'
        assert payment.frequency == 'Monthly'


def test_native_checkout_rejects_missing_card_token():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact_id = db.session.scalar(db.select(Contact.id))
    response = client.post(f'/supporters/{contact_id}/embedded-checkout-session', data={
        'csrf': csrf(client), 'amount': '18.00', 'frequency': 'One time'})
    assert response.status_code == 400
    assert 'secure card token is missing' in response.get_json()['error']


def test_zero_pledge_defaults_to_valid_one_dollar_native_form():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact = db.session.scalar(db.select(Contact))
        contact.monthly_cents = 0
        db.session.commit()
        contact_id = contact.id
    page = client.get(f'/supporters/{contact_id}/donation').text
    assert 'value="1.00"' in page
    assert 'One time' in page


def test_connect_onboarding_and_approved_expense_transfer(monkeypatch):
    app = make_app()
    client = app.test_client()
    monkeypatch.setattr(app_module, 'create_connected_account',
                        lambda *_args: {'id': 'acct_recipient_1'})
    monkeypatch.setattr(app_module, 'create_account_link',
                        lambda *_args: {'url': 'https://connect.stripe.test/onboard'})
    monkeypatch.setattr(app_module, 'retrieve_connected_account',
                        lambda *_args: {'details_submitted': True, 'payouts_enabled': True})
    monkeypatch.setattr(app_module, 'create_transfer',
                        lambda *_args: {'id': 'tr_yazory_1'})
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status = 'Active'
        expense = Expense(family_id=family.id, category='Groceries', payee='Market',
                          amount_cents=2500, month='2026-09', status='Approved')
        db.session.add(expense)
        db.session.commit()
        family_id, expense_id = family.id, expense.id

    response = client.post('/payouts/recipients', data={
        'csrf': csrf(client), 'kind': 'family', 'family_id': family_id,
        'email': 'recipient@example.test'})
    assert response.status_code == 302
    with app.app_context():
        recipient = db.session.scalar(db.select(StripeRecipient))
        recipient_id = recipient.id
        assert recipient.stripe_account_id == 'acct_recipient_1'
    response = client.get(f'/payouts/recipients/{recipient_id}/return')
    assert response.status_code == 302
    response = client.post(f'/expenses/{expense_id}/stripe-transfer', data={
        'csrf': csrf(client), 'recipient_id': recipient_id})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Expense, expense_id).payment_reference == 'tr_yazory_1'
        assert db.session.get(Expense, expense_id).status == 'Paid'
        assert db.session.scalar(db.select(db.func.count()).select_from(StripeTransfer)) == 1
    assert client.post(f'/expenses/{expense_id}/stripe-transfer', data={
        'csrf': csrf(client), 'recipient_id': recipient_id}).status_code == 400


def test_unverified_recipient_cannot_receive_transfer():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        expense = Expense(family_id=family.id, category='Groceries', payee='Market',
                          amount_cents=2500, month='2026-09', status='Approved')
        recipient = StripeRecipient(kind='family', recipient_key=str(family.id),
            family_id=family.id, name=family.name, email='recipient@example.test',
            stripe_account_id='acct_not_ready')
        db.session.add_all([expense, recipient])
        db.session.commit()
        expense_id, recipient_id = expense.id, recipient.id
    assert client.post(f'/expenses/{expense_id}/stripe-transfer', data={
        'csrf': csrf(client), 'recipient_id': recipient_id}).status_code == 400
