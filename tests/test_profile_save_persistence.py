"""Exercise the identity form actually rendered by the person workspace."""
from html.parser import HTMLParser

import pytest
from sqlalchemy import event

from app_entry_intake import create_app
from app import Askan, Child, Contact, Family, SupporterPerson, SupporterProfile, db
from person_names import PersonNames, resolve_name_owner, save_names


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test-only'})


class IdentityForm(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_identity = False
        self.in_form = False
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id') == 'identity':
            self.in_identity = True
        if tag == 'form' and self.in_identity:
            self.in_form = True
        if tag == 'input' and self.in_form and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.in_form = False
        if tag == 'section':
            self.in_identity = False


def seed_person(app):
    with app.app_context():
        person = SupporterPerson(identity_key='phone:8455558123', name='Old English',
                                 phone='8455558123', cell_phone='8455558123')
        db.session.add(person)
        db.session.flush()
        save_names('person', person.id, 'Old English', 'אלטער נאמען')
        profiles = [SupporterProfile(person_id=person.id, name=person.name,
                                    phone=person.phone, normalized_phone=key)
                    for key in ('8455558123',)]
        family_ids = db.session.scalars(db.select(Family.id).order_by(Family.id).limit(2)).all()
        if len(family_ids) < 2:
            family = Family(name='Second case', fund_name='')
            db.session.add(family)
            db.session.flush()
            family_ids.append(family.id)
        contacts = [Contact(person_id=person.id, family_id=family_id, name=person.name,
                            phone=person.phone, supporter_key=person.identity_key,
                            relationship='Friend') for family_id in family_ids]
        db.session.add_all(profiles + contacts)
        db.session.commit()
        return person.id, profiles[0].id, [p.id for p in profiles], [c.id for c in contacts]


@pytest.mark.parametrize('english,yiddish', [
    ('New English', 'נייער נאמען'),
    ('Old English', 'בלויז א נייע אידישע נאמען'),
    ('', 'בלויז אידיש'),
])
def test_rendered_identity_form_persists_after_redirect_reload_and_linked_records(app, english, yiddish):
    person_id, profile_id, profile_ids, contact_ids = seed_person(app)
    client = app.test_client()
    url = f'/supporter-directory/{profile_id}/edit'
    page = client.get(url)
    assert page.status_code == 200
    form = IdentityForm(page.text).values
    assert form['name'] == 'Old English'  # the hidden legacy field is stale
    form.update(name_english=english, name_yiddish=yiddish,
                phone='8455558222', home_phone='8455558333', cell_phone='8455558444',
                email='saved@example.test', work_phone='8455558555', notes='Saved notes')
    response = client.post(url, data=form, follow_redirects=True)
    assert response.status_code == 200
    for _ in range(2):
        reloaded = client.get(url)
        values = IdentityForm(reloaded.text).values
        assert values['name_english'] == english
        assert values['name_yiddish'] == yiddish
        assert values['email'] == 'saved@example.test'
    with app.app_context():
        person = db.session.get(SupporterPerson, person_id)
        expected_name = english or yiddish
        assert person.name == expected_name
        names = db.session.scalar(db.select(PersonNames).where(
            PersonNames.owner_kind == 'person', PersonNames.owner_id == person_id))
        assert (names.english_name, names.yiddish_name) == (english, yiddish)
        for ident in profile_ids:
            profile = db.session.get(SupporterProfile, ident)
            assert (profile.person_id, profile.name, profile.phone, profile.email) == (
                person_id, expected_name, '8455558222', 'saved@example.test')
        for ident in contact_ids:
            contact = db.session.get(Contact, ident)
            assert contact.person_id == person_id
            for field in ('name', 'phone', 'home_phone', 'cell_phone', 'email', 'work_phone', 'notes'):
                assert getattr(contact, field) == getattr(person, field)


def test_workspace_get_does_not_canonicalize_unrelated_legacy_profiles(app):
    _, profile_id, _, _ = seed_person(app)
    with app.app_context():
        legacy = SupporterProfile(name='Unlinked import', phone='8455558777',
                                  normalized_phone='8455558777')
        db.session.add(legacy)
        db.session.commit()
        legacy_id = legacy.id
        engine = db.engine
    writes = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in ('UPDATE', 'INSERT', 'DELETE'):
            writes.append(statement)

    client = app.test_client()
    client.get('/')
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        assert client.get(f'/supporter-directory/{profile_id}/edit').status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert not writes, writes
    with app.app_context():
        assert db.session.get(SupporterProfile, legacy_id).person_id is None


def test_save_uses_profile_canonical_id_not_another_contacts_stale_phone_key(app):
    person_id, profile_id, _, contact_ids = seed_person(app)
    with app.app_context():
        person = db.session.get(SupporterPerson, person_id)
        person.identity_key = 'phone:8455558999'
        for ident in contact_ids:
            db.session.get(Contact, ident).supporter_key = person.identity_key
        # A legacy snapshot has the profile's old phone key. It is not this
        # person: its explicit canonical ID must beat a coincidental key match.
        unrelated = db.session.scalar(db.select(Contact).where(
            Contact.id.not_in(contact_ids)).order_by(Contact.id))
        unrelated.supporter_key = 'phone:8455558123'
        unrelated_person_id = unrelated.person_id
        unrelated_name = unrelated.name
        db.session.commit()
    client = app.test_client()
    url = f'/supporter-directory/{profile_id}/edit'
    form = IdentityForm(client.get(url).text).values
    form.update(name_english='Correct canonical person', name_yiddish='ריכטיג',
                email='canonical@example.test', phone='8455558888')
    assert client.post(url, data=form, follow_redirects=True).status_code == 200
    with app.app_context():
        assert db.session.get(SupporterPerson, person_id).name == 'Correct canonical person'
        assert db.session.get(SupporterPerson, unrelated_person_id).name == unrelated_name


def test_role_profile_save_does_not_treat_its_own_linked_contact_as_a_duplicate(app):
    person_id, profile_id, _, _ = seed_person(app)
    with app.app_context():
        db.session.get(SupporterProfile, profile_id).normalized_phone = 'family:9999:father'
        db.session.commit()
    client = app.test_client()
    url = f'/supporter-directory/{profile_id}/edit'
    form = IdentityForm(client.get(url).text).values
    form.update(name_english='Saved role person', name_yiddish='געראטעוועט')
    response = client.post(url, data=form, follow_redirects=True)
    assert response.status_code == 200, response.text
    with app.app_context():
        assert db.session.get(SupporterPerson, person_id).name == 'Saved role person'


@pytest.mark.parametrize('kind,cell,primary', [
    ('family', '8455559777', '8455559666'), ('family', '', '8455559666'),
    ('askan', '8455559777', '8455559666'),
    ('child', '8455559777', '8455559666'), ('child', '8455559777', '8455559888')])
def test_profile_save_refreshes_linked_role_snapshot_and_survives_role_resync(app, kind, cell, primary):
    with app.app_context():
        if kind == 'family':
            role = db.session.get(Family, 1)
        elif kind == 'askan':
            role = Askan(name='Old role name', phone='8455558111')
            db.session.add(role)
            db.session.flush()
            for sync in app.extensions['askan_profile_person_sync']:
                sync(role)
        else:
            role = Child(family_id=1, name='Old child name', age=12, school='',
                         married=True, cell_phone='8455558111')
            db.session.add(role)
        db.session.commit()
        if kind == 'child':
            app.extensions['sync_married_child_supporters'](role)
            db.session.commit()
        owner_kind, person_id, _ = resolve_name_owner(kind, role.id)
        assert owner_kind == 'person'
        person = db.session.get(SupporterPerson, person_id)
        profile = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.person_id == person_id))
        assert profile is not None
        role_id, profile_id = role.id, profile.id
    client = app.test_client()
    url = f'/supporter-directory/{profile_id}/edit'
    form = IdentityForm(client.get(url).text).values
    form.update(name_english='Updated role identity', name_yiddish='נייע אידענטיטעט',
                phone=primary, cell_phone=cell, home_phone='8455559888',
                email='role@example.test', work_phone='8455559999', notes='Role note')
    assert client.post(url, data=form, follow_redirects=True).status_code == 200
    with app.app_context():
        model = dict(family=Family, askan=Askan, child=Child)[kind]
        role = db.session.get(model, role_id)
        assert role.name == 'Updated role identity'
        if kind == 'family':
            assert (role.phone, role.email) == (primary, 'role@example.test')
            # This is the callback invoked on the next family intake save.
            for sync in app.extensions['family_profile_person_sync']:
                sync(role)
        elif kind == 'askan':
            assert (role.phone, role.cell_phone, role.email) == (
                primary, '8455559777', 'role@example.test')
            for sync in app.extensions['askan_profile_person_sync']:
                sync(role)
        else:
            assert (role.home_phone, role.cell_phone) == ('8455559888', '8455559777')
            role.grade = 'New grade'
            app.extensions['sync_married_child_supporters'](role)
        db.session.commit()
        assert db.session.get(SupporterPerson, person_id).name == 'Updated role identity'
        assert db.session.get(SupporterPerson, person_id).cell_phone == cell
        assert db.session.get(SupporterPerson, person_id).phone == primary
        assert db.session.get(SupporterPerson, person_id).identity_key == 'phone:' + primary
        names = db.session.scalar(db.select(PersonNames).where(
            PersonNames.owner_kind == 'person', PersonNames.owner_id == person_id))
        assert (names.english_name, names.yiddish_name) == (
            'Updated role identity', 'נייע אידענטיטעט')
    assert IdentityForm(client.get(url).text).values['name_english'] == 'Updated role identity'


