import pytest
from app_entry import create_app
from app import Askan, Contact, Family, StaffUser, db
from person_addresses import PersonAddressDetails, mailing_lines


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test-addresses'})


def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf': csrf})


def test_shared_supporter_address_and_mailing_preference(app):
    with app.app_context():
        families = [Family(name='First'), Family(name='Second')]
        db.session.add_all(families)
        db.session.flush()
        contacts = [Contact(family_id=f.id, name='Same donor', relationship='Friend',
                            phone='3475551234', supporter_key='phone:3475551234') for f in families]
        db.session.add_all(contacts)
        db.session.flush()
        for contact in contacts:
            app.extensions['supporter_identity']['attach'](contact)
        db.session.commit()
        ids = [c.id for c in contacts]
    client = app.test_client()
    assert post(client, f'/people/supporter/{ids[0]}/addresses', {
        'home_street': '10 Main Street', 'home_unit': 'Apt 2',
        'home_city': 'Monroe', 'home_state': 'NY', 'home_zip_code': '00123',
        'work_company': 'Office', 'work_street': '20 Work Road',
        'work_city': 'Brooklyn', 'mailing_preference': 'work'}).status_code == 302
    with app.app_context():
        for cid in ids:
            contact = db.session.get(Contact, cid)
            assert contact.home_address == '10 Main Street'
            assert contact.zip_code == '00123'
            assert mailing_lines(contact) == ['Office', '20 Work Road', 'Brooklyn']
        assert db.session.query(PersonAddressDetails).count() == 1
    response = client.get(f'/people/supporter/{ids[1]}/addresses')
    assert b'Apt 2' in response.data and b'20 Work Road' in response.data


def test_new_supporter_saves_addresses_with_profile_and_blank_reconnect_preserves(app):
    client = app.test_client()
    with app.app_context():
        family = Family(name='New supporter case')
        second = Family(name='Second connection')
        db.session.add_all([family, second])
        db.session.commit()
        fid, second_id = family.id, second.id
    data = {'name': 'New donor', 'cell_phone': '3475558877',
            'relationship': 'Friend', 'status': 'To contact', 'monthly': '0'}
    assert post(client, f'/families/{fid}/contacts', {
        **data, 'home_street': '12 Home Road', 'home_unit': 'Apartment 3',
        'home_zip_code': '00123', 'work_street': '45 Office Lane',
        'work_company': 'Donor Company', 'mailing_preference': 'work'}).status_code == 302
    assert post(client, f'/families/{second_id}/contacts', {
        **data, 'home_street': '', 'work_street': '', 'mailing_preference': ''}).status_code == 302
    with app.app_context():
        rows = db.session.scalars(db.select(Contact).where(Contact.name == 'New donor')).all()
        assert len(rows) == 2
        for contact in rows:
            assert contact.home_address == '12 Home Road'
            assert contact.zip_code == '00123'
            assert mailing_lines(contact) == ['Donor Company', '45 Office Lane']
        details = db.session.query(PersonAddressDetails).one()
        assert details.home['unit'] == 'Apartment 3'
    for path in ('/supporters', f'/families/{fid}'):
        page = client.get(path).get_data(as_text=True)
        assert 'name="home_street"' in page
        assert 'name="work_street"' in page
        assert 'name="home_street" required' not in page


@pytest.mark.parametrize('kind,model', [('family', Family), ('askan', Askan), ('staff', StaffUser)])
def test_addresses_optional_for_existing_profiles(app, kind, model):
    with app.app_context():
        values = {'name': 'Optional Address'}
        if kind == 'staff':
            values.update(email='optional@example.test', password_hash='unused')
        row = model(**values)
        db.session.add(row)
        db.session.commit()
        person_id = row.id
    client = app.test_client()
    assert post(client, f'/people/{kind}/{person_id}/addresses', {}).status_code == 302
    assert client.get(f'/people/{kind}/{person_id}/addresses').status_code == 200


def test_existing_home_address_is_read_without_duplicate_storage(app):
    with app.app_context():
        family = Family(name='Existing', address='Original Road', city='Monroe')
        db.session.add(family)
        db.session.commit()
        fid = family.id
    client = app.test_client()
    assert b'Original Road' in client.get(f'/people/family/{fid}/addresses').data
    with app.app_context():
        assert db.session.query(PersonAddressDetails).count() == 0


def test_explicit_migration_preserves_existing_home_address(app):
    with app.app_context():
        family = Family(name='Migration', address='Keep this address')
        db.session.add(family)
        db.session.commit()
        fid = family.id
        PersonAddressDetails.__table__.drop(db.engine)
    result = app.test_cli_runner().invoke(args=['init-db'])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert db.session.get(Family, fid).address == 'Keep this address'
        assert db.session.query(PersonAddressDetails).count() == 0


def test_deleting_person_does_not_leave_addresses_for_reused_id(app):
    with app.app_context():
        askan = Askan(name='Delete me')
        db.session.add(askan)
        db.session.flush()
        db.session.add(PersonAddressDetails(person_kind='askan', person_id=askan.id,
                                            work={'street': 'Private address'}))
        db.session.commit()
        db.session.delete(askan)
        db.session.commit()
        assert db.session.query(PersonAddressDetails).count() == 0


def test_unassigned_user_cannot_read_or_edit_addresses(app):
    with app.app_context():
        family = Family(name='Private')
        user = StaffUser(name='Unassigned', email='unassigned@example.test',
                         password_hash='unused', role='family_admin')
        db.session.add_all([family, user])
        db.session.commit()
        fid, uid = family.id, user.id
    client = app.test_client()
    client.get('/')
    app.config['DEMO'] = False
    with client.session_transaction() as session:
        session['user_id'] = uid
    assert client.get(f'/people/family/{fid}/addresses').status_code == 403
    assert post(client, f'/people/family/{fid}/addresses', {'home_street': 'Changed'}).status_code == 403


@pytest.mark.parametrize('language,heading', [('en','Home &amp; work addresses'),
                                            ('he','כתובת הבית והעבודה'),
                                            ('yi','היים און ארבעט אדרעסן')])
def test_address_locales(app, language, heading):
    with app.app_context():
        row = Askan(name='Test')
        db.session.add(row)
        db.session.commit()
        aid = row.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['language'] = language
    response = client.get(f'/people/askan/{aid}/addresses')
    assert heading in response.get_data(as_text=True)
