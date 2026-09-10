from datetime import datetime

from werkzeug.security import generate_password_hash

from app import (CharityCampaign, Contact, EmailMessage, Family, Receipt, StaffTask,
                 SupporterCommunication, create_app, db)


def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf': csrf})


def setup_workspace(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH',
                'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'test', 'DEMO': False,
                      'ADMIN_EMAIL': 'owner@example.test',
                      'ADMIN_PASSWORD_HASH': generate_password_hash('owner-pass-123')})
    client = app.test_client()
    client.get('/login')
    with client.session_transaction() as session:
        csrf = session['csrf']
    client.post('/login', data={'csrf': csrf, 'email': 'owner@example.test',
                                'password': 'owner-pass-123'})
    with app.app_context():
        family = Family(name='Test family')
        db.session.add(family)
        db.session.flush()
        contact = Contact(family_id=family.id, name='Test Supporter',
                          relationship='Friend', phone='8455551212',
                          email='supporter@example.test', supporter_key='phone:8455551212',
                          monthly_cents=3600, pledge_frequency='Monthly',
                          status='To contact')
        db.session.add(contact)
        db.session.add(CharityCampaign(
            family_id=family.id, external_id='55', key_env='test-key',
            public_url='https://abcharity.org/campaign/test-family',
            label='Test campaign', currency='USD'))
        db.session.commit()
        return app, client, contact.id


def test_full_supporter_communication_workflow(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    page = client.get('/communications')
    assert page.status_code == 200
    assert 'Test Supporter' in page.text and 'First phone call' in page.text

    assert post(client, f'/contacts/{contact_id}/communications/callback', {
        'scheduled_for': '2026-09-12T14:30', 'note': 'Call after work'}).status_code == 302
    with app.app_context():
        callback = db.session.scalar(db.select(SupporterCommunication).where(
            SupporterCommunication.contact_id == contact_id,
            SupporterCommunication.kind == 'callback'))
        task = db.session.scalar(db.select(StaffTask).where(
            StaffTask.source_contact_id == contact_id))
        assert callback.status == 'scheduled'
        assert callback.scheduled_for == datetime(2026, 9, 12, 14, 30)
        assert task.status == 'Waiting' and task.due_date.isoformat() == '2026-09-12'

    assert post(client, f'/contacts/{contact_id}/communications/call', {
        'note': 'Agreed to support monthly'}).status_code == 302
    assert post(client, f'/contacts/{contact_id}/communications/pledge', {}).status_code == 302
    with app.app_context():
        contact = db.session.get(Contact, contact_id)
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'pledge_confirmation'))
        assert contact.status == 'Pledged'
        assert message.status == 'preview'
        assert '$36.00 each month' in message.text_body
        assert db.session.scalar(db.select(db.func.count()).select_from(
            SupporterCommunication)) == 3


def test_manual_receipt_emails_and_enters_timeline(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    response = post(client, '/collections/receipts', {
        'contact_id': str(contact_id), 'received_on': '2026-09-10',
        'amount': '36.00', 'reference': 'check-100', 'note': ''})
    assert response.status_code == 302
    with app.app_context():
        receipt = db.session.scalar(db.select(Receipt))
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'donation_receipt'))
        timeline = db.session.scalar(db.select(SupporterCommunication).where(
            SupporterCommunication.kind == 'receipt_email'))
        assert receipt.amount_cents == 3600
        assert message.recipient == 'supporter@example.test'
        assert '09/10/2026' in message.text_body
        assert timeline.email_message_id == message.id
