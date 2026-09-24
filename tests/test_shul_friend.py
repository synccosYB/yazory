from app_entry import create_app
import pytest

from app import Contact, Family, Institution, PersonAffiliation, db


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


def test_shul_friends_join_applicant_network_and_old_rows_are_reconciled(app, client):
    assert post(client, '/families/new', {'name': 'Network applicant'}).status_code == 302
    with app.app_context():
        family_id = db.session.scalar(db.select(Family.id).where(Family.name == 'Network applicant'))
    assert post(client, f'/families/{family_id}/edit', {
        'name': 'Network applicant', 'weekday_shul': 'Beis Dov',
        'shabbos_shul': 'Beis Dov', 'city': 'Monroe', 'state': 'NY',
    }).status_code == 302
    assert post(client, f'/families/{family_id}/contacts', {
        'name': 'New shul friend', 'relationship': 'Shul friend',
        'status': 'To contact', 'monthly': '0',
    }).status_code == 302
    with app.app_context():
        shul = db.session.scalar(db.select(Institution).where(Institution.name == 'Beis Dov'))
        friend = db.session.scalar(db.select(Contact).where(Contact.name == 'New shul friend'))
        assert len(db.session.scalars(db.select(PersonAffiliation).where(
            PersonAffiliation.institution_id == shul.id,
            PersonAffiliation.person_type == 'supporter',
            PersonAffiliation.person_id == friend.id)).all()) == 1
        old = Contact(family_id=family_id, name='Existing shul friend',
                      relationship='Shul friend', status='To contact', monthly_cents=0)
        db.session.add(old)
        db.session.commit()
        shul_id, old_id = shul.id, old.id
    for _ in range(2):
        page = client.get('/community-directories?kind=Shul')
        assert page.status_code == 200
        assert 'Existing shul friend' in page.text
    with app.app_context():
        assert len(db.session.scalars(db.select(PersonAffiliation).where(
            PersonAffiliation.institution_id == shul_id,
            PersonAffiliation.person_type == 'supporter',
            PersonAffiliation.person_id == old_id)).all()) == 1
