import csv
from collections import Counter
from io import BytesIO, StringIO

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from flask import g

from app_entry import create_app
from app import (
    Contact, PersonBookRecord, StaffTask, SupporterPerson, SupporterProfile, db,
)
from app_original import Audit, StaffUser
from book_directory import PersonFamilyConnection, preload_family_connections, save_family_names
from person_addresses import (
    PersonAddressDetails, address_details, preload_addresses,
    save_new_supporter_addresses,
)
from person_names import PersonNames, names_row, preload_names, save_names


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test'})


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def rows(count, start=0, *, book=False, changed=False):
    output = StringIO()
    fields = ['Name', 'English Name', 'Yiddish Name', 'Phone', 'Home address',
              'Apartment', 'City', 'State', 'ZIP', 'Father name']
    if book:
        fields += ['Book ID', 'Book source', 'Father book ID']
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for i in range(start, start + count):
        name = f'Changed Person {i:03}' if changed else f'Person {i:03}'
        row = {
            'Name': name, 'English Name': name, 'Yiddish Name': f'נאמען {i:03}',
            'Phone': f'845555{i:04}', 'Home address': f'{i + 1} Main St',
            'Apartment': f'{i:02}', 'City': 'Monroe', 'State': 'NY',
            'ZIP': f'{10000 + i}', 'Father name': f'Father {i:03}',
        }
        if book:
            row.update({'Book ID': f'book-{i:03}', 'Book source': 'performance',
                        'Father book ID': f'parent-{i:03}'})
        writer.writerow(row)
    return output.getvalue()


def no_phone_rows(count, start=0):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'Name', 'English Name', 'Yiddish Name', 'Home address', 'Apartment',
        'City', 'State', 'ZIP', 'Father name',
    ])
    writer.writeheader()
    for i in range(start, start + count):
        writer.writerow({
            'Name': f'No phone {i:03}', 'English Name': f'No phone {i:03}',
            'Yiddish Name': f'ללא טלפון {i:03}',
            'Home address': f'{i + 1} Oak St', 'Apartment': f'{i:02}',
            'City': 'Monroe', 'State': 'NY', 'ZIP': f'{20000 + i}',
            'Father name': f'Father {i:03}',
        })
    return output.getvalue()


def import_csv(app, client, content, family_id=None):
    token = csrf(client)
    statements = []
    listener_state = {'active': False}

    def count_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    def stop_after_import_commit(session):
        if listener_state['active']:
            # The endpoint renders the directory after committing. Keep those
            # GET-like presentation reads out of the import query counts.
            event.remove(engine, 'before_cursor_execute', count_statement)
            listener_state['active'] = False

    with app.app_context():
        engine = db.engine
    event.listen(Session, 'after_commit', stop_after_import_commit)
    event.listen(engine, 'before_cursor_execute', count_statement)
    listener_state['active'] = True
    try:
        response = client.post('/supporter-directory', data={
            'csrf': token, 'family_id': str(family_id) if family_id else '',
            'file': (BytesIO(content.encode()), 'people.csv')
        }, content_type='multipart/form-data')
    finally:
        event.remove(Session, 'after_commit', stop_after_import_commit)
        if listener_state['active']:
            event.remove(engine, 'before_cursor_execute', count_statement)
    assert response.status_code == 200, response.get_data(as_text=True)
    with client.session_transaction() as session:
        result = dict(session['people_import_result'])
    operations = [statement.lstrip().split(None, 1)[0].upper()
                  for statement in statements if statement.strip()]
    return operations.count('SELECT'), len(statements), result, dict(Counter(operations))


@pytest.mark.parametrize('book', [False, True], ids=['phone-import', 'book-import'])
def test_import_selects_do_not_grow_linearly_and_duplicates_are_preserved(app, book):
    client = app.test_client()
    fresh, repeated = {}, {}
    for size, start in ((10, 0), (40, 100), (50, 200)):
        selects, total, initial, ops = import_csv(
            app, client, rows(size, start=start, book=book))
        assert initial['created'] == size
        assert initial['duplicates'] == 0
        fresh[size] = selects, total, ops

        selects, total, duplicate, ops = import_csv(
            app, client, rows(size, start=start, book=book, changed=True))
        assert duplicate['created'] == 0
        assert duplicate['duplicates'] == size
        assert duplicate['skipped'] == 0
        repeated[size] = selects, total, ops

    # SELECTs include raw connection reads from mapper hooks. This fixture uses
    # SQLite, whose emitted INSERT calls are not PostgreSQL executemany batches;
    # total calls are reported separately and are expected to scale with rows.
    print(f"{'book' if book else 'phone'} imports: fresh {fresh}; repeated {repeated}")
    assert max(value[0] for value in fresh.values()) <= min(
        value[0] for value in fresh.values()) + 8, fresh
    assert max(value[0] for value in repeated.values()) <= min(
        value[0] for value in repeated.values()) + 8, repeated

    with app.app_context():
        imported_profiles = db.session.scalars(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone.in_(
                [f'845555{i:04}' for i in range(200, 250)]))).all()
        assert len(imported_profiles) == 50
        imported_people = [db.session.get(SupporterPerson, profile.person_id)
                           for profile in imported_profiles]
        assert len({person.id for person in imported_people}) == 50
        if book:
            assert db.session.scalar(db.select(db.func.count(PersonBookRecord.id)).where(
                PersonBookRecord.source == 'performance')) == 100
            assert db.session.scalar(db.select(db.func.count(Contact.id)).where(
                Contact.supporter_key.like('phone:845555%'))) == 0
        first = next(profile for profile in imported_profiles
                     if profile.normalized_phone == '8455550200')
        person = db.session.get(SupporterPerson, first.person_id)
        assert person.name == 'Person 200'
        assert person.home_address == '201 Main St'
        assert names_row('person', person.id).english_name == 'Person 200'


