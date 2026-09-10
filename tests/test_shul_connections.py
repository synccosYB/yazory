from pathlib import Path

import pytest

from app import (
    Family,
    FamilyGabbaiConnection,
    FamilyRabbiConnection,
    HelperPerson,
    HelperPhone,
    Institution,
    OrganizationSetting,
    PersonAffiliation,
    RabbiPerson,
    ShulGabbaiDirectory,
    ShulGabbai,
    ShulGabbaiPhone,
    ShulHelperAssociation,
    ShulRabbi,
    ShulRabbiAssistant,
    ShulRabbiAssistantPhone,
    ShulRabbiPhone,
    create_app,
    db,
    _migrate_family_gabbaim_to_shared_shuls,
)


def test_directory_rabbi_selection_saves_phone_entered_on_family_form(app, client):
    add_shuls(app)
    with app.app_context():
        person = RabbiPerson(
            name='Rabbi Directory', normalized_name='rabbi directory', phone='')
        db.session.add(person)
        db.session.commit()
        person_id = person.id

    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'rabbi_mode': 'canonical',
        'rabbi_person_id': str(person_id),
        'rabbi': 'Rabbi Directory',
        'rabbi_phone': '845-555-7777',
    })
    assert response.status_code == 302

    with app.app_context():
        family = db.session.get(Family, 1)
        person = db.session.get(RabbiPerson, person_id)
        assert person.phone == '845-555-7777'
        assert family.rabbi == 'Rabbi Directory'
        assert family.rabbi_phone == '845-555-7777'

    assert b'845-555-7777' in client.get('/families/1').data


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


def add_shuls(app):
    with app.app_context():
        db.session.add_all([
            Institution(kind='Shul', name='Weekday Test Shul', city='Monroe'),
            Institution(kind='Shul', name='Shabbos Test Shul', city='Monroe'),
        ])
        db.session.commit()


def test_applicant_can_inherit_different_rabbis_and_multiple_gabbais_from_two_shuls(app, client):
    add_shuls(app)

    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Weekday',
        'weekday_shul_rabbi_phone': '845-555-1001',
        'weekday_shul_gabbai_name': ['Gabbai One', 'Gabbai Two'],
        'weekday_shul_gabbai_phone': ['845-555-2001', '845-555-2002'],
        'shabbos_shul': 'Shabbos Test Shul',
        'shabbos_shul_rabbi': 'Rabbi Shabbos',
        'shabbos_shul_rabbi_phone': '845-555-1002',
        'shabbos_shul_gabbai_name': ['Gabbai Three'],
        'shabbos_shul_gabbai_phone': ['845-555-2003'],
    })
    assert response.status_code == 302

    with app.app_context():
        shuls = {
            row.name: row
            for row in db.session.scalars(db.select(Institution).where(
                Institution.kind == 'Shul',
                Institution.name.in_(('Weekday Test Shul', 'Shabbos Test Shul'))
            )).all()
        }
        weekday_rabbi = db.session.get(ShulRabbi, shuls['Weekday Test Shul'].id)
        shabbos_rabbi = db.session.get(ShulRabbi, shuls['Shabbos Test Shul'].id)
        assert (weekday_rabbi.rabbi_name, weekday_rabbi.rabbi_phone) == (
            'Rabbi Weekday', '845-555-1001')
        assert (shabbos_rabbi.rabbi_name, shabbos_rabbi.rabbi_phone) == (
            'Rabbi Shabbos', '845-555-1002')

        family_rabbis = {
            row.role: row.rabbi_name
            for row in db.session.scalars(db.select(FamilyRabbiConnection).where(
                FamilyRabbiConnection.family_id == 1,
                FamilyRabbiConnection.role.in_(('weekday_shul', 'shabbos_shul'))
            )).all()
        }
        assert family_rabbis == {
            'weekday_shul': 'Rabbi Weekday',
            'shabbos_shul': 'Rabbi Shabbos',
        }

        weekday_gabbais = db.session.scalars(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shuls['Weekday Test Shul'].id
        ).order_by(ShulGabbaiDirectory.id)).all()
        shabbos_gabbais = db.session.scalars(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shuls['Shabbos Test Shul'].id
        ).order_by(ShulGabbaiDirectory.id)).all()
        assert [(row.name, row.phone) for row in weekday_gabbais] == [
            ('Gabbai One', '845-555-2001'),
            ('Gabbai Two', '845-555-2002'),
        ]
        assert [(row.name, row.phone) for row in shabbos_gabbais] == [
            ('Gabbai Three', '845-555-2003'),
        ]

        connections = db.session.scalars(db.select(FamilyGabbaiConnection).where(
            FamilyGabbaiConnection.family_id == 1
        )).all()
        assert sorted(row.role for row in connections) == [
            'shabbos_shul', 'weekday_shul', 'weekday_shul'
        ]


