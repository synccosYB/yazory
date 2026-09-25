from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app_entry import create_app
from app import StaffTask, SupporterCommunication
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


def test_callback_later_today_appears_in_later_roster():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'same-day-roster-test'})
    with app.app_context():
        admin = StaffUser(email='admin@sameday.test', password_hash='x',
                          role='organization_admin')
        family = Family(name='Same-day family')
        db.session.add_all([admin, family])
        db.session.flush()
        contact = Contact(family_id=family.id, name='Afternoon helper',
                          relationship='Friend', status='To contact')
        db.session.add(contact)
        db.session.commit()
        admin_id, family_id, contact_id = admin.id, family.id, contact.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['csrf'] = 'same-day-csrf'
    later = datetime.now(ZoneInfo('America/New_York')) + timedelta(hours=1)
    url = f'/families/{family_id}/helpers/work'
    response = client.post(f'/contacts/{contact_id}/communications/callback', data={
        'csrf': 'same-day-csrf', 'return_to': 'case_roster',
        'scheduled_for': later.strftime('%Y-%m-%dT%H:%M')})
    assert response.status_code == 302
    if later.date() == datetime.now(ZoneInfo('America/New_York')).date():
        assert b'Afternoon helper' not in client.get(url).data
    assert b'Afternoon helper' in client.get(url + '?section=later').data


def test_helper_picker_filters_and_keeps_selection_after_work():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'picker-test'})
    with app.app_context():
        admin = StaffUser(email='admin@picker.test', password_hash='x',
                          role='organization_admin')
        family = Family(name='Picker family')
        db.session.add_all([admin, family])
        db.session.flush()
        first = Contact(family_id=family.id, name='Shul friend',
                        relationship='Shul friend', status='To contact')
        second = Contact(family_id=family.id, name='Brother',
                         relationship='Sibling', status='To contact')
        db.session.add_all([first, second])
        db.session.commit()
        admin_id, family_id, first_id = admin.id, family.id, first.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['csrf'] = 'picker-csrf'
    url = f'/families/{family_id}/helpers/work'
    picker = client.get(url + '?section=choose&relationship=Shul+friend')
    assert b'Shul friend' in picker.data and b'Brother' not in picker.data
    assert client.post(url, data={'csrf': 'picker-csrf',
                                  'contact_ids': str(first_id)}).status_code == 302
    page = client.get(url)
    assert b'Shul friend' in page.data and b'Brother' not in page.data
    future = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%dT12:00')
    client.post(f'/contacts/{first_id}/communications/callback', data={
        'csrf': 'picker-csrf', 'return_to': 'case_roster',
        'scheduled_for': future})
    assert b'Shul friend' not in client.get(url).data
    assert b'Shul friend' in client.get(url + '?section=later').data
    assert b'Brother' not in client.get(url + '?section=later').data
    assert client.post(url, data={'csrf': 'picker-csrf', 'mode': 'all'}).status_code == 302
    assert b'Brother' in client.get(url).data


def test_completed_call_without_notes_leaves_ready_roster():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'call-roster-test'})
    with app.app_context():
        admin = StaffUser(email='admin@call-roster.test', password_hash='x',
                          role='organization_admin')
        family = Family(name='Call roster family')
        db.session.add_all([admin, family])
        db.session.flush()
        contact = Contact(family_id=family.id, name='Called helper',
                          relationship='Shul friend', status='To contact')
        db.session.add(contact)
        db.session.commit()
        admin_id, family_id, contact_id = admin.id, family.id, contact.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['csrf'] = 'call-roster-csrf'
    url = f'/families/{family_id}/helpers/work'
    for language in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        assert b'Called helper' in client.get(url).data
    response = client.post(f'/contacts/{contact_id}/communications/call', data={
        'csrf': 'call-roster-csrf', 'return_to': 'case_roster',
        'outreach_status': 'No answer', 'note': ''})
    assert response.status_code == 302 and response.location.endswith(url)
    for language in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        assert b'Called helper' not in client.get(url).data
        assert b'Called helper' in client.get(url + '?section=finished').data
    with app.app_context():
        task = db.session.scalar(db.select(StaffTask).where(
            StaffTask.source_contact_id == contact_id))
        assert task.status == 'Completed' and task.outcome == 'No answer'