def test_legacy_target_get_is_read_only_and_save_can_clear_optional_fields(app):
    with app.app_context():
        profile = SupporterProfile(name='Legacy target', phone='8455558777',
                                  normalized_phone='8455558777')
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
        engine = db.engine
    client = app.test_client()
    client.get('/')
    writes = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in ('UPDATE', 'INSERT', 'DELETE'):
            writes.append(statement)

    event.listen(engine, 'before_cursor_execute', capture)
    try:
        page = client.get(f'/supporter-directory/{profile_id}/edit')
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert page.status_code == 200
    assert not writes, writes
    form = IdentityForm(page.text).values
    assert form['cell_phone'] == '8455558777'
    form.update(name_english='Saved legacy target', cell_phone='', home_phone='',
                phone='', email='', notes='')
    response = client.post(f'/supporter-directory/{profile_id}/edit', data=form,
                           follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        profile = db.session.get(SupporterProfile, profile_id)
        person = db.session.get(SupporterPerson, profile.person_id)
        assert person.name == 'Saved legacy target'
        assert (person.phone, person.cell_phone, person.home_phone, person.email) == ('', '', '', '')


def test_unlinked_profile_form_uses_existing_canonical_bilingual_names(app):
    with app.app_context():
        person = SupporterPerson(identity_key='phone:8455558012', name='Current English',
                                 phone='8455558012', cell_phone='8455558013')
        db.session.add(person)
        db.session.flush()
        save_names('person', person.id, 'Current English', 'איצטיגער נאמען')
        profile = SupporterProfile(name='Stale snapshot', phone='8455558012',
                                  normalized_phone='8455558012')
        db.session.add(profile)
        db.session.commit()
        profile_id, person_id = profile.id, person.id
    client = app.test_client()
    url = f'/supporter-directory/{profile_id}/edit'
    form = IdentityForm(client.get(url).text).values
    assert (form['name_english'], form['name_yiddish']) == ('Current English', 'איצטיגער נאמען')
    with app.app_context():
        assert db.session.get(SupporterProfile, profile_id).person_id is None
    form['email'] = 'email-only@example.test'
    assert client.post(url, data=form, follow_redirects=True).status_code == 200
    with app.app_context():
        assert db.session.get(SupporterProfile, profile_id).person_id == person_id
        assert db.session.get(SupporterPerson, person_id).name == 'Current English'
    assert IdentityForm(client.get(url).text).values['name_yiddish'] == 'איצטיגער נאמען'