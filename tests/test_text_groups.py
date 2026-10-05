import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import MultiDict

from app_entry import create_app
from app import SupporterCommunication
from app_original import Contact, Family, FamilyAssignment, StaffUser, db
from text_groups import TextGroup, TextGroupMessage, create_conversation
from notifications import StaffActivityCursor


@pytest.fixture
def workspace():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'shared-group',
                      'TWILIO_GROUP_MMS_FROM': '+18454600117',
                      'TWILIO_AUTH_TOKEN': 'signature-secret', 'TWILIO_ACCOUNT_SID': 'AC' + 'a' * 32,
                      'APP_BASE_URL': 'https://yaazory.org'})
    with app.app_context():
        admin = StaffUser(email='admin@groups.test', password_hash='x', role='organization_admin')
        helper = StaffUser(email='helper@groups.test', password_hash='x', role='family_admin')
        family = Family(name='First case')
        other = Family(name='Other case')
        db.session.add_all([admin, helper, family, other]); db.session.flush()
        contacts = [Contact(name='Helper ' + str(i), family_id=family.id if i < 9 else other.id,
                            relationship='Friend', status='To contact', cell_phone=f'845555{1200+i}') for i in range(10)]
        db.session.add_all(contacts)
        db.session.add(FamilyAssignment(family_id=family.id, staff_user_id=helper.id))
        db.session.commit()
        for user in (admin, helper):
            db.session.add(StaffActivityCursor(staff_user_id=user.id, last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)))
        db.session.commit()
        values = admin.id, helper.id, family.id, other.id, [contact.id for contact in contacts]
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=values[0], csrf='csrf')
    return app, client, values


def create_group(client, ids, **values):
    return client.post('/communications/text-groups', data=dict(
        csrf='csrf', name='Family helpers', contact_ids=ids, **values))


def signature(params):
    url = 'https://yaazory.org/twilio/text-groups/webhook'
    value = url + ''.join(key + val for key in sorted(params) for val in sorted(params.getlist(key)))
    return base64.b64encode(hmac.new(b'signature-secret', value.encode(), hashlib.sha1).digest()).decode()


def test_group_preview_persistence_and_private_bulk_labels(workspace):
    app, client, (_, _, family_id, _, ids) = workspace
    response = create_group(client, ids[:2], family_id=family_id)
    assert response.status_code == 302
    with app.app_context():
        group = db.session.scalar(db.select(TextGroup))
        assert group.name == 'Family helpers' and group.state == 'preview'
        assert len(group.members) == 2
        group_id = group.id
    assert create_group(client, ids[:2], family_id=family_id).location == response.location
    page = client.get(response.location)
    assert 'Message to everyone' in page.text
    with client.session_transaction() as session:
        key = session[f'text_group_send:{group_id}']
    data = dict(csrf='csrf', send_key=key, body='Talk together')
    assert client.post(response.location, data=data).status_code == 302
    # A stale cookie/token replay still cannot send again: database reservation is unique.
    with client.session_transaction() as session:
        session[f'text_group_send:{group_id}'] = key
    assert client.post(response.location, data=data).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(TextGroupMessage)) == 1
        history = db.session.scalars(db.select(SupporterCommunication)).all()
        assert len(history) == 2 and all(row.kind == 'group_mms' for row in history)
    assert 'Private group text' in client.get('/communications').text


@pytest.mark.parametrize('count', [0, 1, 10])
def test_group_member_limits(workspace, count):
    app, client, (_, _, _, _, ids) = workspace
    assert create_group(client, ids[:count]).status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(TextGroup)) == 0


def test_group_rejects_missing_duplicate_and_non_us_numbers(workspace):
    app, client, (_, _, _, _, ids) = workspace
    for invalid_phone in ('', '+442071234567', '8455551200'):
        with app.app_context():
            db.session.get(Contact, ids[1]).cell_phone = invalid_phone
            db.session.commit()
        assert create_group(client, ids[:2]).status_code == 400


