from datetime import datetime, timedelta

from app_entry import create_app
from app import StaffTask
from app_original import Contact, Family, FamilyAssignment, StaffUser, db


def test_case_roster_moves_future_callbacks_and_scopes_case_access():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'roster-test'})
    with app.app_context():
        admin = StaffUser(email='admin@roster.test', password_hash='x',
                          role='organization_admin')
        outsider = StaffUser(email='outside@roster.test', password_hash='x',
                             role='family_admin')
        family = Family(name='Roster family')
        db.session.add_all([admin, outsider, family])
        db.session.flush()
        contact = Contact(family_id=family.id, name='Roster helper',
                          relationship='Friend', status='To contact')
        db.session.add(contact)
        db.session.commit()
        admin_id, outsider_id = admin.id, outsider.id
        family_id, contact_id = family.id, contact.id

    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = outsider_id
        session['csrf'] = 'roster-csrf'
    assert client.get(f'/families/{family_id}/helpers/work').status_code == 403

    with client.session_transaction() as session:
        session['user_id'] = admin_id
    url = f'/families/{family_id}/helpers/work'
    assert b'Roster helper' in client.get(url).data
    future = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%dT12:00')
    response = client.post(f'/contacts/{contact_id}/communications/callback', data={
        'csrf': 'roster-csrf', 'return_to': 'case_roster',
        'scheduled_for': future, 'note': 'Call on the chosen date'})
    assert response.status_code == 302 and response.location.endswith(url)
    assert b'Roster helper' not in client.get(url).data
    assert b'Roster helper' in client.get(url + '?section=later').data
    with app.app_context():
        task = db.session.scalar(db.select(StaffTask).where(
            StaffTask.source_contact_id == contact_id))
        assert task.due_date == datetime.strptime(future, '%Y-%m-%dT%H:%M').date()

    for language in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        page = client.get(url + '?section=later')
        assert page.status_code == 200 and b'Roster helper' in page.data
