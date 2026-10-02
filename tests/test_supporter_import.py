from app_entry import create_app
from io import BytesIO

import pytest
from sqlalchemy import event

from app import (Contact, Family, Institution, PersonAffiliation,
                 PersonRelationship, SupporterPerson, SupporterProfile, db)


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test-only'})


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def test_family_relative_names_are_backfilled_without_resaving_profile(app, client):
    """Legacy case text fields must immediately appear in the people list."""
    with app.app_context():
        family = db.session.get(Family, 1)
        expected = {
            'family:1:applicant': family.name,
            'family:1:spouse': family.spouse,
            'family:1:father': family.father,
            'family:1:inlaws': family.inlaws,
        }
        profiles = {
            row.normalized_phone: row.name for row in
            db.session.scalars(db.select(SupporterProfile).where(
                SupporterProfile.normalized_phone.in_(expected))).all()
        }
        assert profiles == expected

    page = client.get('/supporter-directory').text
    for name in expected.values():
        assert name in page


def test_partial_family_profile_save_syncs_relative_names_once(app, client):
    response = client.post('/families/1/edit?field=father', data={
        'csrf': csrf(client), 'name': 'Sample family',
        'father': 'R. Yaakov Shlomo',
        'inlaws': 'R. Monish Neishtיין',
        'inlaws_maiden_name': 'Yisroel Boruch Gutman',
        'inlaws_family': 'R. Hersh Meilech Seidenfeld',
    })
    assert response.status_code == 302

    with app.app_context():
        sync_people = app.extensions['family_profile_person_sync'][0]
        sync_people(db.session.get(Family, 1))
        db.session.commit()
        profiles = db.session.scalars(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone.like('family:1:%'))).all()
        by_key = {row.normalized_phone: row.name for row in profiles}
        assert by_key['family:1:father'] == 'R. Yaakov Shlomo'
        assert by_key['family:1:applicant'] == 'Sample family'
        assert by_key['family:1:inlaws'] == 'R. Monish Neishtיין'
        assert by_key['family:1:maiden'] == 'Yisroel Boruch Gutman'
        assert by_key['family:1:inlawfam'] == 'R. Hersh Meilech Seidenfeld'
        assert len(by_key) == len(set(by_key))


def test_csv_import_uses_phone_as_unique_identity(app, client):
    data = (
        'Name,Phone,Email\n'
        'First Name,(845) 555-1200,first@example.test\n'
        'Duplicate Name,845-555-1200,duplicate@example.test\n'
        'Missing Phone,,nobody@example.test\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'contacts.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    assert 'New profiles' in response.text
    assert 'Duplicates found' in response.text
    assert 'Rows skipped' in response.text
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8455551200')).all()
        assert len(rows) == 1
        assert rows[0].name == 'First Name'



def test_import_blocks_same_name_and_home_address_with_different_phone(app, client):
    data = (
        'Name,Phone,Home address,City,State,Zip code\n'
        'Same Person,8455553100,10 Main Street,Monroe,NY,10950\n'
        'Same Person,8455553200,10 Main Street,Monroe,NY,10950\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'duplicate-address.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    with client.session_transaction() as session:
        result = session['people_import_result']
        assert result['created'] == 1
        assert result['duplicates'] == 1
        assert result['skipped'] == 1
        assert 'same name and home address' in result['errors'][0]
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone.in_(['8455553100', '8455553200']))).all()
        assert len(rows) == 1


def test_import_allows_same_name_at_different_addresses(app, client):
    data = (
        'Name,Phone,Home address,City,State,Zip code\n'
        'Common Name,8455553300,10 Main Street,Monroe,NY,10950\n'
        'Common Name,8455553400,20 Main Street,Monroe,NY,10950\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'same-name.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    with app.app_context():
        rows = db.session.scalars(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone.in_(['8455553300', '8455553400']))).all()
        assert len(rows) == 2


