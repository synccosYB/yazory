from app_entry import create_app
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime

from werkzeug.security import generate_password_hash

import app_original as core_module
import app as app_module
from app import (Askan, CharityCampaign, Contact, EmailMessage, Family, GeneralSmsMessage,
                 InboundInboxMessage, Receipt, StaffTask, SupporterCommunication, db)


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
    assert 'communication-accordion-item outreach-supporter' in page.text
    assert 'data-accordion-search="communications-supporters-list"' in page.text
    assert 'id="communications-supporters-list"' in page.text
    assert 'aria-label="Search supporters"' in page.text
    assert 'data-communication-filter="all"' in page.text
    assert 'data-communication-filter="callbacks"' in page.text
    assert 'data-communication-filter="overdue"' in page.text
    assert 'data-mailbox-folder="supporters"' in page.text
    assert 'data-mailbox-folder="applicants"' in page.text
    assert 'data-mailbox-folder="sent"' in page.text
    assert 'id="communication-callbacks"' in page.text
    assert 'id="outreach-workflow"' in page.text
    assert 'class="card foldable-communication-section" id="communication-history"' in page.text
    assert 'class="mailbox-list-fold"' in page.text
    assert '<div class="outreach-action-grid">' in page.text
    assert 'pages.js?v=20260920-mobile-v2' in page.text
    assert '<span>Mobile number</span><bdi dir="ltr">8455551212</bdi>' in page.text
    javascript = client.get('/static/pages.js').text
    assert "table.closest('section')?.querySelector('.supporter-summary-heading')" in javascript

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
        assert 'https://abcharity.org/campaign/test-family' in message.text_body
        assert db.session.scalar(db.select(db.func.count()).select_from(
            SupporterCommunication)) == 3


def test_message_uses_saved_phone_without_asking_for_it_again(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        assert db.session.get(Contact, contact_id).phone == '8455551212'
    client.get('/communications')
    with app.app_context():
        assert db.session.get(Contact, contact_id).phone == '8455551212'
    with client.session_transaction() as session:
        csrf = session['csrf']
    response = client.post(f'/contacts/{contact_id}/communications/message/sms', data={
        'body': 'Can we speak today?', 'csrf': csrf})
    assert response.status_code == 302, response.text
    page = client.get(response.location)
    assert 'Communication with Test Supporter' in page.text
    assert 'Test family' in page.text
    assert 'Messages and communication history' in page.text
    assert 'Can we speak today?' in page.text
    assert 'Show all supporters' in page.text
    with app.app_context():
        row = db.session.scalar(db.select(SupporterCommunication).where(
            SupporterCommunication.contact_id == contact_id,
            SupporterCommunication.kind == 'sms'))
        assert row is not None and row.status == 'preview'



def test_two_family_pledges_automatically_use_one_yazory_link(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        original = db.session.get(Contact, contact_id)
        second_family = Family(name='Second family')
        db.session.add(second_family)
        db.session.flush()
        db.session.add(Contact(
            family_id=second_family.id, name=original.name,
            relationship='Friend', phone=original.phone, email=original.email,
            supporter_key=original.supporter_key, monthly_cents=2400,
            pledge_frequency='Monthly', status='Contacted'))
        db.session.commit()

    page = client.get(f'/communications?contact_id={contact_id}')
    assert '<strong>Yazory</strong>' in page.text
    assert '2 connected family pledges' in page.text
    assert post(client, f'/contacts/{contact_id}/communications/pledge', {}).status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'pledge_confirmation'))
        assert 'Test family: $36.00 each month' in message.text_body
        assert 'Second family: $24.00 each month' in message.text_body
        assert f'/supporters/{contact_id}/donate' in message.text_body
        assert 'abcharity.org/campaign/test-family' not in message.text_body


def test_missing_abcharity_campaign_falls_back_to_yazory(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        db.session.query(CharityCampaign).delete()
        db.session.commit()
    assert post(client, f'/contacts/{contact_id}/communications/pledge', {}).status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'pledge_confirmation'))
        assert f'/supporters/{contact_id}/donate' in message.text_body


def test_connected_campaign_without_public_url_blocks_wrong_pledge_link(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        campaign = db.session.scalar(db.select(CharityCampaign))
        campaign.public_url = ''
        db.session.commit()
    response = post(client, f'/contacts/{contact_id}/communications/pledge', {})
    assert response.status_code == 302
    assert response.location.endswith('/families/1/donations')
    with app.app_context():
        assert db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'pledge_confirmation')) is None