def test_completed_call_with_future_followup_stays_in_later_roster():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'followup-roster-test'})
    with app.app_context():
        admin = StaffUser(email='admin@followup.test', password_hash='x',
                          role='organization_admin')
        family = Family(name='Follow-up family')
        db.session.add_all([admin, family])
        db.session.flush()
        contact = Contact(family_id=family.id, name='Follow-up helper',
                          relationship='Friend', status='To contact')
        db.session.add(contact)
        db.session.commit()
        admin_id, family_id, contact_id = admin.id, family.id, contact.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['csrf'] = 'followup-csrf'
    due = (datetime.now(ZoneInfo('America/New_York')) + timedelta(days=3)).date()
    response = client.post(f'/contacts/{contact_id}/communications/call', data={
        'csrf': 'followup-csrf', 'return_to': 'case_roster',
        'outreach_status': 'Contacted', 'followup_title': 'Call back',
        'followup_due_date': due.isoformat()})
    assert response.status_code == 302
    url = f'/families/{family_id}/helpers/work'
    assert b'Follow-up helper' not in client.get(url).data
    assert b'Follow-up helper' in client.get(url + '?section=later').data


def test_due_date_without_task_title_creates_callback_followup():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'date-only-followup-test'})
    with app.app_context():
        admin = StaffUser(email='admin@dateonly.test', password_hash='x',
                          role='organization_admin')
        family = Family(name='Date-only family')
        db.session.add_all([admin, family])
        db.session.flush()
        contact = Contact(family_id=family.id, name='Call later helper',
                          relationship='Friend', status='To contact')
        db.session.add(contact)
        db.session.commit()
        admin_id, family_id, contact_id = admin.id, family.id, contact.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['csrf'] = 'date-only-csrf'
    due = (datetime.now(ZoneInfo('America/New_York')) + timedelta(days=2)).date()
    response = client.post(f'/contacts/{contact_id}/communications/call', data={
        'csrf': 'date-only-csrf', 'return_to': 'case_roster',
        'outreach_status': 'Contacted', 'followup_due_date': due.isoformat()})
    assert response.status_code == 302
    url = f'/families/{family_id}/helpers/work'
    assert b'Call later helper' in client.get(url + '?section=later').data
    with app.app_context():
        parent = db.session.scalar(db.select(StaffTask).where(
            StaffTask.source_contact_id == contact_id))
        assert len(parent.subtasks) == 1
        assert parent.subtasks[0].title == 'Call back: Call later helper'
        assert parent.subtasks[0].due_date == due


def test_helper_can_send_inline_and_see_only_selected_history():
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'helper-message-test'})
    with app.app_context():
        admin = StaffUser(email='admin@messages.test', password_hash='x',
                          role='organization_admin')
        family = Family(name='Message family')
        db.session.add_all([admin, family])
        db.session.flush()
        first = Contact(family_id=family.id, name='First helper',
                        relationship='Friend', status='To contact',
                        cell_phone='3475550199', email='first@example.com')
        second = Contact(family_id=family.id, name='Second helper',
                         relationship='Friend', status='To contact')
        db.session.add_all([first, second])
        db.session.commit()
        admin_id, family_id, first_id, second_id = (
            admin.id, family.id, first.id, second.id)
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['csrf'] = 'message-csrf'
    url = f'/families/{family_id}/helpers/work'
    for language in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        page = client.get(url + f'?contact_id={first_id}')
        assert page.status_code == 200
        assert f'/contacts/{first_id}/communications/message/sms'.encode() in page.data
    response = client.post(f'/contacts/{first_id}/communications/message/sms', data={
        'csrf': 'message-csrf', 'return_to': 'case_roster',
        'roster_section': 'ready', 'body': 'Checking in today'})
    assert response.status_code == 302
    assert f'contact_id={first_id}' in response.location
    assert b'Checking in today' in client.get(response.location).data
    assert b'Checking in today' not in client.get(url + f'?contact_id={second_id}').data
    with app.app_context():
        record = db.session.scalar(db.select(SupporterCommunication).where(
            SupporterCommunication.contact_id == first_id))
        assert record.kind == 'sms' and record.body == 'Checking in today'