def test_no_phone_import_blocks_same_name_and_home_address(app, client):
    data = (
        'Name,Email,Home address,City,State,Zip code\n'
        'No Phone Person,first@example.test,15 Forest Road,Monroe,NY,10950\n'
        'No Phone Person,second@example.test,15 Forest Road,Monroe,NY,10950\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'no-phone-duplicates.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    with client.session_transaction() as session:
        result = session['people_import_result']
        assert result['created'] == 1
        assert result['duplicates'] == 1
        assert result['skipped'] == 1
        assert 'same name and home address' in result['errors'][0]



def test_imported_profile_connects_once_to_a_case(app, client):
    with app.app_context():
        profile = SupporterProfile(name='Imported Person', phone='845-555-1300',
                                   normalized_phone='8455551300',
                                   email='person@example.test')
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))
    path = f'/supporter-directory/{profile_id}/connect'
    payload = {'csrf': csrf(client), 'family_id': str(family_id), 'relationship': 'Friend'}
    first = client.post(path, data=payload)
    second = client.post(path, data=payload)
    assert first.status_code == 302 and first.location.endswith(f'/supporter-directory/{profile_id}/edit#case-connections')
    assert second.status_code == 302
    with app.app_context():
        contacts = db.session.scalars(db.select(Contact).where(
            Contact.family_id == family_id,
            Contact.supporter_key == 'phone:8455551300')).all()
        assert len(contacts) == 1
        assert contacts[0].email == 'person@example.test'
        link_model = app.extensions['workflows']['models']['SupporterLink']
        link = db.session.get(link_model, contacts[0].id)
        assert link is not None
        assert link.side == 'Community'
        assert link.relationship == 'Friend'

    case_page = client.get(f'/families/{family_id}')
    assert case_page.status_code == 200
    assert 'Imported Person' in case_page.text


def test_directory_connection_starts_a_separate_case_pledge_and_followup(app, client):
    with app.app_context():
        first_family = db.session.scalar(db.select(Family).order_by(Family.id))
        second_family = Family(name='Another case')
        profile = SupporterProfile(name='Shared Person', phone='845-555-1301',
                                   normalized_phone='8455551301',
                                   email='shared@example.test')
        db.session.add_all([second_family, profile])
        db.session.flush()
        db.session.add(Contact(
            family_id=first_family.id, name=profile.name, phone=profile.phone,
            email=profile.email, relationship='Friend',
            supporter_key='phone:8455551301', status='Pledged',
            monthly_cents=6500, pledge_frequency='Weekly'))
        db.session.commit()
        profile_id, second_id = profile.id, second_family.id
    response = client.post(f'/supporter-directory/{profile_id}/connect', data={
        'csrf': csrf(client), 'family_id': str(second_id),
        'relationship': 'Friend'})
    assert response.status_code == 302
    with app.app_context():
        second = db.session.scalar(db.select(Contact).where(
            Contact.family_id == second_id,
            Contact.supporter_key == 'phone:8455551301'))
        assert second.status == 'To contact'
        assert second.monthly_cents == 0
        assert second.pledge_frequency == 'Monthly'
        assert second.email == 'shared@example.test'


def test_case_supporter_form_can_select_imported_profile_and_blocks_duplicate(app, client):
    with app.app_context():
        profile = SupporterProfile(name='Directory Name', phone='(845) 555-1350',
                                   normalized_phone='8455551350',
                                   email='directory@example.test')
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))

    payload = {
        'csrf': csrf(client), 'supporter_profile_id': str(profile_id),
        'name': 'Different manual spelling', 'phone': '845-555-9999',
        'email': 'different@example.test', 'relationship': 'Friend',
        'status': 'To contact', 'monthly': '0',
        'pledge_frequency': 'Monthly',
    }
    first = client.post(f'/families/{family_id}/contacts', data=payload)
    assert first.status_code == 302
    payload['csrf'] = csrf(client)
    second = client.post(f'/families/{family_id}/contacts', data=payload)
    assert second.status_code == 400
    assert 'already connected to this case' in second.text

    with app.app_context():
        rows = db.session.scalars(db.select(Contact).where(
            Contact.family_id == family_id,
            Contact.supporter_key == 'phone:8455551350')).all()
        assert len(rows) == 1
        assert (rows[0].name, rows[0].phone, rows[0].email) == (
            'Directory Name', '(845) 555-1350', 'directory@example.test')


