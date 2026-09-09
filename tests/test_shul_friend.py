import pytest

from app import Contact, Family, create_app, db


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


def test_shul_friend_is_a_distinct_supported_relationship(app, client):
    assert post(client, '/families/new', {'name': 'Shul friend test family'}).status_code == 302
    with app.app_context():
        family_id = db.session.scalar(
            db.select(Family.id).where(Family.name == 'Shul friend test family')
        )

    client.get('/language/yi')
    page = client.get(f'/supporters?family_id={family_id}')
    assert page.status_code == 200
    assert 'חבר פון שול' in page.text

    response = post(client, f'/families/{family_id}/contacts', {
        'name': 'Shul friend test supporter',
        'relationship': 'Shul friend',
        'status': 'To contact',
        'monthly': '0',
    })
    assert response.status_code == 302

    with app.app_context():
        supporter = db.session.scalar(
            db.select(Contact).where(Contact.name == 'Shul friend test supporter')
        )
        assert supporter is not None
        assert supporter.relationship == 'Shul friend'
