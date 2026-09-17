from app_entry import create_app
import pytest

from app import Child, Contact, Family, Institution, PersonAffiliation, db


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
    # Applicant filtering remains available without creating a second network.
    assert 'name="family_id"' in page

    with app.app_context():
        second_id = db.session.scalar(db.select(Family.id).where(
            Family.name == 'Second Applicant'))
    for selected_family_id in (1, second_id):
        filtered = client.get(
            f'/community-directories?kind=Shul&family_id={selected_family_id}'
        ).get_data(as_text=True)
        assert 'Shared Supporter' in filtered
        assert 'Second Applicant' in filtered
        assert 'Sample family' in filtered


def test_directory_only_renders_one_network_workspace(app, client):
    with app.app_context():
        first = Institution(kind='Shul', name='First shul')
        second = Institution(kind='Shul', name='Second shul')
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id

    index = client.get('/community-directories?kind=Shul').get_data(as_text=True)
    assert index.count('Connect an existing person') == 1
    assert index.count('name="institution_id"') == 1

    selected = client.get(
        f'/community-directories?kind=Shul&network_id={first_id}'
    ).get_data(as_text=True)
    assert selected.count('Connect an existing person') == 1
    assert selected.count('name="institution_id"') == 1


def test_directory_spouse_relationship_names_both_connections(app, client):
    with app.app_context():
        family = db.session.get(Family, 1)
        child = Child(family_id=family.id, name='Applicant daughter', age=25,
                      grade='', school='', married=True,
                      spouse_name='Applicant son in law')
        shul = Institution(kind='Shul', name='Relationship shul')
        db.session.add_all([child, shul])
        db.session.flush()
        db.session.add_all([
            PersonAffiliation(institution_id=shul.id, person_type='family',
                              person_id=family.id),
            PersonAffiliation(institution_id=shul.id, person_type='child_spouse',
                              person_id=child.id),
        ])
        db.session.commit()
        shul_id = shul.id

    page = client.get(
        f'/community-directories?kind=Shul&network_id={shul_id}'
    ).get_data(as_text=True)
    assert 'Spouse of Applicant daughter' in page
    assert 'Son-in-law or daughter-in-law of Sample family' in page


def test_directory_new_copy_is_translated_to_yiddish(app, client):
    with app.app_context():
        shul = Institution(kind='Shul', name='אידישע שול')
        db.session.add(shul)
        db.session.commit()
        shul_id = shul.id

    client.get('/language/yi')
    page = client.get(
        f'/community-directories?kind=Shul&network_id={shul_id}'
    ).get_data(as_text=True)
    for english in (
        'One shared network.', 'Find a network', 'Master directory',
        'Applicants connected here', 'People in this network',
        'Connect an existing person', 'Create new supporters in Supporters',
        '>Open<', '>Remove<', '>Add<', '>Clear<',
    ):
        assert english not in page