def test_manual_entry_matching_imported_email_reuses_directory_identity(app, client):
    with app.app_context():
        profile = SupporterProfile(name='Canonical Name', phone='845-555-1360',
                                   normalized_phone='8455551360',
                                   email='same@example.test')
        db.session.add(profile)
        db.session.commit()
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))

    response = client.post(f'/families/{family_id}/contacts', data={
        'csrf': csrf(client), 'name': 'Duplicate Name', 'phone': '',
        'email': 'SAME@example.test', 'relationship': 'Friend',
        'status': 'To contact', 'monthly': '0',
        'pledge_frequency': 'Monthly',
    })
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(Contact).where(
            Contact.family_id == family_id,
            Contact.supporter_key == 'phone:8455551360'))
        assert row is not None
        assert row.name == 'Canonical Name'

def test_wide_contact_export_uses_local_name_and_first_available_phone(app, client):
    data = (
        'Account #,English Name,Yiddish/Hebrew Name,Phone 1,Phone 2,Phone 3,Email 1,Email 2\n'
        '260,Zvi Hersh Gold,צבי הירש גאלד,8456375221,8452389207,,gold@example.test,\n'
        '695,Yakov Schwerts,יעקב שווארטץ,,8455551919,,,second@example.test\n'
    ).encode()
    response = client.post('/supporter-directory', data={
        'csrf': csrf(client), 'file': (BytesIO(data), 'wide-contacts.csv')},
        content_type='multipart/form-data')
    assert response.status_code == 200
    with app.app_context():
        first = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8456375221'))
        fallback = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8455551919'))
        assert first.name == 'צבי הירש גאלד'
        assert first.email == 'gold@example.test'
        assert fallback.name == 'יעקב שווארטץ'
        assert fallback.email == 'second@example.test'


def test_large_import_checks_existing_profiles_in_bulk(app, client):
    token = csrf(client)
    rows = ['Name,Phone,Email'] + [
        f'Person {number},845555{number:04d},person{number}@example.test'
        for number in range(1000)
    ]
    profile_selects = []

    def count_profile_selects(_conn, _cursor, statement, _parameters, _context, _many):
        normalized = statement.lower().lstrip()
        if normalized.startswith('select') and 'supporter_profile' in normalized:
            profile_selects.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', count_profile_selects)
        try:
            response = client.post('/supporter-directory', data={
                'csrf': token,
                'file': (BytesIO(('\n'.join(rows) + '\n').encode()), 'large.csv'),
            }, content_type='multipart/form-data')
        finally:
            event.remove(db.engine, 'before_cursor_execute', count_profile_selects)

    assert response.status_code == 200
    # Pagination adds one count, while profile lookups remain batched.
    counts = [sql for sql in profile_selects if 'count(' in sql.lower()]
    assert len(counts) == 1
    assert len(profile_selects) - len(counts) <= 3
    assert 'LIMIT' in profile_selects[-1]



def test_edit_imported_profile_updates_connected_cases(app, client):
    with app.app_context():
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))
        profile = SupporterProfile(
            name='Old Name', phone='845-555-2100',
            normalized_phone='8455552100', email='old@example.test')
        contact = Contact(
            family_id=family_id, name='Old Name', phone='845-555-2100',
            cell_phone='845-555-2100', email='old@example.test',
            relationship='Friend', supporter_key='phone:8455552100')
        db.session.add_all([profile, contact])
        db.session.commit()
        profile_id = profile.id
        contact_id = contact.id

    response = client.post(f'/supporter-directory/{profile_id}/edit', data={
        'csrf': csrf(client), 'name': 'New Name', 'phone': '(845) 555-2200',
        'email': 'new@example.test'})
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.get(SupporterProfile, profile_id)
        contact = db.session.get(Contact, contact_id)
        assert (profile.name, profile.normalized_phone, profile.email) == (
            'New Name', '8455552200', 'new@example.test')
        assert (contact.name, contact.phone, contact.cell_phone, contact.email,
                contact.supporter_key) == (
            'New Name', '(845) 555-2200', '(845) 555-2200',
            'new@example.test', 'phone:8455552200')


