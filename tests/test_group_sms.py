import pytest
from app_entry import create_app
from app import SupporterCommunication
from app_original import Contact, Family, StaffUser, db


@pytest.fixture
def group_setup():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'group-test'})
    with app.app_context():
        admin = StaffUser(email='admin@group.test', password_hash='x', role='organization_admin')
        outsider = StaffUser(email='outside@group.test', password_hash='x', role='fundraiser')
        family = Family(name='Group family')
        db.session.add_all([admin, outsider, family]); db.session.flush()
        contacts = [Contact(family_id=family.id, name=name, relationship='Friend',
                            status='To contact', cell_phone=phone)
                    for name, phone in [('First', '8455551212'), ('Shared', '+18455551212'),
                                        ('Other', '8455551213'), ('Missing', '')]]
        db.session.add_all(contacts); db.session.commit()
        values = admin.id, outsider.id, family.id, [c.id for c in contacts]
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=values[0], csrf='csrf', group_sms_token='once')
    return app, client, values


def test_group_history_shared_phone_missing_and_repeat(group_setup):
    app, client, (_, _, family_id, ids) = group_setup
    data = {'csrf': 'csrf', 'group_sms_token': 'once', 'contact_ids': ids + [ids[0]],
            'body': 'Hello group', 'family_id': family_id}
    response = client.post('/communications/group-sms', data=data)
    assert response.status_code == 302
    assert response.location.endswith(f'/families/{family_id}/helpers/work')
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterCommunication)).all()
        assert {r.contact_id for r in rows} == set(ids[:3])
        assert all(r.status == 'preview' and 'Hello group' in r.body for r in rows)
    assert client.post('/communications/group-sms', data=data).status_code == 400


def test_group_checks_every_permission_before_sending(group_setup):
    app, client, (_, outsider_id, _, ids) = group_setup
    with client.session_transaction() as session:
        session['user_id'] = outsider_id
    assert client.post('/communications/group-sms', data={
        'csrf': 'csrf', 'group_sms_token': 'once', 'contact_ids': ids[:2],
        'body': 'Hello'}).status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(SupporterCommunication)) == 0


def test_group_private_delivery_once_per_number_and_failures(group_setup, monkeypatch):
    app, client, (_, _, _, ids) = group_setup
    calls = []
    def deliver(*args, **kwargs):
        calls.append(args[2])
        return ('SMfirst', '') if len(calls) == 1 else (None, 'Delivery error')
    monkeypatch.setattr('app.deliver_message', deliver)
    app.config['TESTING'] = False
    app.config['TWILIO_MESSAGING_SERVICE_SID'] = 'MGtest'
    assert client.post('/communications/group-sms', data={
        'csrf': 'csrf', 'group_sms_token': 'once', 'contact_ids': ids[:3],
        'body': 'Hello'}).status_code == 302
    assert calls == ['+18455551212', '+18455551213']
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterCommunication).order_by(SupporterCommunication.id)).all()
        assert [r.status for r in rows] == ['completed', 'completed', 'failed']
        assert rows[-1].delivery_error == 'Delivery error'


def test_group_controls_in_all_locales(group_setup):
    _, client, (_, _, family_id, _) = group_setup
    for language in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        for url in ('/communications', f'/families/{family_id}/helpers/work'):
            response = client.get(url)
            assert response.status_code == 200
            assert b'/communications/group-sms' in response.data
