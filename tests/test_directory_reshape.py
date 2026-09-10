import pytest

from app import Contact, Family, Institution, PersonAffiliation, create_app, db


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


def test_directory_uses_one_shared_network_for_multiple_applicants(app, client):
    with app.app_context():
        second = Family(name='Second Applicant')
        db.session.add(second)
        db.session.flush()
        shul = Institution(kind='Shul', name='Shared Shul', city='Monroe', state='NY')
        db.session.add(shul)
        db.session.flush()
        supporter = Contact(
            family_id=1,
            name='Shared Supporter',
            phone='8455551111',
            relationship='Friend',
            supporter_key='phone:8455551111',
            monthly_cents=0,
            pledge_frequency='Monthly',
            status='To contact',
        )
        db.session.add(supporter)
        db.session.flush()
        db.session.add_all([
            PersonAffiliation(institution_id=shul.id, person_type='family', person_id=1),
            PersonAffiliation(institution_id=shul.id, person_type='family', person_id=second.id),
            PersonAffiliation(institution_id=shul.id, person_type='supporter', person_id=supporter.id),
        ])
        db.session.commit()

    response = client.get('/community-directories?kind=Shul')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Master directory' in page
    assert 'Shared Shul' in page
    assert 'Shared Supporter' in page
    assert 'Second Applicant' in page
    assert 'via' in page
    # The old embedded create-supporter-per-applicant flow is gone.
    assert 'Add and connect person' not in page
    assert 'name="family_id"' not in page
