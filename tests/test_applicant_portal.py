import hashlib
import base64
import hmac
import json
import time

import pytest

import app as app_module
from app import EmailMessage, Family, FamilyAssignment, StaffUser, db
from app_entry import create_app
from applicant_portal import ApplicantLoginToken, ApplicantMessage


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'DEMO': False,
                       'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'applicant-tests',
                       'APP_BASE_URL': 'https://yazory.example'})


def test_applicant_email_is_saved_on_intake(app):
    client = app.test_client()
    with app.app_context():
        owner = StaffUser(email='owner@example.test', password_hash='unused',
                          role='organization_admin')
        db.session.add(owner)
        db.session.commit()
        owner_id = owner.id
    with client.session_transaction() as state:
        state['user_id'] = owner_id
        state['csrf'] = 'test-csrf'
    response = client.post('/families/new', data={
        'csrf': 'test-csrf', 'name': 'Applicant family',
        'email': 'Applicant@Example.Test'})
    assert response.status_code == 302
    with app.app_context():
        family = db.session.scalar(db.select(Family).where(Family.name == 'Applicant family'))
        assert family.email == 'applicant@example.test'


def test_applicant_and_assigned_staff_share_private_thread(app):
    client = app.test_client()
    with app.app_context():
        family = Family(name='Portal family', email='family@example.test')
        staff = StaffUser(email='worker@example.test', password_hash='unused',
                          role='family_admin', status='active')
        db.session.add_all([family, staff])
        db.session.flush()
        db.session.add(FamilyAssignment(staff_user_id=staff.id, family_id=family.id))
        db.session.commit()
        family_id, staff_id = family.id, staff.id

    with client.session_transaction() as state:
        state['csrf'] = 'test-csrf'
    response = client.post('/applicant/login', data={
        'csrf': 'test-csrf', 'email': 'FAMILY@example.test'})
    assert response.status_code == 302
    with app.app_context():
        token = db.session.scalar(db.select(ApplicantLoginToken))
        raw = 'known-applicant-token'
        token.token_hash = hashlib.sha256(raw.encode()).hexdigest()
        db.session.commit()
    page = client.get(f'/applicant/login/{raw}', follow_redirects=True)
    assert page.status_code == 200
    assert 'Portal family' in page.text
    assert client.post('/applicant/messages', data={
        'csrf': 'test-csrf', 'body': 'I need help with a document.'}).status_code == 302

    with client.session_transaction() as state:
        state.clear()
        state['user_id'] = staff_id
        state['csrf'] = 'staff-csrf'
    staff_page = client.get(f'/families/{family_id}/messages')
    assert staff_page.status_code == 200
    assert 'I need help with a document.' in staff_page.text
    communications = client.get('/communications')
    assert 'New applicant messages' in communications.text
    assert 'I need help with a document.' in communications.text
    with app.app_context():
        incoming_id = db.session.scalar(db.select(ApplicantMessage).where(
            ApplicantMessage.direction == 'applicant')).id
    handled = client.post(
        f'/communications/applicant-messages/{incoming_id}/handled',
        data={'csrf': 'staff-csrf'})
    assert handled.status_code == 302
    assert client.post(f'/families/{family_id}/messages', data={
        'csrf': 'staff-csrf', 'body': 'We received your message.'}).status_code == 302

    with client.session_transaction() as state:
        state.clear()
        state['applicant_family_id'] = family_id
        state['csrf'] = 'portal-csrf'
    portal = client.get('/applicant')
    assert 'We received your message.' in portal.text
    with app.app_context():
        assert [row.direction for row in db.session.scalars(
            db.select(ApplicantMessage).order_by(ApplicantMessage.id))] == [
                'applicant', 'staff']


def test_direct_applicant_email_reply_enters_communications(app, monkeypatch):
    client = app.test_client()
    with app.app_context():
        family = Family(name='Email family', email='family@example.test')
        staff = StaffUser(email='worker@example.test', password_hash='unused',
                          role='organization_admin', status='active')
        db.session.add_all([family, staff])
        db.session.flush()
        message = EmailMessage(
            kind='applicant_portal_message', recipient=family.email,
            subject='New message', text_body='Please open the portal.',
            status='sent', family_id=family.id, staff_user_id=staff.id)
        db.session.add(message)
        db.session.commit()
        family_id, staff_id, message_id = family.id, staff.id, message.id
    app.config.update(
        EMAIL_REPLY_DOMAIN='reply.yaazory.org', RESEND_API_KEY='test-key',
        RESEND_WEBHOOK_SECRET='whsec_' + base64.b64encode(b'webhook-secret').decode())
    reference = hmac.new(b'applicant-tests', str(message_id).encode(),
                         hashlib.sha256).hexdigest()[:20]
    monkeypatch.setattr(app_module, 'retrieve_received_email', lambda *_args: {
        'to': [f'reply+{message_id}-{reference}@reply.yaazory.org'],
        'from': 'Applicant <family@example.test>',
        'subject': 'Re: New message', 'text': 'I replied by regular email.'})
    event = json.dumps({'type': 'email.received',
                        'data': {'email_id': 'applicant-inbound-1'}},
                       separators=(',', ':')).encode()
    timestamp = str(int(time.time()))
    event_id = 'applicant-event-1'
    signature = base64.b64encode(hmac.new(
        b'webhook-secret', event_id.encode() + b'.' + timestamp.encode() + b'.' + event,
        hashlib.sha256).digest()).decode()
    response = client.post('/resend/webhook', data=event, headers={
        'svix-id': event_id, 'svix-timestamp': timestamp,
        'svix-signature': f'v1,{signature}', 'content-type': 'application/json'})
    assert response.status_code == 200
    assert response.json['recipient'] == 'applicant'
    with client.session_transaction() as state:
        state['user_id'] = staff_id
        state['csrf'] = 'staff-csrf'
    page = client.get('/communications')
    assert 'I replied by regular email.' in page.text
    assert f'/families/{family_id}/messages' in page.text


def test_unassigned_staff_cannot_open_applicant_messages(app):
    client = app.test_client()
    with app.app_context():
        family = Family(name='Private family', email='private@example.test')
        staff = StaffUser(email='outsider@example.test', password_hash='unused',
                          role='family_admin', status='active')
        db.session.add_all([family, staff])
        db.session.commit()
        family_id, staff_id = family.id, staff.id
    with client.session_transaction() as state:
        state['user_id'] = staff_id
        state['csrf'] = 'staff-csrf'
    assert client.get(f'/families/{family_id}/messages').status_code == 403