def test_group_checks_all_members_and_csrf_before_any_provider_request(workspace, monkeypatch):
    app, client, (_, helper_id, family_id, _, ids) = workspace
    monkeypatch.setattr('text_groups.create_conversation', lambda *args: pytest.fail('Unauthorized provider call'))
    with client.session_transaction() as session:
        session['user_id'] = helper_id
    assert create_group(client, [ids[0], ids[-1]]).status_code == 403
    assert create_group(client, ids[:2], family_id=999).status_code == 400
    assert client.post('/communications/text-groups', data={'name': 'No CSRF', 'contact_ids': ids[:2]}).status_code == 400
    response = create_group(client, ids[:2], family_id=family_id)
    assert response.status_code == 302
    with app.app_context():
        assignment = db.session.scalar(db.select(FamilyAssignment).where(FamilyAssignment.staff_user_id == helper_id))
        db.session.delete(assignment); db.session.commit()
    assert client.get(response.location).status_code == 403


def test_atomic_provider_request_uses_projected_address_not_private_proxy(monkeypatch):
    calls = []
    def request(method, url, account, token, **kwargs):
        calls.append((method, url, kwargs))
        return {'sid': 'CH' + 'a' * 32, 'state': 'initializing'}, None
    monkeypatch.setattr('text_groups._request', request)
    result, error = create_conversation('AC', 'secret', 'Helpers', '+18454600117',
                                        ['+18455551200', '+18455551201'], 'unique', 'MGtest')
    assert not error
    assert calls[0][1].endswith('/ConversationWithParticipants')
    participants = [json.loads(value) for key, value in calls[0][2]['data'] if key == 'Participant']
    assert participants == [
        {'messaging_binding': {'address': '+18455551200'}},
        {'messaging_binding': {'address': '+18455551201'}},
        {'messaging_binding': {'projected_address': '+18454600117'}}]


def test_group_live_initialization_then_send_and_failed_send_history(workspace, monkeypatch):
    app, client, (_, _, _, _, ids) = workspace
    app.config['TESTING'] = False
    state = ['initializing']
    calls = []
    monkeypatch.setattr('text_groups.create_conversation', lambda *args: ({'sid': 'CH' + 'a' * 32, 'state': 'initializing'}, None))
    monkeypatch.setattr('text_groups.conversation_status', lambda *args: ({'state': state[0]}, None))
    monkeypatch.setattr('text_groups.attach_webhook', lambda *args: (calls.append(('webhook', args[-1])) or {'sid': 'WH'}, None))
    def send(*args):
        calls.append(('send', args[-1]))
        return {'sid': 'IM' + 'b' * 32}, None
    monkeypatch.setattr('text_groups.send_message', send)
    response = create_group(client, ids[:2])
    assert response.status_code == 302
    assert 'Finish group setup' in client.get(response.location).text
    assert not calls
    state[0] = 'active'
    assert client.post(response.location, data={'csrf': 'csrf', 'action': 'setup'}).status_code == 302
    assert calls == [('webhook', 'https://yaazory.org/twilio/text-groups/webhook')]
    client.get(response.location)
    with client.session_transaction() as session:
        key = session['text_group_send:1']
    assert client.post(response.location, data={'csrf': 'csrf', 'send_key': key, 'body': 'Hello everyone'}).status_code == 302
    assert len([call for call in calls if call[0] == 'send']) == 1
    with app.app_context():
        message = db.session.scalar(db.select(TextGroupMessage))
        assert message.status == 'sent' and message.provider_sid == 'IM' + 'b' * 32
    monkeypatch.setattr('text_groups.send_message', lambda *args: (None, 'Provider failure'))
    client.get(response.location)
    with client.session_transaction() as session:
        key = session['text_group_send:1']
    client.post(response.location, data={'csrf': 'csrf', 'send_key': key, 'body': 'Second'})
    with app.app_context():
        message = db.session.scalar(db.select(TextGroupMessage).order_by(TextGroupMessage.id.desc()))
        assert message.status == 'failed' and message.error == 'Provider failure'


def test_signed_reply_archived_once_without_rebroadcast(workspace, monkeypatch):
    app, client, (_, _, _, _, ids) = workspace
    response = create_group(client, ids[:2])
    with app.app_context():
        group = db.session.scalar(db.select(TextGroup)); group.conversation_sid = 'CH' + 'a' * 32
        db.session.commit()
    client = app.test_client()  # Public callback must work without staff session or CSRF.
    params = MultiDict(dict(EventType='onMessageAdded', ConversationSid='CH' + 'a' * 32,
                       MessageSid='IM' + 'c' * 32, Author='+18455551200', Body='I can help'))
    monkeypatch.setattr('text_groups.send_message', lambda *args: pytest.fail('Do not rebroadcast native replies'))
    assert client.post('/twilio/text-groups/webhook', data=params).status_code == 403
    headers = {'X-Twilio-Signature': signature(params)}
    assert client.post('/twilio/text-groups/webhook', data=params, headers=headers).json == {'received': True}
    assert client.post('/twilio/text-groups/webhook', data=params, headers=headers).json == {'received': True, 'duplicate': True}
    with app.app_context():
        messages = db.session.scalars(db.select(TextGroupMessage)).all()
        assert len(messages) == 1 and messages[0].body == 'I can help'
        history = db.session.scalar(db.select(SupporterCommunication))
        assert history.contact_id == ids[0] and history.direction == 'inbound'


