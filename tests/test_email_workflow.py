import re

import app as app_module
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


def test_email_html_uses_yazory_brand_and_absolute_logo(monkeypatch):
    app, owner = app_and_owner(monkeypatch)
    app.config['APP_BASE_URL'] = 'https://yazory.example'
    app.config['RESEND_API_KEY'] = 'test-key'
    app.config['EMAIL_FROM'] = 'notifications@synccos.live'
    delivered = {}

    def capture_delivery(api_key, sender, recipient, subject, html, text):
        delivered.update(api_key=api_key, sender=sender, recipient=recipient,
                         subject=subject, html=html, text=text)
        return 'email_123', None

    monkeypatch.setattr(app_module, 'deliver', capture_delivery)
    app.config['TESTING'] = False
    response = post(owner, '/people-access', {'name': 'Family Admin',
        'email': 'brand@example.test', 'role': 'family_admin'})
    assert response.status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.recipient == 'brand@example.test'))
        assert message.status == 'sent'
        # The persisted plain-text version remains suitable for logs and clients
        # that do not display HTML.
        assert 'You have been invited' in message.text_body
    assert delivered['sender'] == 'notifications@synccos.live'
    assert 'background:#f8f7f3' in delivered['html']
    assert 'background:#173e66' in delivered['html']
    assert 'background:#b49a52' in delivered['html']
    assert 'src="https://yazory.example/static/yazory-logo.png"' in delivered['html']
    assert 'Yazory · יעזורי' in delivered['html']
    assert '<a href="https://yazory.example/accept-invitation/' in delivered['html']


def test_staff_details_status_and_delete(monkeypatch):
    app, owner = app_and_owner(monkeypatch)
    assert post(owner, '/staff', {'name': 'Staff Member', 'email': 'staff@example.test',
        'role': 'office_employee', 'password': 'initial-password-123',
        'phone': '845-555-1212', 'address': '10 Main St', 'city': 'Monroe',
        'state': 'NY', 'zip_code': '10950', 'job_title': 'Coordinator'}).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'staff@example.test'))
        user_id = user.id
        assert (user.phone, user.city, user.job_title) == ('845-555-1212', 'Monroe', 'Coordinator')
    page = owner.get('/staff').text
    assert '845-555-1212' in page and '10 Main St' in page and 'Coordinator' in page
    assert 'staff-edit-button' in page
    assert post(owner, f'/staff/{user_id}/details', {'name': 'Updated Staff',
        'email': 'updated@example.test', 'phone': '845-555-3434', 'address': '20 Main St',
        'city': 'Kiryas Joel', 'state': 'NY', 'zip_code': '10950',
        'job_title': 'Manager'}).status_code == 302
    assert post(owner, f'/staff/{user_id}/status', {'status': 'deactivated'}).status_code == 302
    with app.app_context():
        user = db.session.get(StaffUser, user_id)
        assert (user.name, user.email, user.status, user.job_title) == (
            'Updated Staff', 'updated@example.test', 'deactivated', 'Manager')
    assert post(owner, f'/staff/{user_id}/delete', {}).status_code == 302
    with app.app_context():
        assert db.session.get(StaffUser, user_id) is None


def test_owner_staff_account_cannot_be_deleted(monkeypatch):
    app, owner = app_and_owner(monkeypatch)
    with app.app_context():
        user_id = db.session.scalar(db.select(StaffUser.id).where(
            StaffUser.email == 'owner@example.test'))
    assert post(owner, f'/staff/{user_id}/delete', {}).status_code == 400
    with app.app_context():
        assert db.session.get(StaffUser, user_id) is not None
