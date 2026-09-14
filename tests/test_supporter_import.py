from app_entry import create_app
from io import BytesIO

import pytest
from sqlalchemy import event

from app import Contact, Family, SupporterProfile, db


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test-only'})


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def test_csv_import_uses_phone_as_unique_identity(app, client):
    data = (
        'Name,Phone,Email\n'
        'First Name,(845) 555-1200,first@example.test\n'
        'Duplicate Name,845-555-1200,duplicate@example.test\n'
        'Missing Phone,,nobody@example.test\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'contacts.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    assert 'New profiles' in response.text
    assert 'Duplicates found' in response.text
    assert 'Rows skipped' in response.text
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8455551200')).all()
        assert len(rows) == 1
        assert rows[0].name == 'First Name'


def test_imported_profile_connects_once_to_a_case(app, client):
    with app.app_context():
        profile = SupporterProfile(name='Imported Person', phone='845-555-1300',
                                   normalized_phone='8455551300',
                                   email='person@example.test')
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))
    path = f'/supporter-directory/{profile_id}/connect'
    payload = {'csrf': csrf(client), 'family_id': str(family_id), 'relationship': 'Friend'}
    first = client.post(path, data=payload)
    second = client.post(path, data=payload)
    assert first.status_code == 302 and '/contacts/' in first.headers['Location']
    assert second.status_code == 302
    with app.app_context():
        contacts = db.session.scalars(db.select(Contact).where(
            Contact.family_id == family_id,
            Contact.supporter_key == 'phone:8455551300')).all()
        assert len(contacts) == 1
        assert contacts[0].email == 'person@example.test'
        link_model = app.extensions['workflows']['models']['SupporterLink']
        link = db.session.get(link_model, contacts[0].id)
        assert link is not None
        assert link.side == 'Community'
        assert link.relationship == 'Friend'

    case_page = client.get(f'/families/{family_id}')
    assert case_page.status_code == 200
    assert 'Imported Person' in case_page.text

def test_wide_contact_export_uses_local_name_and_first_available_phone(app, client):
    data = (
        'Account #,English Name,Yiddish/Hebrew Name,Phone 1,Phone 2,Phone 3,Email 1,Email 2\n'
        '260,Zvi Hersh Gold,צבי הירש גאלד,8456375221,8452389207,,gold@example.test,\n'
        '695,Yakov Schwerts,יעקב שווארטץ,,8455551919,,,second@example.test\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'wide-contacts.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    with app.app_context():
        first = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8456375221'))
        fallback = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8455551919'))
        assert first.name == 'צבי הירש גאלד'
        assert first.email == 'gold@example.test'
        assert fallback.name == 'יעקב שווארטץ'
        assert fallback.email == 'second@example.test'


def test_large_import_checks_existing_profiles_in_bulk(app, client):
    token = csrf(client)
    rows = ['Name,Phone,Email'] + [
        f'Person {number},845555{number:04d},person{number}@example.test'
        for number in range(1000)
    ]
    profile_selects = []

    def count_profile_selects(_conn, _cursor, statement, _parameters, _context, _many):
        normalized = statement.lower().lstrip()
        if normalized.startswith('select') and 'supporter_profile' in normalized:
            profile_selects.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', count_profile_selects)
        try:
            response = client.post('/supporter-directory', data={
                'csrf': token,
                'file': (BytesIO(('\n'.join(rows) + '\n').encode()), 'large.csv'),
            }, content_type='multipart/form-data')
        finally:
            event.remove(db.engine, 'before_cursor_execute', count_profile_selects)

    assert response.status_code == 200
    assert len(profile_selects) <= 3



def test_edit_imported_profile_updates_connected_cases(app, client):
    with app.app_context():
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))
        profile = SupporterProfile(
            name='Old Name', phone='845-555-2100',
            normalized_phone='8455552100', email='old@example.test')
        contact = Contact(
            family_id=family_id, name='Old Name', phone='845-555-2100',
            cell_phone='845-555-2100', email='old@example.test',
            relationship='Friend', supporter_key='phone:8455552100')
        db.session.add_all([profile, contact])
        db.session.commit()
        profile_id = profile.id
        contact_id = contact.id

    response = client.post(f'/supporter-directory/{profile_id}/edit', data={
        'csrf': csrf(client), 'name': 'New Name', 'phone': '(845) 555-2200',
        'email': 'new@example.test'})
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.get(SupporterProfile, profile_id)
        contact = db.session.get(Contact, contact_id)
        assert (profile.name, profile.normalized_phone, profile.email) == (
            'New Name', '8455552200', 'new@example.test')
        assert (contact.name, contact.phone, contact.cell_phone, contact.email,
                contact.supporter_key) == (
            'New Name', '(845) 555-2200', '(845) 555-2200',
            'new@example.test', 'phone:8455552200')


def test_edit_imported_profile_rejects_duplicate_phone(app, client):
    with app.app_context():
        first = SupporterProfile(
            name='First', phone='845-555-2300',
            normalized_phone='8455552300', email='')
        second = SupporterProfile(
            name='Second', phone='845-555-2400',
            normalized_phone='8455552400', email='')
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id

    response = client.post(f'/supporter-directory/{first_id}/edit', data={
        'csrf': csrf(client), 'name': 'First', 'phone': '845-555-2400',
        'email': ''})
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(SupporterProfile, first_id).normalized_phone == '8455552300'
