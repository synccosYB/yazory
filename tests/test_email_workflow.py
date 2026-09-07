import re

from werkzeug.security import generate_password_hash

from app import (AccountToken, EmailMessage, Family, FamilyAssignment, StaffUser,
                 create_app, db)


def post(client, path, data):
    public_form = (path == '/forgot-password' or path.startswith('/accept-invitation/')
                   or path.startswith('/reset-password/'))
    client.get(path if public_form else '/')
    with client.session_transaction() as session:
        token = session['csrf']
    return client.post(path, data={**data, 'csrf': token})


def app_and_owner(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test', 'DEMO': False, 'ADMIN_EMAIL': 'owner@example.test',
        'ADMIN_PASSWORD_HASH': generate_password_hash('owner-password-123')})
    client = app.test_client()
    client.get('/login')
    with client.session_transaction() as session:
        csrf = session['csrf']
    assert client.post('/login', data={'csrf': csrf, 'email': 'owner@example.test',
        'password': 'owner-password-123'}).status_code == 302
    return app, client


def link_from(message):
    return re.search(r'https?://[^\s]+', message.text_body).group(0).replace('http://localhost', '')


def test_invitation_acceptance_is_single_use(monkeypatch):
    app, owner = app_and_owner(monkeypatch)
    response = post(owner, '/people-access', {'name': 'Family Admin',
        'email': 'new@example.test', 'role': 'family_admin'})
    assert response.status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'new@example.test'))
        message = db.session.scalar(db.select(EmailMessage).where(EmailMessage.kind == 'staff_invitation'))
        assert user.status == 'pending' and user.password_hash == '!invited'
        assert message.status == 'preview'
        path = link_from(message)
        user_id = user.id
    guest = app.test_client()
    assert guest.get(path).status_code == 200
    accepted = post(guest, path, {'name': 'Accepted Name', 'password': 'secure-password-123',
                                  'password_confirmation': 'secure-password-123'})
    assert accepted.status_code == 302
    assert guest.get(path).status_code == 400
    with app.app_context():
        user = db.session.get(StaffUser, user_id)
        assert user.status == 'active' and user.name == 'Accepted Name' and user.activated_at
    guest.get('/login')
    with guest.session_transaction() as session:
        csrf = session['csrf']
    assert guest.post('/login', data={'csrf': csrf, 'email': 'new@example.test',
        'password': 'secure-password-123'}).status_code == 302


def test_reset_deactivation_and_assignment_notifications(monkeypatch):
    app, owner = app_and_owner(monkeypatch)
    assert post(owner, '/staff', {'email': 'staff@example.test', 'role': 'office_employee',
        'password': 'initial-password-123'}).status_code == 302
    assert post(owner, '/families/new', {'name': 'Assigned household'}).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'staff@example.test'))
        family = db.session.scalar(db.select(Family).where(Family.name == 'Assigned household'))
        user_id, family_id = user.id, family.id
    assert post(owner, f'/staff/{user_id}/assignments', {'family_id': family_id}).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(FamilyAssignment).where(
            FamilyAssignment.staff_user_id == user_id, FamilyAssignment.family_id == family_id))
        assert db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'family_assignment')).status == 'preview'

    guest = app.test_client()
    response = post(guest, '/forgot-password', {'email': 'staff@example.test'})
    assert response.status_code == 302
    with app.app_context():
        reset = db.session.scalar(db.select(EmailMessage).where(EmailMessage.kind == 'password_reset'))
        path = link_from(reset)
    assert post(guest, path, {'password': 'replacement-pass-123',
        'password_confirmation': 'replacement-pass-123'}).status_code == 302
    assert guest.get(path).status_code == 400

    assert post(owner, f'/staff/{user_id}/status', {'status': 'deactivated'}).status_code == 302
    login = app.test_client()
    login.get('/login')
    with login.session_transaction() as session:
        csrf = session['csrf']
    denied = login.post('/login', data={'csrf': csrf, 'email': 'staff@example.test',
        'password': 'replacement-pass-123'})
    assert denied.status_code == 200


def test_unknown_reset_email_does_not_disclose_account(monkeypatch):
    app, _ = app_and_owner(monkeypatch)
    guest = app.test_client()
    response = post(guest, '/forgot-password', {'email': 'missing@example.test'})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(AccountToken)) == 0
