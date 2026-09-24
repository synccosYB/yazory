from app_entry import create_app
import pytest
import sqlite3
from sqlalchemy import inspect

from app import (Contact, Family, Institution, PersonAffiliation,
                 SupporterPerson, db)


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL',
                'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({
        'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test-only',
    })


@pytest.fixture
def client(app):
    return app.test_client()


def _post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf': csrf})


def test_migrate_legacy_contact_schema_adds_person_id_before_contact_queries(
        monkeypatch, tmp_path):
    database = tmp_path / 'legacy.db'
    connection = sqlite3.connect(database)
    connection.execute(
        'CREATE TABLE contact ('
        'id INTEGER PRIMARY KEY, family_id INTEGER NOT NULL, '
        'name VARCHAR(160) NOT NULL, relationship VARCHAR(80) NOT NULL, '
        "phone VARCHAR(80) DEFAULT '', monthly_cents INTEGER NOT NULL DEFAULT 0, "
        "status VARCHAR(30) NOT NULL DEFAULT 'To contact')")
    connection.commit()
    connection.close()
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL',
                'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)

    legacy_app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database}',
        'SECRET_KEY': 'test-only',
    })

    with legacy_app.app_context():
        columns = {column['name'] for column in inspect(db.engine).get_columns('contact')}
        assert 'person_id' in columns


def test_supporter_identity_details_save_display_and_sync(app, client):
    with app.app_context():
        first_family = Family(name='First family')
        second_family = Family(name='Second family')
        db.session.add_all([first_family, second_family])
        db.session.flush()
        first = Contact(
            family_id=first_family.id, name='Same Supporter', relationship='Sibling',
            phone='8455551000', supporter_key='phone:8455551000')
        second = Contact(
            family_id=second_family.id, name='Same Supporter', relationship='Friend',
            phone='8455551000', supporter_key='phone:8455551000')
        db.session.add_all([first, second])
        db.session.commit()
        first_id, second_id = first.id, second.id

    response = _post(client, f'/contacts/{first_id}/edit', {
        'name': 'Yoel Teitelbaum', 'relationship': 'Sibling',
        'cell_phone': '845-555-2000', 'home_phone': '845-555-3000',
        'email': 'yoel@example.test', 'home_address': '12 Main Street',
        'city': 'Monroe', 'state': 'NY', 'zip_code': '10950',
        'workplace': 'Teitelbaum Foods', 'work_phone': '845-555-4000',
        'notes': 'Uses Yoel T. on checks.', 'parent_contact_id': '',
        'parent_connection': '', 'monthly': '0',
        'pledge_frequency': 'Monthly', 'status': 'To contact',
    })
    assert response.status_code == 302

    with app.app_context():
        first = db.session.get(Contact, first_id)
        second = db.session.get(Contact, second_id)
        assert first.person_id == second.person_id
        person = db.session.get(SupporterPerson, first.person_id)
        assert person.name == 'Yoel Teitelbaum'
        assert person.email == 'yoel@example.test'
        for contact in (first, second):
            assert contact.cell_phone == '845-555-2000'
            assert contact.home_phone == '845-555-3000'
            assert contact.phone == '845-555-2000'
            assert contact.home_address == '12 Main Street'
            assert contact.city == 'Monroe'
            assert contact.state == 'NY'
            assert contact.zip_code == '10950'
            assert contact.workplace == 'Teitelbaum Foods'
            assert contact.work_phone == '845-555-4000'
            assert contact.notes == 'Uses Yoel T. on checks.'
        assert second.relationship == 'Friend'

    detail = client.get(f'/supporters/{first_id}').text
    for value in ('12 Main Street', 'Monroe', 'Teitelbaum Foods',
                  'Uses Yoel T. on checks.'):
        assert value in detail
    assert 'Work phone' in detail and '4000' in detail


def test_clearing_cell_phone_does_not_redisplay_home_phone_as_cell(app, client):
    with app.app_context():
        family = Family(name='Phone test family')
        db.session.add(family)
        db.session.flush()
        supporter = Contact(
            family_id=family.id, name='Phone Test', relationship='Friend',
            phone='845-555-1915', cell_phone='845-555-1915',
            home_phone='845-555-1915', supporter_key='phone:8455551915')
        db.session.add(supporter)
        db.session.commit()
        supporter_id = supporter.id

    response = _post(client, f'/contacts/{supporter_id}/edit', {
        'name': 'Phone Test', 'relationship': 'Friend',
        'cell_phone': '', 'home_phone': '845-555-1915',
        'email': '', 'home_address': '', 'city': '', 'state': '',
        'zip_code': '', 'workplace': '', 'work_phone': '', 'notes': '',
        'parent_contact_id': '', 'parent_connection': '', 'monthly': '0',
        'pledge_frequency': 'Monthly', 'status': 'To contact',
    })
    assert response.status_code == 302

    with app.app_context():
        supporter = db.session.get(Contact, supporter_id)
        assert supporter.cell_phone == ''
        assert supporter.home_phone == '845-555-1915'

    detail = client.get(f'/supporters/{supporter_id}').text
    assert '<dt>Cell phone</dt><dd><bdi dir="ltr">—</bdi>' in detail

    edit = client.get(f'/contacts/{supporter_id}/edit').text
    assert 'name="cell_phone" value=""' in edit