def test_family_linked_import_and_no_phone_repeat_keep_family_names_and_addresses(app):
    client = app.test_client()
    linked_fresh, linked_repeat = {}, {}
    for size, start in ((10, 500), (40, 600), (50, 700)):
        selects, total, first, ops = import_csv(
            app, client, rows(size, start=start), family_id=1)
        assert (first['created'], first['linked'], first['duplicates']) == (size, size, 0)
        linked_fresh[size] = selects, total, ops

        selects, total, repeat, ops = import_csv(
            app, client, rows(size, start=start, changed=True), family_id=1)
        assert (repeat['created'], repeat['linked'], repeat['duplicates']) == (0, 0, size)
        linked_repeat[size] = selects, total, ops

    print(f"linked phone imports: fresh {linked_fresh}; repeated {linked_repeat}")
    assert max(value[0] for value in linked_fresh.values()) <= min(
        value[0] for value in linked_fresh.values()) + 15, linked_fresh
    assert max(value[0] for value in linked_repeat.values()) <= min(
        value[0] for value in linked_repeat.values()) + 15, linked_repeat

    content = no_phone_rows(50)
    no_phone_first = import_csv(app, client, content, family_id=1)[2]
    no_phone_repeat = import_csv(app, client, content, family_id=1)[2]
    assert (no_phone_first['created'], no_phone_first['linked']) == (50, 50)
    assert (no_phone_repeat['created'], no_phone_repeat['duplicates'],
            no_phone_repeat['linked']) == (0, 50, 0)

    with app.app_context():
        phone_profile = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.normalized_phone == '8455550500'))
        phone_person = db.session.get(SupporterPerson, phone_profile.person_id)
        phone_family = db.session.get(PersonFamilyConnection, phone_person.id)
        assert phone_person.name == 'Person 500'
        assert phone_person.home_address == '501 Main St'
        assert phone_family.father_name == 'Father 500'
        assert db.session.scalar(db.select(db.func.count(Contact.id)).where(
            Contact.family_id == 1, Contact.person_id == phone_person.id)) == 1
        no_phone_profile = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.name == 'No phone 000'))
        no_phone_person = db.session.get(SupporterPerson, no_phone_profile.person_id)
        family = db.session.get(PersonFamilyConnection, no_phone_person.id)
        assert no_phone_person.name == 'No phone 000'
        assert no_phone_person.home_address == '1 Oak St'
        assert family.father_name == 'Father 000'
        assert names_row('person', no_phone_person.id).yiddish_name == 'ללא טלפון 000'
        assert db.session.scalar(db.select(db.func.count(Contact.id)).where(
            Contact.family_id == 1, Contact.person_id == no_phone_person.id)) == 1


