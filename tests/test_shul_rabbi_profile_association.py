import pytest

from app import FamilyRabbiConnection, Institution, create_app, db


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test-only',
    })


@pytest.fixture
def client(app):
    return app.test_client()


def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf': csrf})


def test_profile_inherits_single_rabbi_from_selected_shul(app, client):
    with app.app_context():
        db.session.add(Institution(kind='Shul', name='Profile Test Shul', city='Monroe'))
        db.session.commit()

    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'shabbos_shul': 'Profile Test Shul',
        'shabbos_shul_rabbi': 'Rabbi Profile',
        'shabbos_shul_rabbi_phone': '845-555-7001',
    })
    assert response.status_code == 302

    with app.app_context():
        from app import Family

        family = db.session.get(Family, 1)
        assert family.rabbi == 'Rabbi Profile'
        assert family.rabbi_phone == '845-555-7001'

        affiliated = db.session.scalar(db.select(FamilyRabbiConnection).where(
            FamilyRabbiConnection.family_id == 1,
            FamilyRabbiConnection.role == 'affiliated',
        ))
        assert affiliated is not None
        assert affiliated.rabbi_name == 'Rabbi Profile'
        assert affiliated.rabbi_phone == '845-555-7001'
        assert affiliated.institution is not None
        assert affiliated.institution.name == 'Profile Test Shul'
