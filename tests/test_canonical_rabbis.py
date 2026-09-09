import pathlib

import pytest

import app as app_module
from app import (
    Family,
    FamilyRabbiPreference,
    Institution,
    RabbiPerson,
    ShulRabbi,
    ShulRabbiAssociation,
    create_app,
    db,
)


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH',
                'SESSION_SECRET'):
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


def add_shuls(app):
    with app.app_context():
        rows = [
            Institution(kind='Shul', name='Weekday Canonical Shul', city='Monroe'),
            Institution(kind='Shul', name='Shabbos Canonical Shul', city='Monroe'),
        ]
        db.session.add_all(rows)
        db.session.commit()
        return [row.id for row in rows]


def connect_rabbi(client, shul_id, **data):
    return post(
        client,
        f'/community-directories/shuls/{shul_id}/rabbis',
        data,
    )


def test_one_canonical_person_can_serve_multiple_shuls(app, client):
    weekday_id, shabbos_id = add_shuls(app)
    assert connect_rabbi(
        client, weekday_id, rabbi_name='Rabbi Shared', rabbi_phone='845-555-1000'
    ).status_code == 302
    with app.app_context():
        person_id = db.session.scalar(
            db.select(RabbiPerson.id).where(RabbiPerson.name == 'Rabbi Shared'))
    assert connect_rabbi(client, shabbos_id, rabbi_person_id=str(person_id)).status_code == 302

    with app.app_context():
        people = db.session.scalars(db.select(RabbiPerson).where(
            RabbiPerson.normalized_name == 'rabbi shared')).all()
        links = db.session.scalars(db.select(ShulRabbiAssociation)).all()
        assert [(person.name, person.phone) for person in people] == [
            ('Rabbi Shared', '845-555-1000')]
        assert {link.institution_id for link in links} == {weekday_id, shabbos_id}
        assert all(link.rabbi_person_id == person_id for link in links)


def test_shul_supports_multiple_rabbis_with_one_primary(app, client):
    shul_id, _ = add_shuls(app)
    connect_rabbi(client, shul_id, rabbi_name='Rabbi First')
    connect_rabbi(client, shul_id, rabbi_name='Rabbi Second')
    with app.app_context():
        links = db.session.scalars(db.select(ShulRabbiAssociation).where(
            ShulRabbiAssociation.institution_id == shul_id
        ).order_by(ShulRabbiAssociation.id)).all()
        assert len(links) == 2
        assert [link.is_primary for link in links] == [True, False]
        second_id = links[1].id
    assert post(
        client,
        f'/community-directories/shul-rabbis/{second_id}/primary',
        {},
    ).status_code == 302
    with app.app_context():
        links = db.session.scalars(db.select(ShulRabbiAssociation).where(
            ShulRabbiAssociation.institution_id == shul_id)).all()
        assert sum(link.is_primary for link in links) == 1
        primary = next(link for link in links if link.is_primary)
        assert primary.rabbi_person.name == 'Rabbi Second'
        legacy = db.session.get(ShulRabbi, shul_id)
        assert legacy.rabbi_name == 'Rabbi Second'


def test_family_automatic_rabbi_uses_weekday_then_shabbos(app, client):
    weekday_id, shabbos_id = add_shuls(app)
    connect_rabbi(client, weekday_id, rabbi_name='Rabbi Weekday')
    connect_rabbi(client, shabbos_id, rabbi_name='Rabbi Shabbos')
    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Canonical Shul',
        'shabbos_shul': 'Shabbos Canonical Shul',
        'rabbi_mode': 'automatic',
    })
    assert response.status_code == 302
    with app.app_context():
        family = db.session.get(Family, 1)
        preference = db.session.get(FamilyRabbiPreference, 1)
        assert family.rabbi == 'Rabbi Weekday'
        assert preference.overridden is False
        assert preference.rabbi_person.name == 'Rabbi Weekday'

    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': '',
        'shabbos_shul': 'Shabbos Canonical Shul',
        'rabbi_mode': 'automatic',
    })
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Family, 1).rabbi == 'Rabbi Shabbos'