def test_group_pages_translated_and_gets_do_not_write(workspace, monkeypatch):
    app, client, (_, _, family_id, _, ids) = workspace
    response = create_group(client, ids[:2])
    monkeypatch.setattr('text_groups.create_conversation', lambda *args: pytest.fail('No GET provider writes'))
    monkeypatch.setattr('text_groups.attach_webhook', lambda *args: pytest.fail('No GET provider writes'))
    for language, label in [('en', 'Shared text groups'), ('he', 'קבוצות הודעות משותפות'), ('yi', 'געמיינזאמע טעקסט גרופעס')]:
        with client.session_transaction() as session:
            session['language'] = language
        for url in ('/communications/text-groups', response.location, '/communications', f'/families/{family_id}/helpers/work'):
            page = client.get(url)
            assert page.status_code == 200 and label in page.text


def test_shared_inbox_and_notifications_link_to_actual_group(workspace):
    app, client, (admin_id, helper_id, _, _, ids) = workspace
    response = create_group(client, ids[:2])
    with app.app_context():
        group = db.session.scalar(db.select(TextGroup))
        db.session.add(TextGroupMessage(group_id=group.id, provider_sid='IM' + 'd' * 32,
                                       author='Helper 0', direction='inbound', status='received', body='Shared reply'))
        db.session.commit()
    page = client.get('/communications')
    assert 'Shared reply' in page.text and response.location in page.text
    page = client.get('/notifications')
    assert response.location in page.text
    with client.session_transaction() as session:
        session['user_id'] = helper_id
    assert client.get(response.location).status_code == 200
    assert 'Family helpers' in client.get('/communications/text-groups').text
    with app.app_context():
        assignment = db.session.scalar(db.select(FamilyAssignment).where(FamilyAssignment.staff_user_id == helper_id))
        db.session.delete(assignment); db.session.commit()
    assert 'Shared reply' not in client.get('/communications').text
    assert 'Shared reply' not in client.get('/notifications').text
    assert client.post(response.location, data={'csrf': 'csrf', 'action': 'setup'}).status_code == 403


def test_sender_validation_and_nine_people_supported(workspace):
    app, client, (_, _, _, _, ids) = workspace
    app.config['TWILIO_GROUP_MMS_FROM'] = '+18005551234'
    assert create_group(client, ids[:2]).status_code == 400
    app.config['TWILIO_GROUP_MMS_FROM'] = '+18454600117'
    assert create_group(client, ids[:9]).status_code == 302
    with app.app_context():
        group = db.session.scalar(db.select(TextGroup))
        assert len(group.members) == 9


def test_provider_setup_failure_saved_and_retryable(workspace, monkeypatch):
    app, client, (_, _, _, _, ids) = workspace
    app.config['TESTING'] = False
    monkeypatch.setattr('text_groups.create_conversation', lambda *args: (None, 'Conversations unavailable'))
    monkeypatch.setattr('text_groups._request', lambda *args, **kwargs: (None, 'Not found'))
    response = create_group(client, ids[:2])
    assert 'Conversations unavailable' in client.get(response.location).text
    with app.app_context():
        group = db.session.scalar(db.select(TextGroup))
        assert group.state == 'error' and not group.conversation_sid
    monkeypatch.setattr('text_groups.create_conversation', lambda *args: ({'sid': 'CH' + 'a' * 32, 'state': 'initializing'}, None))
    monkeypatch.setattr('text_groups.conversation_status', lambda *args: ({'state': 'active'}, None))
    monkeypatch.setattr('text_groups.attach_webhook', lambda *args: ({'sid': 'WH'}, None))
    assert client.post(response.location, data={'csrf': 'csrf', 'action': 'setup'}).status_code == 302
    with app.app_context():
        group = db.session.scalar(db.select(TextGroup))
        assert group.state == 'active' and not group.error