def test_supporter_communication_link_opens_only_that_supporter(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    with app.app_context():
        contact = db.session.get(Contact, contact_id)
        other = Contact(family_id=contact.family_id, name='Other Supporter',
                        relationship='Friend', monthly_cents=0,
                        pledge_frequency='Monthly', status='To contact')
        db.session.add(other)
        db.session.flush()
        db.session.add_all([
            SupporterCommunication(
                contact_id=contact.id, family_id=contact.family_id, kind='sms',
                subject='Selected conversation', body='Only this message belongs here',
                status='completed'),
            SupporterCommunication(
                contact_id=other.id, family_id=other.family_id, kind='sms',
                subject='Other conversation', body='Must not appear here',
                status='completed'),
            InboundInboxMessage(
                provider_message_id='general-inbox-message',
                sender_email='stranger@example.test', recipient='info@yaazory.org',
                subject='General portal inbox message', body='Not this supporter'),
            GeneralSmsMessage(
                provider_message_id='general-sms-message', phone='+19175550199',
                direction='inbound', body='Unrelated general SMS', status='unread'),
        ])
        db.session.commit()

    profile = client.get(f'/supporters/{contact_id}')
    assert f'/communications?contact_id={contact_id}' in profile.text
    page = client.get(f'/communications?contact_id={contact_id}')
    assert page.status_code == 200
    assert 'Test Supporter' in page.text
    assert 'Other Supporter' not in page.text
    assert 'Selected conversation' in page.text
    assert 'Only this message belongs here' in page.text
    assert 'Other conversation' not in page.text
    assert 'General portal inbox message' not in page.text
    assert 'Unrelated general SMS' not in page.text
    assert 'data-mailbox-folder=' not in page.text
    assert 'New applicant messages' not in page.text
    assert 'Applicant communication history' not in page.text


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
        assert message.status == 'preview'
        assert message.error == 'Email delivery is disabled in preview mode.'
        assert timeline.email_message_id == message.id
        assert timeline.status == 'preview'
    result_page = client.get(sent.location)
    assert 'Email was prepared but not sent because delivery is in preview mode.' in result_page.text
    assert 'id="selected-supporter-history"' in result_page.text
    assert 'What time works for a short call?' in result_page.text
    assert '<small class="preserve">Dear Test Supporter' not in result_page.text


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


def test_resend_inbound_reply_is_matched_to_exact_supporter_and_case(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    app.config.update(
        EMAIL_REPLY_DOMAIN='reply.yaazory.org',
        RESEND_API_KEY='test-api-key',
        RESEND_WEBHOOK_SECRET='whsec_' + base64.b64encode(b'webhook-secret').decode())
    with app.app_context():
        message = EmailMessage(
            kind='supporter_initial_contact', recipient='supporter@example.test',
            subject='Can we speak?', text_body='What time works?', status='sent')
        db.session.add(message)
        db.session.flush()
        db.session.add(SupporterCommunication(
            contact_id=contact_id, family_id=db.session.get(Contact, contact_id).family_id,
            email_message_id=message.id, kind='initial_email', direction='outbound',
            subject=message.subject, body=message.text_body, status='completed'))
        db.session.commit()
        message_id = message.id
    reference = hmac.new(b'test', str(message_id).encode(), hashlib.sha256).hexdigest()[:20]
    monkeypatch.setattr(app_module, 'retrieve_received_email', lambda key, email_id: {
        'id': email_id,
        'to': [f'reply+{message_id}-{reference}@reply.yaazory.org'],
        'from': 'Test Supporter <supporter@example.test>',
        'subject': 'Re: Can we speak?',
        'text': 'Tomorrow evening works for me.',
        'attachments': [{'filename': 'schedule.pdf'}],
    })
    event = json.dumps({
        'type': 'email.received',
        'data': {'email_id': 'received-email-1'},
    }, separators=(',', ':')).encode()
    timestamp = str(int(time.time()))
    event_id = 'msg_inbound_1'
    signature = base64.b64encode(hmac.new(
        b'webhook-secret', event_id.encode() + b'.' + timestamp.encode() + b'.' + event,
        hashlib.sha256).digest()).decode()
    headers = {
        'svix-id': event_id, 'svix-timestamp': timestamp,
        'svix-signature': f'v1,{signature}', 'content-type': 'application/json'}
    response = client.post('/resend/webhook', data=event, headers=headers)
    assert response.status_code == 200
    assert response.json == {'matched': True, 'received': True}
    # Resend retries are idempotent.
    duplicate = client.post('/resend/webhook', data=event, headers=headers)
    assert duplicate.json == {'duplicate': True, 'received': True}
    with app.app_context():
        reply = db.session.scalar(db.select(SupporterCommunication).where(
            SupporterCommunication.kind == 'email_reply'))
        assert reply.contact_id == contact_id
        assert reply.direction == 'inbound'
        assert reply.status == 'received'
        assert 'Tomorrow evening works for me.' in reply.body
        assert 'schedule.pdf' in reply.body
        reply_id = reply.id
    inbox = client.get(f'/communications?contact_id={contact_id}')
    assert 'New email replies' in inbox.text
    assert 'Tomorrow evening works for me.' in inbox.text
    assert 'Mark handled' in inbox.text
    handled = post(client, f'/communications/replies/{reply_id}/handled', {})
    assert handled.status_code == 302
    with app.app_context():
        assert db.session.get(SupporterCommunication, reply_id).status == 'handled'
    assert 'Tomorrow evening works for me.' not in client.get(handled.location).text.split(
        'New email replies', 1)[1].split('Outreach workflow', 1)[0]


def test_email_to_public_info_address_appears_in_messages(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    app.config.update(
        EMAIL_REPLY_DOMAIN='reply.yaazory.org',
        PUBLIC_INBOX_EMAIL='info@yaazory.org',
        RESEND_API_KEY='test-api-key',
        RESEND_WEBHOOK_SECRET='whsec_' + base64.b64encode(b'webhook-secret').decode())
    monkeypatch.setattr(app_module, 'retrieve_received_email', lambda key, email_id: {
        'id': email_id,
        'to': ['Yazory <info@yaazory.org>'],
        'from': 'New Applicant <sender@example.test>',
        'subject': 'Need help with utilities',
        'text': 'Please call me about an application.',
        'html': '<p>Please call me about an <strong>application</strong>.</p>'
                '<img src="data:image/png;base64,c2lnbmF0dXJl">',
        'attachments': [
            {'filename': 'signature.png', 'content_disposition': 'inline'},
            {'filename': 'utility-bill.pdf'}],
    })
    event = json.dumps({
        'type': 'email.received',
        'data': {'email_id': 'public-inbox-email-1'},
    }, separators=(',', ':')).encode()
    timestamp = str(int(time.time()))
    event_id = 'msg_public_inbox_1'
    signature = base64.b64encode(hmac.new(
        b'webhook-secret', event_id.encode() + b'.' + timestamp.encode() + b'.' + event,
        hashlib.sha256).digest()).decode()
    headers = {
        'svix-id': event_id, 'svix-timestamp': timestamp,
        'svix-signature': f'v1,{signature}', 'content-type': 'application/json'}

    response = client.post('/resend/webhook', data=event, headers=headers)
    assert response.status_code == 200
    assert response.json == {
        'matched': True, 'received': True, 'recipient': 'public_inbox'}
    with app.app_context():
        message = db.session.scalar(db.select(InboundInboxMessage))
        assert message.sender_name == 'New Applicant'
        assert message.sender_email == 'sender@example.test'
        assert message.recipient == 'info@yaazory.org'
        assert 'Please call me about an application.' in message.body
        assert 'utility-bill.pdf' in message.body
        assert 'signature.png' not in message.body
        assert '<strong>application</strong>' in message.html_body
        message_id = message.id

    inbox = client.get('/communications')
    assert 'Yazory inbox' in inbox.text
    assert 'Need help with utilities' in inbox.text
    assert 'Please call me about an application.' in inbox.text
    assert 'communication-email-frame' in inbox.text
    assert '&lt;strong&gt;application&lt;/strong&gt;' in inbox.text
    handled = post(client, f'/communications/inbox/{message_id}/handled', {})
    assert handled.status_code == 302
    with app.app_context():
        assert db.session.get(InboundInboxMessage, message_id).status == 'handled'
    assert 'Need help with utilities' in client.get(handled.location).text


def test_organization_admin_can_reply_to_public_inbox_message(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    delivered = {}

    def capture_delivery(api_key, sender, recipient, subject, html, text, **options):
        delivered.update(
            recipient=recipient, subject=subject, text=text, options=options)
        return 'reply-provider-id', None

    monkeypatch.setattr(core_module, 'deliver', capture_delivery)
    app.config.update(TESTING=False, DEMO=False, RESEND_API_KEY='test-key',
                      EMAIL_FROM='Yazory <info@reply.yaazory.org>')
    with app.app_context():
        inbox_message = InboundInboxMessage(
            provider_message_id='received-public-message',
            sender_name='New Applicant', sender_email='sender@example.test',
            recipient='info@yaazory.org', subject='Need help with utilities',
            body='Please call me.', status='unread')
        db.session.add(inbox_message)
        db.session.commit()
        message_id = inbox_message.id

    page = client.get('/communications')
    assert f'/communications/inbox/{message_id}/reply' in page.text
    assert 'value="Re: Need help with utilities"' in page.text

    response = post(client, f'/communications/inbox/{message_id}/reply', {
        'subject': 'Re: Need help with utilities',
        'body': 'Thank you. We will call you shortly.'})
    assert response.status_code == 302
    assert delivered['recipient'] == 'sender@example.test'
    assert delivered['subject'] == 'Re: Need help with utilities'
    assert delivered['text'] == 'Thank you. We will call you shortly.'
    with app.app_context():
        saved = db.session.get(InboundInboxMessage, message_id)
        assert saved.status == 'handled'
        assert saved.handled_at is not None
        outbound = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'public_inbox_reply'))
        assert outbound.recipient == 'sender@example.test'
        assert outbound.status == 'sent'


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
        db.session.get(Contact, contact_id).email = ''
        db.session.commit()
    repaired = client.get('/communications')
    assert 'value="new-address@example.test"' in repaired.text
    with app.app_context():
        assert db.session.get(Contact, contact_id).email == 'new-address@example.test'


def test_compose_can_send_to_email_not_connected_to_system(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    page = client.get('/communications')
    assert 'name="recipient_email"' in page.text
    assert 'Any email address' in page.text

    composer = client.get('/communications?recipient_email=outside@example.test')
    assert composer.status_code == 200
    assert 'value="outside@example.test"' in composer.text
    assert 'action="/communications/external-email"' in composer.text

    sent = post(client, '/communications/external-email', {
        'recipient_email': 'outside@example.test',
        'subject': 'A message from Yazory',
        'body': 'This address is not connected to a supporter.'})
    assert sent.status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'general_outbound'))
        assert message.recipient == 'outside@example.test'
        assert message.subject == 'A message from Yazory'
        assert message.staff_user_id is not None
        assert message.family_id is None
    history = client.get('/communications')
    assert 'data-mailbox-category="sent"' in history.text
    assert 'outside@example.test' in history.text
    assert 'A message from Yazory' in history.text
    assert 'This address is not connected to a supporter.' in history.text


def test_external_email_reply_goes_to_general_inbox(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    delivered = {}

    def capture_delivery(api_key, sender, recipient, subject, html, text, **options):
        delivered.update(options)
        return 'external-provider-id', None

    monkeypatch.setattr(core_module, 'deliver', capture_delivery)
    app.config.update(TESTING=False, DEMO=False, RESEND_API_KEY='test-key',
                      EMAIL_FROM='Yazory <info@reply.yaazory.org>',
                      EMAIL_REPLY_DOMAIN='reply.yaazory.org')
    sent = post(client, '/communications/external-email', {
        'recipient_email': 'outside@example.test',
        'subject': 'Hello', 'body': 'Please reply to Yazory.'})
    assert sent.status_code == 302
    assert delivered['reply_to'] == 'info@reply.yaazory.org'


def test_sms_and_whatsapp_are_saved_in_communication_history(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    sent = []

    def capture(*args, **kwargs):
        sent.append((args, kwargs))
        return f'SM{len(sent)}', None

    monkeypatch.setattr('app.deliver_message', capture)
    app.config.update(
        TESTING=False, DEMO=False, TWILIO_ACCOUNT_SID='ACtest',
        TWILIO_AUTH_TOKEN='secret', TWILIO_SMS_FROM='+18455550000',
        TWILIO_WHATSAPP_FROM='+14155238886')
    sms = post(client, f'/contacts/{contact_id}/communications/message/sms', {
        'recipient_phone': '(845) 555-1212', 'body': 'Can we speak today?'})
    whatsapp = post(client, f'/contacts/{contact_id}/communications/message/whatsapp', {
        'recipient_phone': '845-555-1212', 'body': 'א גוטן, ווען קען מען רעדן?'})
    assert sms.status_code == 302 and whatsapp.status_code == 302
    assert sent[0][0][2] == '+18455551212'
    assert sent[0][1]['channel'] == 'sms'
    assert sent[1][1]['channel'] == 'whatsapp'
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterCommunication).order_by(
            SupporterCommunication.id)).all()
        assert [row.kind for row in rows] == ['sms', 'whatsapp']
        assert [row.provider_message_id for row in rows] == ['SM1', 'SM2']
        assert all(row.status == 'completed' for row in rows)
        assert db.session.get(Contact, contact_id).cell_phone == '+18455551212'


def test_failed_twilio_message_keeps_error_in_history(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    monkeypatch.setattr('app.deliver_message', lambda *args, **kwargs: (
        None, 'Twilio rejected this destination.'))
    app.config.update(TESTING=False, DEMO=False)
    response = post(client, f'/contacts/{contact_id}/communications/message/sms', {
        'recipient_phone': '8455551212', 'body': 'Test'})
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(SupporterCommunication))
        assert row.status == 'failed'
        assert row.delivery_error == 'Twilio rejected this destination.'


def test_valid_twilio_reply_is_saved_once_in_supporter_history(monkeypatch):
    app, client, contact_id = setup_workspace(monkeypatch)
    app.config.update(TESTING=False, DEMO=False, TWILIO_AUTH_TOKEN='secret')
    monkeypatch.setattr('app.validate_webhook_signature', lambda *args: True)
    payload = {
        'From': '+18455551212', 'To': '+12513063232',
        'Body': 'Yes, please call after six.',
        'MessageSid': 'SM' + 'b' * 32}

    first = client.post('/twilio/incoming-message', data=payload)
    duplicate = client.post('/twilio/incoming-message', data=payload)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert first.mimetype == 'application/xml'
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterCommunication)).all()
        assert len(rows) == 1
        assert rows[0].contact_id == contact_id
        assert rows[0].kind == 'sms'
        assert rows[0].direction == 'inbound'
        assert rows[0].subject == 'Incoming text message'
        assert rows[0].body == 'Yes, please call after six.'


