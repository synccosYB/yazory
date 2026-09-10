import pytest

from app import Contact, Family, create_app, db


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
                  '845-555-4000', 'Uses Yoel T. on checks.'):
        assert value in detail


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