def test_linked_book_imports_batch_queries_and_queue_one_consistent_followup(app):
    client = app.test_client()
    with app.app_context():
        assignee = StaffUser(
            email='directory-followup@example.test', password_hash='test',
            name='Directory follow-up owner', role='organization_admin',
            status='active')
        db.session.add(assignee)
        db.session.commit()
        assignee_id = assignee.id

    fresh, repeated = {}, {}
    for size, start in ((10, 800), (40, 1000), (50, 1100)):
        content = rows(size, start=start, book=True)
        selects, total, initial, ops = import_csv(
            app, client, content, family_id=1)
        assert (initial['created'], initial['duplicates'], initial['linked']) == (
            size, 0, size)
        fresh[size] = selects, total, ops

        with app.app_context():
            phones = [f'845555{i:04}' for i in range(start, start + size)]
            profiles = db.session.scalars(db.select(SupporterProfile).where(
                SupporterProfile.normalized_phone.in_(phones))).all()
            contacts = db.session.scalars(db.select(Contact).where(
                Contact.family_id == 1,
                Contact.person_id.in_([profile.person_id for profile in profiles]))).all()
            assert len(profiles) == len(contacts) == size
            tasks = db.session.scalars(db.select(StaffTask).where(
                StaffTask.source_contact_id.in_([contact.id for contact in contacts]))).all()
            assert len(tasks) == size
            assert {task.assigned_to for task in tasks} == {assignee_id}
            assert {task.created_by for task in tasks} == {assignee_id}
            expected_actions = {
                f'Created automatic supporter follow-up: Person {i:03}'
                for i in range(start, start + size)
            }
            actions = set(db.session.scalars(db.select(Audit.action).where(
                Audit.action.in_(expected_actions))).all())
            assert actions == expected_actions

        selects, total, duplicate, ops = import_csv(
            app, client, rows(size, start=start, book=True, changed=True),
            family_id=1)
        assert duplicate['created'] == 0
        assert duplicate['duplicates'] == size
        assert duplicate['linked'] == 0
        repeated[size] = selects, total, ops

        with app.app_context():
            task_count = db.session.scalar(db.select(db.func.count(StaffTask.id)).where(
                StaffTask.source_contact_id.in_([contact.id for contact in contacts])))
            assert task_count == size
            actions = db.session.scalars(db.select(Audit.action).where(
                Audit.action.in_(expected_actions))).all()
            assert len(actions) == size

    print(f"linked book imports: fresh {fresh}; repeated {repeated}")
    assert max(value[0] for value in fresh.values()) <= min(
        value[0] for value in fresh.values()) + 12, fresh
    assert max(value[0] for value in repeated.values()) <= min(
        value[0] for value in repeated.values()) + 12, repeated


def test_no_phone_import_selects_stay_bounded_for_fresh_and_repeat_uploads(app):
    client = app.test_client()
    fresh, repeated = {}, {}
    for size, start in ((40, 1200), (50, 1400)):
        content = no_phone_rows(size, start=start)
        selects, total, initial, ops = import_csv(
            app, client, content, family_id=1)
        assert (initial['created'], initial['duplicates'], initial['linked']) == (
            size, 0, size)
        fresh[size] = selects, total, ops

        selects, total, duplicate, ops = import_csv(
            app, client, content, family_id=1)
        assert (duplicate['created'], duplicate['duplicates'],
                duplicate['linked']) == (0, size, 0)
        repeated[size] = selects, total, ops

    print(f"no-phone imports: fresh {fresh}; repeated {repeated}")
    assert max(value[0] for value in fresh.values()) <= min(
        value[0] for value in fresh.values()) + 8, fresh
    assert max(value[0] for value in repeated.values()) <= min(
        value[0] for value in repeated.values()) + 8, repeated


