from datetime import datetime

from werkzeug.security import generate_password_hash

import app_original as core_module
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
    assert 'data-ai-email-form' in page.text
    assert 'data-loading-text="Writing the email…"' in page.text

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


def test_supporter_communication_link_opens_only_that_supporter(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        contact = db.session.get(Contact, contact_id)
        other = Contact(family_id=contact.family_id, name='Other Supporter',
                        relationship='Friend', monthly_cents=0,
                        pledge_frequency='Monthly', status='To contact')
        db.session.add(other)
        db.session.commit()

    profile = client.get(f'/supporters/{contact_id}')
    assert f'/communications?contact_id={contact_id}' in profile.text
    page = client.get(f'/communications?contact_id={contact_id}')
    assert page.status_code == 200
    assert 'Test Supporter' in page.text
    assert 'Other Supporter' not in page.text


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


def test_no_answer_ai_draft_preview_and_send(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-ai-key')
    monkeypatch.setattr(
        'app.draft_initial_email',
        lambda key, model, language: 'Dear {supporter_name},\n\nWhat time works for a short call?\n\n{staff_name}')
    draft = post(client, f'/contacts/{contact_id}/communications/initial-email/draft', {})
    assert draft.status_code == 200
    assert 'Test Supporter' in draft.text
    assert 'supporter-email-preview-body' in draft.text
    assert 'data-initial-email-draft' in draft.text
    assert 'What time works for a short call?' in draft.text
    sent = post(client, f'/contacts/{contact_id}/communications/initial-email', {
        'recipient_email': 'supporter@example.test',
        'subject': 'A good time to speak',
        'body': 'Dear Test Supporter,\n\nWhat time works for a short call?'})
    assert sent.status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'supporter_initial_contact'))
        timeline = db.session.scalar(db.select(SupporterCommunication).where(
            SupporterCommunication.kind == 'initial_email'))
        assert message.recipient == 'supporter@example.test'
        assert timeline.email_message_id == message.id


def test_yiddish_supporter_email_is_delivered_rtl(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    delivered = {}

    def capture_delivery(api_key, sender, recipient, subject, html, text):
        delivered.update(html=html, text=text)
        return 'email_rtl', None

    monkeypatch.setattr(core_module, 'deliver', capture_delivery)
    app.config.update(TESTING=False, DEMO=False, RESEND_API_KEY='test-key',
                      EMAIL_FROM='notifications@example.test')
    response = post(client, f'/contacts/{contact_id}/communications/initial-email', {
        'recipient_email': 'supporter@example.test',
        'subject': 'ווען איז א גוטע צייט צו רעדן?',
        'body': 'לכבוד דעם חשובן העלפער,\n\nווען איז א גוטע צייט פאר א קורצן שמועס?'})
    assert response.status_code == 302
    assert '<html dir="rtl">' in delivered['html']
    assert 'dir="rtl" align="right"' in delivered['html']
    assert 'direction:rtl;text-align:right' in delivered['html']


def test_email_button_works_without_saved_email_and_saves_it(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        db.session.get(Contact, contact_id).email = ''
        db.session.commit()
    monkeypatch.setattr('app.draft_initial_email', lambda *args: 'Hello {supporter_name}')
    page = client.get('/communications')
    assert 'data-ai-email-form' in page.text
    assert 'disabled' not in page.text.split('data-ai-email-form', 1)[1].split('</form>', 1)[0]
    draft = post(client, f'/contacts/{contact_id}/communications/initial-email/draft', {})
    assert draft.status_code == 200
    assert 'name="recipient_email"' in draft.text
    sent = post(client, f'/contacts/{contact_id}/communications/initial-email', {
        'recipient_email': 'new-address@example.test',
        'subject': 'Hello', 'body': 'A short message'})
    assert sent.status_code == 302
    with app.app_context():
        assert db.session.get(Contact, contact_id).email == 'new-address@example.test'


def test_no_answer_button_opens_fallback_when_ai_fails(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    monkeypatch.setattr(
        'app.draft_initial_email',
        lambda *args: (_ for _ in ()).throw(ValueError('AI unavailable')))
    with client.session_transaction() as session:
        session['language'] = 'yi'
    draft = post(client, f'/contacts/{contact_id}/communications/initial-email/draft', {})
    assert draft.status_code == 200
    assert 'supporter-email-body' in draft.text
    assert 'ווען איז א גוטע צייט צו רעדן?' in draft.text
    assert 'Test Supporter' in draft.text