def test_manual_and_blank_overrides_survive_directory_changes(app, client):
    weekday_id, _ = add_shuls(app)
    connect_rabbi(client, weekday_id, rabbi_name='Rabbi Original')
    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Canonical Shul',
        'rabbi_mode': 'manual',
        'rabbi': 'Rabbi Family Choice',
        'rabbi_phone': '845-555-2000',
    }).status_code == 302
    connect_rabbi(
        client, weekday_id, rabbi_name='Rabbi New Primary', make_primary='1')
    with app.app_context():
        family = db.session.get(Family, 1)
        assert (family.rabbi, family.rabbi_phone) == (
            'Rabbi Family Choice', '845-555-2000')
        assert db.session.get(FamilyRabbiPreference, 1).overridden is True

    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Canonical Shul',
        'rabbi_mode': 'manual',
        'rabbi': '',
        'rabbi_phone': '',
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Family, 1).rabbi == ''
        assert db.session.get(FamilyRabbiPreference, 1).overridden is True


def test_resume_automatic_and_canonical_override(app, client):
    weekday_id, _ = add_shuls(app)
    connect_rabbi(client, weekday_id, rabbi_name='Rabbi Automatic')
    connect_rabbi(client, weekday_id, rabbi_name='Rabbi Directory Choice')
    with app.app_context():
        choice_id = db.session.scalar(db.select(RabbiPerson.id).where(
            RabbiPerson.name == 'Rabbi Directory Choice'))
    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Canonical Shul',
        'rabbi_mode': 'canonical',
        'rabbi_person_id': str(choice_id),
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Family, 1).rabbi == 'Rabbi Directory Choice'
        assert db.session.get(FamilyRabbiPreference, 1).overridden is True

    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Canonical Shul',
        'rabbi_mode': 'automatic',
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Family, 1).rabbi == 'Rabbi Automatic'
        assert db.session.get(FamilyRabbiPreference, 1).overridden is False


def test_legacy_backfill_reuses_names_and_is_idempotent(app):
    with app.app_context():
        first = Institution(kind='Shul', name='Legacy One')
        second = Institution(kind='Shul', name='Legacy Two')
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add_all([
            ShulRabbi(
                institution_id=first.id, rabbi_name='Rabbi Legacy',
                rabbi_phone='845-555-3000'),
            ShulRabbi(
                institution_id=second.id, rabbi_name='  rabbi legacy  ',
                rabbi_phone=''),
        ])
        marker = db.session.get(
            app_module.OrganizationSetting, 'canonical_rabbis_v1')
        if marker:
            db.session.delete(marker)
        db.session.commit()
        app_module._migrate_canonical_rabbis()
        db.session.commit()
        app_module._migrate_canonical_rabbis()
        db.session.commit()
        legacy_people = db.session.scalars(db.select(RabbiPerson).where(
            RabbiPerson.normalized_name == 'rabbi legacy')).all()
        assert len(legacy_people) == 1
        assert db.session.scalar(db.select(
            db.func.count(ShulRabbiAssociation.id)).where(
                ShulRabbiAssociation.rabbi_person_id == legacy_people[0].id)) == 2


def test_form_javascript_combines_canonical_rabbis_and_localized_shul_directory_editor(app, client):
    script = pathlib.Path('static/institution-picker.js').read_text()
    assert 'form.dataset.gabbaisLabel' in script
    assert 'form.dataset.rabbiLabel' in script
    assert 'form.dataset.addPhoneLabel' in script
    assert "mode.value='manual'" in script
    assert 'selectedShuls.weekday_shul' in script
    for language in ('he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        response = client.get('/families/1/edit')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'data-gabbais-label=' in html
        assert 'data-add-phone-label=' in html
        assert 'data-rabbi-assistants-label=' in html
        assert 'data-rabbi-mode' in html