def test_edit_imported_profile_rejects_duplicate_phone(app, client):
    with app.app_context():
        first = SupporterProfile(
            name='First', phone='845-555-2300',
            normalized_phone='8455552300', email='')
        second = SupporterProfile(
            name='Second', phone='845-555-2400',
            normalized_phone='8455552400', email='')
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id

    response = client.post(f'/supporter-directory/{first_id}/edit', data={
        'csrf': csrf(client), 'name': 'First', 'phone': '845-555-2400',
        'email': ''})
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(SupporterProfile, first_id).normalized_phone == '8455552300'


def test_standalone_person_keeps_full_details_without_a_case(app, client):
    response = client.post('/people/new', data={
        'csrf': csrf(client), 'name': 'Standalone Helper',
        'phone': '845-555-2500', 'cell_phone': '845-555-2501',
        'home_phone': '845-555-2502', 'email': 'helper@example.test',
        'home_address': '10 Main Street', 'city': 'Monroe', 'state': 'NY',
        'zip_code': '10950', 'workplace': 'Helper Services',
        'work_phone': '845-555-2503', 'notes': 'Available before Yom Tov',
        'next': '/supporter-directory'})
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8455552500'))
        person = db.session.get(SupporterPerson, profile.person_id)
        assert db.session.scalar(db.select(Contact.id).where(
            Contact.person_id == person.id)) is None
        assert (person.cell_phone, person.home_phone, person.home_address,
                person.city, person.state, person.zip_code, person.workplace,
                person.work_phone, person.notes) == (
            '845-555-2501', '845-555-2502', '10 Main Street', 'Monroe',
            'NY', '10950', 'Helper Services', '845-555-2503',
            'Available before Yom Tov')


def test_people_can_be_related_without_case_or_institution(app, client):
    with app.app_context():
        first = SupporterProfile(name='Avraham Aharon Roth', phone='845-555-2600',
                                 normalized_phone='8455552600', email='')
        second = SupporterProfile(name='Yoel Hersh Roth', phone='845-555-2601',
                                  normalized_phone='8455552601', email='')
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id
        client.get(f'/supporter-directory/{first.id}/edit')
        second_person_id = db.session.get(SupporterProfile, second.id).person_id

    response = client.post(f'/supporter-directory/{first_id}/relationships', data={
        'csrf': csrf(client), 'other_person_id': second_person_id,
        'relationship': 'Brothers', 'relationship_notes': 'Family connection'})
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(PersonRelationship))
        assert row.relationship == 'Brothers'
        assert row.notes == 'Family connection'


def test_person_can_join_shul_network_before_being_connected_to_case(app, client):
    with app.app_context():
        profile = SupporterProfile(name='Future Helper', phone='845-555-2700',
                                   normalized_phone='8455552700', email='')
        institution = Institution(kind='Shul', name='Shared Shul', city='Monroe')
        db.session.add_all([profile, institution])
        db.session.commit()
        profile_id, institution_id = profile.id, institution.id

    response = client.post(f'/supporter-directory/{profile_id}/affiliations', data={
        'csrf': csrf(client), 'institution_id': institution_id,
        'grade': '', 'year_from': '', 'year_to': '',
        'affiliation_note': 'Weekday minyan'})
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(PersonAffiliation).where(
            PersonAffiliation.person_type == 'supporter_profile',
            PersonAffiliation.person_id == profile_id))
        assert row.institution_id == institution_id
        assert row.note == 'Weekday minyan'

    directory = client.get('/community-directories?kind=Shul')
    assert directory.status_code == 200
    assert 'Future Helper' in directory.text

def test_supporter_directory_options_are_bounded_and_searchable(app, client):
    from app import SupporterProfile, db
    with app.app_context():
        db.session.add_all([
            SupporterProfile(name=f'Bulk Person {index:03d}', phone=f'845555{index:04d}',
                             normalized_phone=f'845555{index:04d}', email=f'bulk{index}@example.test')
            for index in range(75)
        ])
        db.session.commit()
    response = client.get('/supporter-directory/options')
    assert response.status_code == 200
    assert len(response.json['profiles']) <= 50
    response = client.get('/supporter-directory/options?q=bulk74%40example.test')
    assert response.status_code == 200
    assert any(profile['email'] == 'bulk74@example.test' for profile in response.json['profiles'])


