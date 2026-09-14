import hashlib

import pytest

from app import Family, FamilyAssignment, StaffUser, db
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