def test_reselecting_existing_shul_reuses_its_rabbi_and_all_gabbais(app, client):
    add_shuls(app)

    first = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Existing',
        'weekday_shul_rabbi_phone': '845-555-3001',
        'weekday_shul_gabbai_name': ['First Gabbai', 'Second Gabbai'],
        'weekday_shul_gabbai_phone': ['845-555-4001', '845-555-4002'],
    })
    assert first.status_code == 302

    second = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
    })
    assert second.status_code == 302

    with app.app_context():
        shul = db.session.scalar(db.select(Institution).where(
            Institution.kind == 'Shul', Institution.name == 'Weekday Test Shul'))
        rabbi = db.session.get(ShulRabbi, shul.id)
        assert rabbi.rabbi_name == 'Rabbi Existing'

        family_rabbis = db.session.scalars(db.select(FamilyRabbiConnection).where(
            FamilyRabbiConnection.family_id == 1,
            FamilyRabbiConnection.role == 'weekday_shul'
        )).all()
        assert [(row.role, row.rabbi_name) for row in family_rabbis] == [
            ('weekday_shul', 'Rabbi Existing')
        ]

        gabbais = db.session.scalars(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shul.id
        ).order_by(ShulGabbaiDirectory.id)).all()
        assert [row.name for row in gabbais] == ['First Gabbai', 'Second Gabbai']

        connections = db.session.scalars(db.select(FamilyGabbaiConnection).where(
            FamilyGabbaiConnection.family_id == 1,
            FamilyGabbaiConnection.role == 'weekday_shul'
        )).all()
        assert sorted(row.gabbai.name for row in connections) == [
            'First Gabbai', 'Second Gabbai'
        ]


def test_profile_shows_gabbai_connected_to_shared_shul_without_family_copy(app, client):
    add_shuls(app)
    with app.app_context():
        family = db.session.get(Family, 1)
        family.weekday_shul = 'Weekday Test Shul'
        shul = db.session.scalar(db.select(Institution).where(
            Institution.kind == 'Shul', Institution.name == 'Weekday Test Shul'))
        db.session.add(ShulGabbaiDirectory(
            institution_id=shul.id, name='Shared Shul Gabbai', phone='845-555-4999'))
        db.session.commit()

        assert db.session.scalar(db.select(FamilyGabbaiConnection).where(
            FamilyGabbaiConnection.family_id == family.id)) is None

    page = client.get('/families/1').text
    assert 'Shared Shul Gabbai' in page


def test_profile_uses_the_applicants_linked_shul_record_for_gabbaim(app, client):
    with app.app_context():
        family = db.session.get(Family, 1)
        family.weekday_shul = 'Weekday Test Shul'
        linked_shul = Institution(
            kind='Shul', name='Weekday Test Shul', city='Monroe')
        db.session.add(linked_shul)
        db.session.flush()
        db.session.add(ShulGabbaiDirectory(
            institution_id=linked_shul.id, name='Linked Shul Gabbai', phone='845-555-4888'))
        db.session.add(PersonAffiliation(
            institution_id=linked_shul.id, person_type='family', person_id=family.id,
            note='Weekday shul · Family profile'))
        db.session.commit()

    page = client.get('/families/1').get_data(as_text=True)

    assert 'Linked Shul Gabbai' in page
    assert '845-555-4888' in page


def test_profile_does_not_repeat_gabbai_when_weekday_and_shabbos_shul_match(app, client):
    add_shuls(app)
    post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'shabbos_shul': 'Weekday Test Shul',
        'weekday_shul_gabbai_name': ['One Shared Gabbai'],
        'weekday_shul_gabbai_phone': ['845-555-4777'],
    })

    page = client.get('/families/1').get_data(as_text=True)

    assert page.count('<strong>One Shared Gabbai</strong>') == 1