@pytest.mark.parametrize('phone', ['845-555-9876', ''])
def test_selected_person_needs_only_connection_and_keeps_identity(app, client, phone):
    from person_addresses import PersonAddressDetails
    from person_names import save_names, PersonNames
    with app.app_context():
        person = SupporterPerson(
            identity_key='phone:8455559876' if phone else 'directory:no-phone',
            name='Selected Person', phone=phone, cell_phone=phone,
            home_phone='845-555-9877', email='selected@example.test',
            home_address='12 Main St', city='Monroe', workplace='Office')
        db.session.add(person)
        db.session.flush()
        profile = SupporterProfile(person_id=person.id, name=person.name,
                                   phone=phone, normalized_phone='8455559876' if phone else 'directory:no-phone',
                                   email=person.email)
        details = PersonAddressDetails(person_kind='person', person_id=person.id,
                                       home={'unit': '2'}, work={'street': '20 Work St'},
                                       mailing_preference='home')
        db.session.add_all([profile, details])
        save_names('person', person.id, 'Selected Person', 'משה כהן')
        db.session.commit()
        profile_id, person_id = profile.id, person.id
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))
        person_count = db.session.scalar(db.select(db.func.count()).select_from(SupporterPerson))
    for language in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = language
        response = client.get('/supporter-directory/options')
        assert response.status_code == 200
        selected = next(p for p in response.json['profiles'] if p['id'] == profile_id)
        assert selected['english_name'] == 'Selected Person'
        assert selected['yiddish_name'] == 'משה כהן'
        assert selected['cell_phone'] == phone
        assert selected['home_phone'] == '845-555-9877'
        assert selected['home']['street'] == '12 Main St'
        assert selected['home']['unit'] == '2'
        assert selected['work'] == {'street': '20 Work St', 'company': 'Office'}
    payload = {
        'csrf': csrf(client), 'supporter_profile_id': str(profile_id),
        'name': '', 'name_english': '', 'name_yiddish': '',
        'relationship': 'Friend', 'status': 'To contact',
        'monthly': '0', 'pledge_frequency': 'Monthly',
        'cell_phone': '', 'home_phone': '', 'home_street': 'Stale address',
    }
    response = client.post(f'/families/{family_id}/contacts', data=payload)
    assert response.status_code == 302
    with app.app_context():
        contact = db.session.scalar(db.select(Contact).where(
            Contact.family_id == family_id, Contact.person_id == person_id))
        assert contact is not None
        assert contact.name == 'Selected Person'
        assert contact.cell_phone == phone
        assert contact.home_phone == '845-555-9877'
        assert contact.home_address == '12 Main St'
        assert db.session.scalar(db.select(db.func.count()).select_from(SupporterPerson)) == person_count
        names = db.session.scalar(db.select(PersonNames).where(
            PersonNames.owner_kind == 'person', PersonNames.owner_id == person_id))
        assert names.yiddish_name == 'משה כהן'
    payload['csrf'] = csrf(client)
    assert client.post(f'/families/{family_id}/contacts', data=payload).status_code == 400

def test_selected_profile_cannot_be_added_to_unassigned_case(app, client):
    from app_original import StaffUser
    with app.app_context():
        staff = StaffUser(email='unassigned@example.test', password_hash='unused',
                          role='fundraiser', name='Unassigned')
        profile = SupporterProfile(name='Private selection', phone='8455559988',
                                   normalized_phone='8455559988')
        db.session.add_all([staff, profile])
        db.session.commit()
        staff_id, profile_id = staff.id, profile.id
        family_id = db.session.scalar(db.select(Family.id).order_by(Family.id))
    app.config['DEMO'] = False
    with client.session_transaction() as session:
        session['user_id'] = staff_id
        session['csrf'] = 'test-selection'
    response = client.post(f'/families/{family_id}/contacts', data={
        'csrf': 'test-selection', 'supporter_profile_id': str(profile_id),
        'relationship': 'Friend', 'status': 'To contact', 'monthly': '0',
    })
    assert response.status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(Contact.id).where(
            Contact.family_id == family_id, Contact.phone == '8455559988')) is None