def test_import_related_negative_caches_track_writes_without_extra_reads(app):
    from sqlalchemy import event

    with app.app_context():
        person = SupporterPerson(identity_key='cache-test:write', name='')
        db.session.add(person)
        db.session.commit()
        person_id = person.id

    with app.test_request_context('/supporter-directory', method='POST'):
        person = db.session.get(SupporterPerson, person_id)
        name_key = ('person', person_id, 'name')
        address_key = ('person', person_id)
        preload_names({name_key})
        preload_addresses({address_key})
        preload_family_connections({person_id})
        selects = []

        def count_select(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith('SELECT'):
                selects.append(statement)

        engine = db.engine
        event.listen(engine, 'before_cursor_execute', count_select)
        try:
            save_names('person', person_id, 'Writer', 'כותב')
            save_new_supporter_addresses(app, Contact(person_id=person_id), {
                'home_street': '1 Cache Lane', 'home_unit': 'Suite 4',
            }, person=person, sync=False)
            save_family_names(person_id, {'father_name': 'Father writer'})
            # These second writes must see the newly added row, not the cached
            # None from preload (and must not perform another lookup).
            save_names('person', person_id, 'Writer updated', 'כותב')
            save_new_supporter_addresses(app, Contact(person_id=person_id), {
                'home_city': 'Monroe',
            }, person=person, sync=False)
            save_family_names(person_id, {'father_inlaw_name': 'Father-in-law writer'})
        finally:
            event.remove(engine, 'before_cursor_execute', count_select)

        assert selects == []
        assert db.session.scalar(db.select(db.func.count(PersonNames.id)).where(
            PersonNames.owner_kind == 'person', PersonNames.owner_id == person_id)) == 1
        assert db.session.scalar(db.select(db.func.count(PersonAddressDetails.id)).where(
            PersonAddressDetails.person_kind == 'person',
            PersonAddressDetails.person_id == person_id)) == 1
        assert db.session.scalar(db.select(db.func.count(PersonFamilyConnection.person_id)).where(
            PersonFamilyConnection.person_id == person_id)) == 1
        assert names_row('person', person_id).english_name == 'Writer updated'
        details = address_details('person', person_id)
        assert details.home == {'unit': 'Suite 4'}
        assert person.home_address == '1 Cache Lane'
        assert person.city == 'Monroe'
        family = preload_family_connections({person_id})[person_id]
        assert family.father_name == 'Father writer'
        assert family.father_inlaw_name == 'Father-in-law writer'

        other = SupporterPerson(identity_key='cache-test:address-writer', name='')
        db.session.add(other)
        db.session.flush()
        key = ('person', other.id)
        preload_addresses({key})
        assert address_details(*key) is None
        written = PersonAddressDetails(
            person_kind='person', person_id=other.id,
            home={'street': 'Second writer'}, work={},
            mailing_preference='')
        db.session.add(written)
        db.session.flush()
        assert address_details(*key) is written
        preload_family_connections({other.id})
        family_written = PersonFamilyConnection(
            person_id=other.id, father_name='Direct family writer',
            father_inlaw_name='', father_person_id=None,
            father_inlaw_person_id=None, father_manually_set=False,
            father_inlaw_manually_set=False)
        db.session.add(family_written)
        db.session.flush()
        assert preload_family_connections({other.id})[other.id] is family_written
        db.session.rollback()


def test_import_lookup_caches_invalidate_after_commit_and_general_name_hooks(app):
    with app.app_context():
        person = SupporterPerson(identity_key='cache-test:transaction', name='')
        db.session.add(person)
        db.session.commit()
        person_id = person.id

    with app.test_request_context('/ordinary-person-write', method='POST'):
        name_key = ('person', person_id, 'name')
        address_key = ('person', person_id)
        assert preload_names({name_key}) is None
        preload_addresses({address_key})
        assert preload_family_connections({person_id})[person_id] is None
        # The new request transaction must not reuse the three negative cache
        # entries left behind by the transaction above.
        db.session.commit()
        db.session.execute(PersonNames.__table__.insert().values(
            owner_kind='person', owner_id=person_id, field='name',
            english_name='Stored', yiddish_name='געהיטן'))
        db.session.execute(PersonAddressDetails.__table__.insert().values(
            person_kind='person', person_id=person_id,
            home={'street': 'Committed St'}, work={}, mailing_preference=''))
        db.session.execute(PersonFamilyConnection.__table__.insert().values(
            person_id=person_id, father_name='Committed father',
            father_inlaw_name='', father_person_id=None,
            father_inlaw_person_id=None, father_manually_set=False,
            father_inlaw_manually_set=False))
        db.session.commit()
        assert names_row('person', person_id).english_name == 'Stored'
        assert address_details('person', person_id).home == {'street': 'Committed St'}
        assert preload_family_connections({person_id})[person_id].father_name == 'Committed father'

    with app.app_context():
        person = SupporterPerson(identity_key='cache-test:mapper', name='Original Mapper')
        db.session.add(person)
        db.session.commit()
        person_id = person.id

    with app.test_request_context('/ordinary-person-write', method='POST', data={
            'name': 'Updated Mapper', 'name_english': 'Updated Mapper',
            'name_yiddish': 'מעדזשער'}):
        key = ('person', person_id, 'name')
        preload_names({key})
        assert names_row(*key).english_name == 'Original Mapper'
        person = db.session.get(SupporterPerson, person_id)
        person.name = 'Updated Mapper'
        db.session.flush()
        # The mapper writes through its connection. The retained ORM row must
        # be expired/refreshed instead of returning the pre-write value.
        assert names_row(*key).english_name == 'Updated Mapper'
        db.session.rollback()


def test_import_canonical_cache_does_not_reuse_a_changed_identity_key(app):
    old_key = 'phone:8455559999'
    with app.app_context():
        person = SupporterPerson(identity_key=old_key, name='Old identity')
        db.session.add(person)
        db.session.flush()
        contact = Contact(
            person_id=person.id, family_id=1, name=person.name,
            relationship='Other', supporter_key=old_key, status='To contact')
        db.session.add(contact)
        db.session.commit()
        person_id, contact_id = person.id, contact.id

    with app.test_request_context('/supporter-directory', method='POST'):
        g._batch_person_import = True
        identity = app.extensions['supporter_identity']
        assert identity['preload_people']({old_key})[old_key].id == person_id
        contact = db.session.get(Contact, contact_id)
        identity['update'](contact, {'supporter_key': 'phone:8455558888'})
        new_profile = SupporterProfile(
            name='New profile', phone='8455559999',
            normalized_phone='8455559999', email='')
        db.session.add(new_profile)
        # A new profile reusing the old phone must not inherit the person after
        # that identity has been moved to a different key in this transaction.
        assert identity['preload_profiles']([new_profile]) == {}
        db.session.rollback()