def test_valid_twilio_reply_from_applicant_is_saved_in_family_messages(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    app.config.update(TESTING=False, DEMO=False, TWILIO_AUTH_TOKEN='secret')
    monkeypatch.setattr('app.validate_webhook_signature', lambda *args: True)
    with app.app_context():
        family = db.session.scalar(db.select(Family).where(Family.name == 'Test family'))
        family.phone = '3479854847'
        db.session.commit()
        family_id = family.id

    response = client.post('/twilio/incoming-message', data={
        'From': '+13479854847', 'To': '+12513063232',
        'Body': 'Applicant reply', 'MessageSid': 'SM' + 'c' * 32})

    assert response.status_code == 200
    with app.app_context():
        from applicant_portal import ApplicantMessage
        row = db.session.scalar(db.select(ApplicantMessage))
        assert row.family_id == family_id
        assert row.direction == 'applicant'
        assert row.status == 'unread'
        assert row.body == 'Applicant reply'
        assert row.provider_message_id == 'SM' + 'c' * 32


def test_unknown_twilio_reply_is_saved_in_general_sms_inbox(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    app.config.update(TESTING=False, DEMO=False, TWILIO_AUTH_TOKEN='secret')
    monkeypatch.setattr('app.validate_webhook_signature', lambda *args: True)

    response = client.post('/twilio/incoming-message', data={
        'From': '+19175550199', 'To': '+12513063232',
        'Body': 'Can someone call me?', 'MessageSid': 'SM' + 'd' * 32})

    assert response.status_code == 200
    with app.app_context():
        row = db.session.scalar(db.select(GeneralSmsMessage))
        assert row.phone == '+19175550199'
        assert row.direction == 'inbound'
        assert row.status == 'unread'
        assert row.body == 'Can someone call me?'
    page = client.get('/communications')
    assert 'data-mailbox-folder="general-sms"' in page.text
    assert 'Can someone call me?' in page.text


def test_general_sms_can_be_sent_and_replied_to(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    sent = post(client, '/communications/general-sms', {
        'recipient_phone': '(917) 555-0199', 'body': 'Hello from Yazory'})
    assert sent.status_code == 302
    with app.app_context():
        outbound = db.session.scalar(db.select(GeneralSmsMessage))
        assert outbound.phone == '+19175550199'
        assert outbound.direction == 'outbound'
        assert outbound.status == 'preview'
        inbound = GeneralSmsMessage(
            provider_message_id='SM' + 'e' * 32, phone='+19175550199',
            direction='inbound', body='Thank you', status='unread')
        db.session.add(inbound)
        db.session.commit()
        inbound_id = inbound.id

    reply = post(client, f'/communications/general-sms/{inbound_id}/reply', {
        'body': 'You are welcome'})
    assert reply.status_code == 302
    with app.app_context():
        rows = db.session.scalars(db.select(GeneralSmsMessage).order_by(
            GeneralSmsMessage.id)).all()
        assert [row.direction for row in rows] == ['outbound', 'inbound', 'outbound']
        assert rows[1].status == 'unread'
        assert rows[2].body == 'You are welcome'


def test_family_askan_sms_button_prefills_and_links_message_to_case(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    with app.app_context():
        family = db.session.scalar(db.select(Family).where(Family.name == 'Test family'))
        askan = Askan(name='Yoel Neiman', phone='8456621449')
        db.session.add(askan)
        db.session.flush()
        family.designated_askan_id = askan.id
        db.session.commit()
        family_id = family.id

    profile = client.get(f'/families/{family_id}')
    assert profile.status_code == 200
    assert 'Send SMS' in profile.text
    assert 'sms_phone=8456621449' in profile.text

    compose = client.get(
        f'/communications?sms_phone=8456621449&sms_name=Yoel+Neiman&family_id={family_id}')
    assert compose.status_code == 200
    assert 'value="8456621449"' in compose.text
    assert f'name="family_id" value="{family_id}"' in compose.text
    assert 'Yoel Neiman' in compose.text

    sent = post(client, '/communications/general-sms', {
        'recipient_phone': '8456621449', 'family_id': str(family_id),
        'body': 'Please call about this case.'})
    assert sent.status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(GeneralSmsMessage))
        assert message.family_id == family_id
        assert message.family.name == 'Test family'


def test_twilio_reply_rejects_invalid_signature(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    app.config.update(TESTING=False, DEMO=False, TWILIO_AUTH_TOKEN='secret')
    monkeypatch.setattr('app.validate_webhook_signature', lambda *args: False)

    response = client.post('/twilio/incoming-message', data={
        'From': '+18455551212', 'Body': 'Untrusted'})

    assert response.status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(
            SupporterCommunication)) == 0


def test_twilio_setup_is_admin_only_and_connects_service(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    overview = {
        'account': {'friendly_name': 'Yazory', 'status': 'active', 'type': 'Full'},
        'numbers': [{'sid': 'PN' + '1' * 32, 'phone_number': '+12513063232',
                     'friendly_name': 'Yazory', 'capabilities': {'sms': True}}],
        'services': [], 'whatsapp_senders': [], 'warnings': []}
    monkeypatch.setattr('app.account_overview', lambda *args: (overview, None))
    monkeypatch.setattr('app.find_messaging_service_for_number', lambda *args: None)
    monkeypatch.setattr('app.create_messaging_service', lambda *args: ('MG123', None))
    page = client.get('/twilio-setup')
    assert page.status_code == 200
    assert 'Connect SMS automatically' in page.text
    response = post(client, '/twilio-setup/messaging-service', {
        'phone_number_sid': 'PN' + '1' * 32})
    assert response.status_code == 302
    with app.app_context():
        setting = db.session.get(core_module.OrganizationSetting,
                                 'twilio_messaging_service_sid')
        assert setting.value == 'MG123'


def test_twilio_test_message_shows_actual_delivery_status(monkeypatch):
    app, client, _ = setup_workspace(monkeypatch)
    sid = 'SM' + 'a' * 32
    overview = {
        'account': {'friendly_name': 'Yazory', 'status': 'active', 'type': 'Full'},
        'numbers': [], 'services': [], 'whatsapp_senders': [], 'warnings': []}
    monkeypatch.setattr('app.account_overview', lambda *args: (overview, None))
    monkeypatch.setattr('app.deliver_message', lambda *args, **kwargs: (sid, None))
    monkeypatch.setattr('app.message_status', lambda *args: ({
        'sid': sid, 'status': 'undelivered', 'error_code': 30034,
        'error_message': 'US A2P registration required',
        'to': '+18455551212', 'from': '+12513063232'}, None))

    response = post(client, '/twilio-setup/test-message', {
        'channel': 'sms', 'recipient_phone': '8455551212'})
    assert response.status_code == 302
    page = client.get('/twilio-setup')
    assert 'Undelivered' in page.text
    assert '30034' in page.text
    assert 'US A2P registration required' in page.text


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
