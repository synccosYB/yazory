import hashlib
import pytest

from app import Contact, Family, Receipt, create_app, db
from supporter_portal import SupporterLoginToken


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'portal-tests', 'APP_BASE_URL': 'https://yazory.example'})


@pytest.fixture
def client(app):
    return app.test_client()


def _csrf(client):
    with client.session_transaction() as session:
        session['csrf'] = 'portal-csrf'
    return 'portal-csrf'


def test_supporter_magic_link_opens_all_linked_cases(app, client):
    with app.app_context():
        second = Family(name='Second supported family', status='Active')
        db.session.add(second)
        db.session.flush()
        first = db.session.scalar(db.select(Contact).order_by(Contact.id))
        first.email = 'donor@example.test'
        first.supporter_key = 'phone:8455550100'
        linked = Contact(family_id=second.id, name=first.name, relationship='Friend',
                         email=first.email, supporter_key=first.supporter_key,
                         monthly_cents=2500, pledge_frequency='Monthly', status='Pledged')
        db.session.add(linked)
        db.session.commit()

    response = client.post('/donor/login', data={
        'csrf': _csrf(client), 'email': 'DONOR@example.test'}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        token = db.session.scalar(db.select(SupporterLoginToken))
        assert token is not None
        # Replace the unknown emailed raw token with a known unused token.
        raw = 'known-secure-link'
        token.token_hash = hashlib.sha256(raw.encode()).hexdigest()
        db.session.commit()
    page = client.get(f'/donor/login/{raw}', follow_redirects=True)
    assert page.status_code == 200
    assert 'Sample family' in page.text
    assert 'Second supported family' in page.text


def test_supporter_can_update_only_own_pledge(app, client):
    with app.app_context():
        own = db.session.scalar(db.select(Contact).order_by(Contact.id))
        own.supporter_key = 'phone:8455550100'
        other = Contact(family_id=own.family_id, name='Other person', relationship='Friend',
                        supporter_key='phone:8455550199')
        db.session.add(other)
        db.session.commit()
        own_id, other_id = own.id, other.id
    with client.session_transaction() as portal_session:
        portal_session['csrf'] = 'portal-csrf'
        portal_session['supporter_key'] = 'phone:8455550100'
    assert client.post(f'/donor/pledges/{own_id}', data={
        'csrf': 'portal-csrf', 'amount': '42.50', 'frequency': 'Weekly'}).status_code == 302
    assert client.post(f'/donor/pledges/{other_id}', data={
        'csrf': 'portal-csrf', 'amount': '10', 'frequency': 'Monthly'}).status_code == 403
    with app.app_context():
        own = db.session.get(Contact, own_id)
        assert (own.monthly_cents, own.pledge_frequency, own.status) == (4250, 'Weekly', 'Pledged')


def test_portal_donation_form_is_available_without_staff_login(app, client):
    with app.app_context():
        contact = db.session.scalar(db.select(Contact).order_by(Contact.id))
        contact.supporter_key = 'phone:8455550100'
        db.session.commit()
        contact_id = contact.id
    with client.session_transaction() as portal_session:
        portal_session['supporter_key'] = 'phone:8455550100'
    response = client.get(f'/donor/donate/{contact_id}')
    assert response.status_code == 200
    assert 'native-payment' in response.text
    assert '/donor' in response.text


def test_supporter_can_download_only_own_receipt(app, client):
    with app.app_context():
        own = db.session.scalar(db.select(Contact).order_by(Contact.id))
        own.supporter_key = 'phone:8455550100'
        other = Contact(family_id=own.family_id, name='Other donor', relationship='Friend',
                        supporter_key='phone:8455550199')
        db.session.add(other)
        db.session.flush()
        own_receipt = Receipt(contact_id=own.id, family_id=own.family_id,
                              amount_cents=2500, reference='pi_own')
        other_receipt = Receipt(contact_id=other.id, family_id=other.family_id,
                                amount_cents=3500, reference='pi_other')
        db.session.add_all([own_receipt, other_receipt])
        db.session.commit()
        own_id, other_id = own_receipt.id, other_receipt.id
    with client.session_transaction() as portal_session:
        portal_session['supporter_key'] = 'phone:8455550100'
    response = client.get(f'/donor/receipts/{own_id}.pdf')
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.data.startswith(b'%PDF-')
    assert client.get(f'/donor/receipts/{other_id}.pdf').status_code == 403