@pytest.mark.parametrize('language', ['en', 'he', 'yi'])
def test_person_workspace_contains_actions_in_all_locales(app, client, language):
    with app.app_context():
        profile = db.session.scalar(db.select(SupporterProfile).order_by(SupporterProfile.id))
        profile_id, person_id = profile.id, profile.person_id
    with client.session_transaction() as session:
        session['language'] = language
    page = client.get(f'/supporter-directory/{profile_id}/edit')
    assert page.status_code == 200
    assert 'id="identity"' in page.text
    assert 'id="addresses"' in page.text
    assert 'id="case-connections"' in page.text
    assert client.get(f'/people/{person_id}').location.endswith(f'/supporter-directory/{profile_id}/edit')
    assert client.get(f'/people/{person_id}/edit').location.endswith(f'/supporter-directory/{profile_id}/edit')
    assert client.get(f'/people/profile/{profile_id}/addresses').location.endswith(f'/supporter-directory/{profile_id}/edit#addresses')


def test_connect_from_person_workspace_stays_on_person_and_reuses_identity(app, client):
    with app.app_context():
        person = SupporterPerson(name='Workspace person', identity_key='phone:7185550198', phone='7185550198')
        db.session.add(person); db.session.flush()
        profile = SupporterProfile(name=person.name, phone=person.phone, normalized_phone='7185550198', person_id=person.id)
        db.session.add(profile); db.session.commit()
        profile_id, person_id = profile.id, person.id
    target = f'/supporter-directory/{profile_id}/edit#case-connections'
    for _ in range(2):
        response = client.post(f'/supporter-directory/{profile_id}/connect', data={
            'csrf': csrf(client), 'family_id': 1, 'relationship': 'Friend'})
        assert response.status_code == 302
        assert response.location.endswith(target)
    with app.app_context():
        contacts = db.session.scalars(db.select(Contact).where(Contact.person_id == person_id)).all()
        assert len(contacts) == 1
        contact_id = contacts[0].id
    page = client.get(f'/supporter-directory/{profile_id}/edit').text
    assert f'/contacts/{contact_id}/communications/message/sms' in page
    assert f'/contacts/{contact_id}/communications/initial-email' in page
    assert 'value="person_workspace"' in page
    assert f'/supporter-directory/{profile_id}/connect' not in client.get('/supporter-directory').text


def test_workspace_hides_unassigned_case_activity(app, client):
    from app import StaffUser, FamilyAssignment, SupporterCommunication
    with app.app_context():
        person = SupporterPerson(name='Shared identity', identity_key='phone:7185550189', phone='7185550189')
        hidden = Family(name='Private unassigned case')
        staff = StaffUser(name='Assigned staff', email='assigned@example.test', password_hash='test', role='family_admin')
        db.session.add_all([person, hidden, staff]); db.session.flush()
        profile = SupporterProfile(name=person.name, phone=person.phone, normalized_phone='7185550189', person_id=person.id)
        db.session.add(profile)
        contact = Contact(name=person.name, family_id=hidden.id, person_id=person.id, supporter_key=person.identity_key, relationship='Friend')
        db.session.add(contact); db.session.flush()
        db.session.add(SupporterCommunication(contact_id=contact.id, family_id=hidden.id, kind='phone_call', body='Private call details', subject='Private history', status='completed'))
        db.session.add(FamilyAssignment(staff_user_id=staff.id, family_id=1))
        db.session.commit()
        profile_id, staff_id = profile.id, staff.id
    app.config['DEMO'] = False
    with client.session_transaction() as session:
        session['user_id'] = staff_id
    response = client.get(f'/supporter-directory/{profile_id}/edit')
    assert response.status_code == 200
    assert '· Private unassigned case ·' not in response.text
    assert 'Private call details' not in response.text
    assert 'Private history' not in response.text
