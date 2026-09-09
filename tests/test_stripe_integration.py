import app as app_module
from app import (Contact, Expense, Family, Receipt, StripeEvent, StripePayment,
                 StripeRecipient, StripeTransfer, create_app, db)


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
        'STRIPE_WEBHOOK_SECRET': 'whsec_yazory',
        'APP_BASE_URL': 'https://yazory.example',
    })


def test_checkout_and_webhook_create_one_receipt(monkeypatch):
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact = db.session.scalar(db.select(Contact))
        contact_id = contact.id
    page = client.get(f'/supporters/{contact_id}/donate').text
    assert 'value="180.00"' in page

    created = {}

    def checkout(_secret, params, idempotency_key):
        assert params['mode'] == 'subscription'
        assert params['line_items'][0]['price_data']['recurring']['interval'] == 'month'
        assert idempotency_key.startswith('yazory-checkout-')
        created['metadata'] = params['metadata']
        return {'id': 'cs_test_1', 'url': 'https://checkout.stripe.test/cs_test_1'}

    monkeypatch.setattr(app_module, 'create_checkout_session', checkout)
    response = client.post(f'/supporters/{contact_id}/stripe-checkout', data={
        'csrf': csrf(client), 'amount': '18.00', 'frequency': 'Monthly'})
    assert response.status_code == 303
    assert response.location == 'https://checkout.stripe.test/cs_test_1'
    checkout_event = {'id': 'evt_checkout_1', 'type': 'checkout.session.completed',
                      'data': {'object': {'id': 'cs_test_1', 'subscription': 'sub_1',
                                          'metadata': created['metadata']}}}
    invoice_event = {'id': 'evt_invoice_1', 'type': 'invoice.paid', 'data': {'object': {
        'id': 'in_1', 'subscription': 'sub_1', 'amount_paid': 1800,
        'customer_email': 'donor@example.test', 'metadata': {}}}}
    events = iter([checkout_event, invoice_event, invoice_event])
    monkeypatch.setattr(app_module, 'construct_webhook_event', lambda *_args: next(events))
    webhook_client = app.test_client()  # Stripe sends no browser session or CSRF token.
    for _ in range(3):
        response = webhook_client.post('/stripe/webhook', data=b'{}',
                                       headers={'Stripe-Signature': 'test'})
        assert response.status_code == 200
    with app.app_context():
        payment = db.session.scalar(db.select(StripePayment))
        assert db.session.scalar(db.select(db.func.count()).select_from(Receipt)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(StripeEvent)) == 2
        assert payment.status == 'active'
        assert payment.successful_charges == 1


def test_zero_pledge_defaults_to_valid_one_dollar_checkout_amount():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact = db.session.scalar(db.select(Contact))
        contact.monthly_cents = 0
        db.session.commit()
        contact_id = contact.id
    page = client.get(f'/supporters/{contact_id}/donate').text
    assert 'value="1.00"' in page
    assert f'/supporters/{contact_id}/embedded-checkout-session' in page
    assert 'value="One time" selected' in page


def test_checkout_can_open_through_plain_get_navigation(monkeypatch):
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact_id = db.session.scalar(db.select(Contact.id))
    monkeypatch.setattr(app_module, 'create_checkout_session',
                        lambda *_args: {'id': 'cs_get_1',
                                       'url': 'https://checkout.stripe.test/cs_get_1'})
    response = client.get(
        f'/supporters/{contact_id}/stripe-checkout?amount=1.00&frequency=One+time')
    assert response.status_code == 303
    assert response.location == 'https://checkout.stripe.test/cs_get_1'


def test_checkout_failure_returns_to_supporter_with_visible_error(monkeypatch):
    app = make_app()
    client = app.test_client()
    with app.app_context():
        contact_id = db.session.scalar(db.select(Contact.id))

    class LiveAccountError(Exception):
        user_message = 'Your Stripe account cannot currently make live charges.'

    monkeypatch.setattr(app_module, 'create_checkout_session',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(LiveAccountError()))
    response = client.post(f'/supporters/{contact_id}/stripe-checkout', data={
        'csrf': csrf(client), 'amount': '1.00', 'frequency': 'One time'},
        follow_redirects=True)
    assert response.status_code == 200
    assert 'Your Stripe account cannot currently make live charges.' in response.text
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(StripePayment)) == 0


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