def test_profile_does_not_classify_rabbi_assistant_as_shul_gabbai(app, client):
    add_shuls(app)
    post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Test',
        'weekday_shul_rabbi_assistant_name': ['Shared Assistant Gabbai'],
        'weekday_shul_rabbi_assistant_phones': ['["845-555-4666"]'],
    })

    page = client.get('/families/1').get_data(as_text=True)

    shul_gabbai_block = page.split('<dt>Shul gabbais</dt><dd>', 1)[1].split('</dd>', 1)[0]
    assert 'Shared Assistant Gabbai' not in shul_gabbai_block
    assert 'Shared Assistant Gabbai' in page
    assert '845-555-4666' in page


def test_legacy_family_gabbai_moves_to_shul_and_connects_every_linked_family(app):
    with app.app_context():
        shul = Institution(kind='Shul', name='Shared Migration Shul')
        second = Family(name='Second linked family', weekday_shul=shul.name)
        first = db.session.get(Family, 1)
        first.weekday_shul = shul.name
        first.shabbos_shul = shul.name
        db.session.add_all([shul, second])
        db.session.flush()
        db.session.add_all([
            PersonAffiliation(institution_id=shul.id, person_type='family',
                              person_id=first.id, note='Weekday shul · Family profile'),
            PersonAffiliation(institution_id=shul.id, person_type='family',
                              person_id=second.id, note='Weekday shul · Family profile'),
            ShulGabbai(family_id=first.id, name='Migrated Shared Gabbai',
                       phone='845-555-4555'),
        ])
        db.session.delete(db.session.get(OrganizationSetting, 'shared_shul_gabbaim_v2'))
        db.session.commit()

        _migrate_family_gabbaim_to_shared_shuls()

        shared = db.session.scalar(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shul.id,
            ShulGabbaiDirectory.name == 'Migrated Shared Gabbai'))
        assert shared is not None
        connected_family_ids = set(db.session.scalars(db.select(
            FamilyGabbaiConnection.family_id
        ).where(FamilyGabbaiConnection.gabbai_id == shared.id)).all())
        assert connected_family_ids == {first.id, second.id}
        assert db.session.scalar(db.select(ShulGabbai).where(
            ShulGabbai.name == 'Migrated Shared Gabbai')) is None


def test_one_helper_can_be_associated_with_multiple_shuls(app, client):
    add_shuls(app)
    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_gabbai_name': ['Shared Helper'],
        'weekday_shul_gabbai_phone': ['845-555-4101'],
        'shabbos_shul': 'Shabbos Test Shul',
        'shabbos_shul_gabbai_name': ['Shared Helper'],
        'shabbos_shul_gabbai_phone': ['845-555-4102'],
    })
    assert response.status_code == 302

    with app.app_context():
        helpers = db.session.scalars(db.select(HelperPerson).where(
            HelperPerson.normalized_name == 'shared helper')).all()
        assert len(helpers) == 1
        links = db.session.scalars(db.select(ShulHelperAssociation).where(
            ShulHelperAssociation.helper_person_id == helpers[0].id,
            ShulHelperAssociation.role == 'shul_gabbai')).all()
        assert {link.institution.name for link in links} == {
            'Weekday Test Shul', 'Shabbos Test Shul'
        }
        phones = db.session.scalars(db.select(HelperPhone).where(
            HelperPhone.helper_person_id == helpers[0].id).order_by(HelperPhone.id)).all()
        assert [row.phone for row in phones] == ['845-555-4101', '845-555-4102']


def test_shul_directory_apis_return_saved_rabbi_and_gabbais(app, client):
    add_shuls(app)
    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi API',
        'weekday_shul_rabbi_phone': '845-555-5001',
        'weekday_shul_gabbai_name': ['API Gabbai'],
        'weekday_shul_gabbai_phone': ['845-555-5002'],
    }).status_code == 302

    rabbis = client.get('/api/shul-rabbis').get_json()
    gabbais = client.get('/api/shul-gabbais').get_json()
    assert rabbis['Weekday Test Shul']['name'] == 'Rabbi API'
    assert rabbis['Weekday Test Shul']['phones'] == ['845-555-5001']
    assert rabbis['Weekday Test Shul']['assistants'] == []
    assert gabbais['Weekday Test Shul'][0]['name'] == 'API Gabbai'
    assert gabbais['Weekday Test Shul'][0]['phones'] == ['845-555-5002']