def test_edit_with_parent_requires_role_without_leaving_edit_form(app, client):
    with app.app_context():
        family = Family(name='Hierarchy edit family')
        db.session.add(family)
        db.session.flush()
        parent = Contact(family_id=family.id, name='Parent', relationship='Sibling')
        child = Contact(family_id=family.id, name='Child', relationship='Nephew')
        db.session.add_all([parent, child])
        db.session.commit()
        parent_id, child_id = parent.id, child.id

    response = _post(client, f'/contacts/{child_id}/edit', {
        'name': 'Child', 'relationship': 'Nephew',
        'parent_contact_id': str(parent_id), 'parent_connection': '',
        'monthly': '0', 'pledge_frequency': 'Monthly', 'status': 'To contact',
    })

    assert response.status_code == 400
    assert '<form class="card padded" method="post">' in response.text
    assert 'Choose whether this person is a son or son-in-law' in response.text
    assert 'Back to overview' not in response.text


def test_existing_supporter_can_be_connected_to_another_family(app, client):
    with app.app_context():
        first_family = Family(name='First connected family')
        second_family = Family(name='Second connected family')
        db.session.add_all([first_family, second_family])
        db.session.flush()
        supporter = Contact(
            family_id=first_family.id, name='One Real Person',
            relationship='Sibling', phone='845-555-2525',
            cell_phone='845-555-2525', email='one@example.test',
            supporter_key='phone:8455552525', monthly_cents=5000,
            pledge_frequency='Monthly', status='Pledged')
        db.session.add(supporter)
        db.session.commit()
        supporter_id = supporter.id
        second_family_id = second_family.id

    detail = client.get(f'/supporters/{supporter_id}')
    assert detail.status_code == 200
    assert '+ Connect to another family' in detail.text
    assert 'Second connected family' in detail.text
    assert 'Whose son or son-in-law is he?' in detail.text

    response = _post(client, f'/supporters/{supporter_id}/connect-family', {
        'family_id': str(second_family_id), 'relationship': 'Friend',
    })
    assert response.status_code == 302

    with app.app_context():
        connections = db.session.scalars(db.select(Contact).where(
            Contact.supporter_key == 'phone:8455552525').order_by(Contact.id)).all()
        assert len(connections) == 2
        added = connections[1]
        assert added.family_id == second_family_id
        assert added.name == 'One Real Person'
        assert added.email == 'one@example.test'
        assert added.relationship == 'Friend'
        assert added.monthly_cents == 0
        assert added.status == 'To contact'
        link_model = app.extensions['workflows']['models']['SupporterLink']
        assert db.session.get(link_model, added.id) is not None

    updated = client.get(response.headers['Location'])
    assert updated.status_code == 200
    assert 'First connected family' in updated.text
    assert 'Second connected family' in updated.text


def test_new_family_connection_keeps_case_specific_hierarchy(app, client):
    with app.app_context():
        first_family = Family(name='Original family')
        second_family = Family(name='Hierarchy family')
        db.session.add_all([first_family, second_family])
        db.session.flush()
        source = Contact(
            family_id=first_family.id, name='Shared Child', relationship='Friend',
            phone='845-555-2727', supporter_key='phone:8455552727')
        parent = Contact(
            family_id=second_family.id, name='Second Case Parent',
            relationship='Sibling', phone='845-555-2828',
            supporter_key='phone:8455552828')
        db.session.add_all([source, parent])
        db.session.commit()
        source_id, parent_id, second_family_id = source.id, parent.id, second_family.id

    response = _post(client, f'/supporters/{source_id}/connect-family', {
        'family_id': str(second_family_id), 'relationship': 'Nephew',
        'parent_contact_id': str(parent_id), 'parent_connection': 'Son-in-law',
    })
    assert response.status_code == 302
    with app.app_context():
        added = db.session.scalar(db.select(Contact).where(
            Contact.family_id == second_family_id,
            Contact.supporter_key == 'phone:8455552727'))
        assert added.parent_contact_id == parent_id
        assert added.parent_connection == 'Son-in-law'


def test_new_family_connection_can_record_shared_shul(app, client):
    with app.app_context():
        first_family = Family(name='First shul family')
        second_family = Family(name='Second shul family')
        shul = Institution(kind='Shul', name='Shared Connection Shul')
        db.session.add_all([first_family, second_family, shul])
        db.session.flush()
        source = Contact(
            family_id=first_family.id, name='Shul Friend',
            relationship='Shul friend', phone='845-555-2929',
            supporter_key='phone:8455552929')
        db.session.add(source)
        db.session.flush()
        db.session.add(PersonAffiliation(
            institution_id=shul.id, person_type='family',
            person_id=second_family.id))
        db.session.commit()
        source_id, second_family_id, shul_id = source.id, second_family.id, shul.id

    detail = client.get(f'/supporters/{source_id}')
    assert 'Shared Connection Shul' in detail.text
    response = _post(client, f'/supporters/{source_id}/connect-family', {
        'family_id': str(second_family_id), 'relationship': 'Shul friend',
        'institution_id': str(shul_id),
    })
    assert response.status_code == 302
    with app.app_context():
        added = db.session.scalar(db.select(Contact).where(
            Contact.family_id == second_family_id,
            Contact.supporter_key == 'phone:8455552929'))
        affiliation = db.session.scalar(db.select(PersonAffiliation).where(
            PersonAffiliation.person_type == 'supporter',
            PersonAffiliation.person_id == added.id,
            PersonAffiliation.institution_id == shul_id))
        assert affiliation is not None


def test_connect_supporter_rejects_duplicate_family(app, client):
    with app.app_context():
        family = Family(name='Only family')
        db.session.add(family)
        db.session.flush()
        supporter = Contact(
            family_id=family.id, name='Already Here', relationship='Friend',
            phone='845-555-2626', supporter_key='phone:8455552626')
        db.session.add(supporter)
        db.session.commit()
        supporter_id = supporter.id
        family_id = family.id

    response = _post(client, f'/supporters/{supporter_id}/connect-family', {
        'family_id': str(family_id), 'relationship': 'Friend',
    })
    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Contact.id)).where(
            Contact.supporter_key == 'phone:8455552626')) == 1
