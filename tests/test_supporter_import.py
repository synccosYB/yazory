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
    assert first.status_code == 302 and '/contacts/' in first.headers['Location']
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
    assert len(profile_selects) <= 3



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