def test_rabbi_and_shul_gabbai_can_have_multiple_phones_and_rabbi_has_own_assistant(app, client):
    add_shuls(app)
    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Multi',
        'weekday_shul_rabbi_phone': ['845-555-6101', '845-555-6102'],
        'weekday_shul_rabbi_assistant_name': ['Rabbi Gabbai'],
        'weekday_shul_rabbi_assistant_phones': ['["845-555-6201", "845-555-6202"]'],
        'weekday_shul_gabbai_name': ['Shul Gabbai'],
        'weekday_shul_gabbai_phones': ['["845-555-6301", "845-555-6302"]'],
    })
    assert response.status_code == 302

    with app.app_context():
        shul = db.session.scalar(db.select(Institution).where(
            Institution.kind == 'Shul', Institution.name == 'Weekday Test Shul'))
        rabbi_phones = db.session.scalars(db.select(ShulRabbiPhone).where(
            ShulRabbiPhone.institution_id == shul.id).order_by(ShulRabbiPhone.id)).all()
        assert [row.phone for row in rabbi_phones] == ['845-555-6101', '845-555-6102']

        assistant = db.session.scalar(db.select(ShulRabbiAssistant).where(
            ShulRabbiAssistant.institution_id == shul.id))
        assert assistant.name == 'Rabbi Gabbai'
        assistant_phones = db.session.scalars(db.select(ShulRabbiAssistantPhone).where(
            ShulRabbiAssistantPhone.assistant_id == assistant.id
        ).order_by(ShulRabbiAssistantPhone.id)).all()
        assert [row.phone for row in assistant_phones] == ['845-555-6201', '845-555-6202']

        gabbai = db.session.scalar(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shul.id,
            ShulGabbaiDirectory.name == 'Shul Gabbai'))
        assert gabbai.name != assistant.name
        gabbai_phones = db.session.scalars(db.select(ShulGabbaiPhone).where(
            ShulGabbaiPhone.gabbai_id == gabbai.id).order_by(ShulGabbaiPhone.id)).all()
        assert [row.phone for row in gabbai_phones] == ['845-555-6301', '845-555-6302']

    rabbis = client.get('/api/shul-rabbis').get_json()['Weekday Test Shul']
    gabbais = client.get('/api/shul-gabbais').get_json()['Weekday Test Shul']
    assert rabbis['phones'] == ['845-555-6101', '845-555-6102']
    assert rabbis['assistants'] == [{
        'name': 'Rabbi Gabbai',
        'phone': '845-555-6201',
        'phones': ['845-555-6201', '845-555-6202'],
    }]
    assert gabbais == [{
        'name': 'Shul Gabbai',
        'phone': '845-555-6301',
        'phones': ['845-555-6301', '845-555-6302'],
    }]

    profile = client.get('/families/1')
    assert profile.status_code == 200
    assert b'845-555-6101' in profile.data
    assert b'Rabbi Gabbai' in profile.data
    assert b'845-555-6201' in profile.data
    assert b'845-555-6202' in profile.data
    assert b'845-555-6301' in profile.data
    assert b'845-555-6302' in profile.data

def test_delayed_directory_load_does_not_overwrite_entered_contact_phones():
    script = Path('static/institution-picker.js').read_text()
    assert "if(!item.contactsEdited())item.update()" in script


def test_profile_deduplicates_same_shul_and_falls_back_to_shared_assistant_phone(app, client):
    add_shuls(app)
    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'shabbos_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Shared',
        'weekday_shul_rabbi_phone': ['845-555-7001'],
        'weekday_shul_rabbi_assistant_name': ['Rabbi Assistant'],
        'weekday_shul_rabbi_assistant_phones': ['["845-555-7002"]'],
    }).status_code == 302

    with app.app_context():
        assistant = db.session.scalar(db.select(ShulRabbiAssistant).where(
            ShulRabbiAssistant.name == 'Rabbi Assistant'))
        db.session.query(ShulRabbiAssistantPhone).filter_by(
            assistant_id=assistant.id).delete()
        db.session.commit()

    profile = client.get('/families/1').text
    assert profile.count('class="profile-linked-contacts"') == 1
    assert 'Rabbi Assistant' in profile
    assert '845-555-7002' in profile


def test_automatic_rabbi_phone_entered_on_family_form_updates_shared_directory(app, client):
    add_shuls(app)
    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Shared',
    }).status_code == 302

    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'rabbi_mode': 'automatic',
        'rabbi': 'Rabbi Shared',
        'rabbi_phone': '845-555-7777',
    })
    assert response.status_code == 302

    profile = client.get('/families/1')
    directory = client.get('/api/shul-rabbis').get_json()['Weekday Test Shul']
    assert b'845-555-7777' in profile.data
    assert directory['phone'] == '845-555-7777'
    assert directory['phones'][0] == '845-555-7777'
