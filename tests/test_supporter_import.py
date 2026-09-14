from app_entry import create_app
from io import BytesIO

import pytest

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
