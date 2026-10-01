import csv
from io import BytesIO, StringIO

import pytest
from app_entry import create_app
from app import db, Family, SupporterPerson, SupporterProfile, Contact, PersonRelationship
from book_directory import PersonBookRecord, PersonFamilyConnection


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def upload(client, rows, **extra):
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
    writer.writeheader()
    writer.writerows(rows)
    return client.post('/supporter-directory', data={'csrf': csrf(client),
        'file': (BytesIO(out.getvalue().encode()), 'people.csv'), **extra}, content_type='multipart/form-data')


def entry(ident='00157', **extra):
    return {'Book ID': ident, 'Yiddish/Hebrew name': 'יואל אבערלאנדער',
        'Yiddish first name': 'יואל', 'Yiddish last name': 'אבערלאנדער',
        'Father name': 'שלמה', 'Father-in-law name': 'ברוך גרינפעלד',
        'Phone 1': '(718) 555-0199', 'Home address': '12 Main St.', 'Apartment': '04-A',
        'City': 'Brooklyn', 'State': 'NY', 'Zip code': '01001',
        'Original relationship line': 'ר׳ שלמה - ר׳ ברוך גרינפעלד',
        'Source rows': 'Book page 2, ID 00157', 'Notes': 'Original source note',
        'Review': 'Check spelling', **extra}


@pytest.mark.parametrize('lang', ['en', 'he', 'yi'])
def test_directory_pages_bound_large_import_and_search_all_records(app, lang):
    client = app.test_client()
    client.get('/')
    with app.app_context():
        db.session.add_all([SupporterProfile(
            name=f'PagingFixture {i:04d}', phone='',
            normalized_phone=f'pagination-test:{i}') for i in range(105)])
        db.session.commit()
    with client.session_transaction() as session:
        session['language'] = lang
    def page(number=1, query='PagingFixture'):
        response = client.get('/supporter-directory', query_string={'q':query, 'page':number})
        assert response.status_code == 200
        return response.get_data(as_text=True)
    first = page()
    assert first.count('class="supporter-accordion-item"') == 50
    assert 'PagingFixture 0000' in first and 'PagingFixture 0050' not in first
    assert 'page=2' in first and 'q=PagingFixture' in first
    second = page(2)
    assert second.count('class="supporter-accordion-item"') == 50
    assert 'PagingFixture 0050' in second and 'PagingFixture 0000' not in second
    last = page(999999999999999999999)
    assert last.count('class="supporter-accordion-item"') == 5
    assert 'PagingFixture 0104' in last
    assert 'PagingFixture 0000' in page(-1)
    assert 'PagingFixture 0000' in page('invalid')
    searched = page(query='PagingFixture 0104')
    assert searched.count('class="supporter-accordion-item"') == 1
    assert 'PagingFixture 0104' in searched
    assert page(query='NoMatchingDirectoryPerson').count('class="supporter-accordion-item"') == 0


def test_reference_details_persist_and_repeat_does_not_duplicate(app):
    client = app.test_client()
    assert upload(client, [entry()], family_id='1').status_code == 200
    with app.app_context():
        record = db.session.scalar(db.select(PersonBookRecord))
        person = db.session.get(SupporterPerson, record.person_id)
        assert record.book_id == '00157' and record.first_name == 'יואל'
        assert record.relationship_text == 'ר׳ שלמה - ר׳ ברוך גרינפעלד'
        assert (record.source_ref, record.notes, record.review) == ('Book page 2, ID 00157', 'Original source note', 'Check spelling')
        assert (person.home_address, person.zip_code, person.notes) == ('12 Main St.', '01001', 'Original source note')
        family = db.session.get(PersonFamilyConnection, person.id)
        assert family.father_name == 'שלמה' and not family.father_person_id
        from person_addresses import address_details
        assert address_details('person', person.id).home['unit'] == '04-A'
        person_id = person.id
        profile_id = db.session.scalar(db.select(SupporterProfile.id).where(SupporterProfile.person_id == person.id))
    assert upload(client, [entry()], family_id='1').status_code == 200
    with client.session_transaction() as session:
        assert session['people_import_result']['created'] == 0
        assert session['people_import_result']['linked'] == 0
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(PersonBookRecord.id))) == 1
        assert db.session.scalar(db.select(db.func.count(Contact.id)).where(Contact.person_id == person_id)) == 1
    assert '00157' in client.get('/supporter-directory?q=00157').text
    assert 'Original source note' in client.get(f'/supporter-directory/{profile_id}/edit').text


def test_address_only_id_survives_changed_source_text_and_later_phone(app):
    client = app.test_client()
    assert upload(client, [entry(**{'Phone 1': ''})]).status_code == 200
    with app.app_context():
        person_id = db.session.scalar(db.select(PersonBookRecord.person_id))
    assert upload(client, [entry(**{'Home address': 'Corrected street'})]).status_code == 200
    with app.app_context():
        record = db.session.scalar(db.select(PersonBookRecord))
        assert record.person_id == person_id
        person = db.session.get(SupporterPerson, person_id)
        assert person.phone == '(718) 555-0199'
        assert person.home_address == '12 Main St.'
        assert db.session.scalar(db.select(db.func.count(PersonBookRecord.id))) == 1


def test_book_id_conflict_does_not_merge_people(app):
    client = app.test_client()
    assert upload(client, [entry()]).status_code == 200
    assert upload(client, [entry('00158')]).status_code == 200
    with client.session_transaction() as session:
        assert session['people_import_result']['skipped'] == 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(PersonBookRecord.id))) == 1


def test_same_id_in_different_books_is_not_the_same_person(app):
    client = app.test_client()
    assert upload(client, [entry(**{'Phone 1': ''})], book_source='Book A').status_code == 200
    assert upload(client, [entry(**{'Phone 1': ''})], book_source='Book B').status_code == 200
    with app.app_context():
        records = db.session.scalars(db.select(PersonBookRecord)).all()
        assert len(records) == 2 and records[0].person_id != records[1].person_id


def test_later_page_resolves_explicit_id_across_cases(app):
    client = app.test_client()
    assert upload(client, [entry(**{'Father book ID': '00999'})], family_id='1').status_code == 200
    with app.app_context():
        child = db.session.scalar(db.select(PersonBookRecord))
        child_id = child.person_id
        assert db.session.get(PersonFamilyConnection, child_id).father_person_id is None
        second = Family(name='Second case', status='New referral')
        db.session.add(second); db.session.commit(); second_id = second.id
    father = {'Book ID': '00999', 'Name': 'שלמה אבערלאנדער', 'Phone': '7185550299'}
    assert upload(client, [father], family_id=str(second_id)).status_code == 200
    with app.app_context():
        target = db.session.scalar(db.select(PersonBookRecord).where(PersonBookRecord.book_id == '00999'))
        assert db.session.get(PersonFamilyConnection, child_id).father_person_id == target.person_id


def test_manual_connections_need_neither_book_nor_case(app):
    client = app.test_client()
    assert upload(client, [{'Name': 'Child', 'Phone': '8455551001'}, {'Name': 'Father', 'Phone': '8455551002'}]).status_code == 200
    with app.app_context():
        child = db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.phone == '8455551001'))
        father = db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.phone == '8455551002'))
        child_profile, child_id, father_id = child.id, child.person_id, father.person_id
    assert client.post(f'/supporter-directory/{child_profile}/family-connections', data={
        'csrf': csrf(client), 'father_person_id': str(father_id)}).status_code == 302
    with app.app_context():
        assert db.session.get(PersonFamilyConnection, child_id).father_person_id == father_id
        assert db.session.scalar(db.select(PersonBookRecord)) is None
        assert db.session.scalar(db.select(Contact.id).where(Contact.person_id.in_([child_id, father_id]))) is None
    assert client.post(f'/supporter-directory/{child_profile}/family-connections', data={
        'csrf': csrf(client), 'father_person_id': str(child_id)}).status_code == 400


def test_family_names_import_without_book_or_phone(app):
    client = app.test_client()
    assert upload(client, [{'Name': 'No Book', 'Father name': 'Father text'}]).status_code == 200
    with app.app_context():
        p = db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.name == 'No Book'))
        assert db.session.get(PersonFamilyConnection, p.person_id).father_name == 'Father text'
        assert db.session.scalar(db.select(PersonBookRecord)) is None


@pytest.mark.parametrize('language,label', [('en','Family connections'),('he','קשרי משפחה'),('yi','משפחה קרבות')])
def test_family_and_reference_ui_localized(app, language, label):
    client = app.test_client(); assert upload(client, [entry()]).status_code == 200
    with app.app_context():
        p = db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.phone == '(718) 555-0199'))
        ident = p.id
    with client.session_transaction() as session:
        session['language'] = language
    page = client.get(f'/supporter-directory/{ident}/edit')
    assert page.status_code == 200 and label in page.text
    assert 'id="family-connections"' in page.text
    assert '<details class="card padded" id="book-details">' in page.text


def test_import_protects_manual_relationship_and_source_corrections(app):
    client = app.test_client(); assert upload(client, [entry()]).status_code == 200
    with app.app_context():
        record = db.session.scalar(db.select(PersonBookRecord)); record.father_name = 'Corrected father'
        family = db.session.get(PersonFamilyConnection, record.person_id); family.father_name = 'Manual father'
        db.session.commit()
    assert upload(client, [entry()]).status_code == 200
    with app.app_context():
        record = db.session.scalar(db.select(PersonBookRecord))
        assert record.father_name == 'Corrected father'
        assert db.session.get(PersonFamilyConnection, record.person_id).father_name == 'Manual father'


def test_reference_write_cannot_target_another_profile(app):
    client = app.test_client(); assert upload(client, [entry()]).status_code == 200
    with app.app_context():
        record = db.session.scalar(db.select(PersonBookRecord)); record_id = record.id
        other = db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.person_id != record.person_id))
        other_id = other.id
    assert client.post(f'/supporter-directory/{other_id}/book/{record_id}', data={'csrf':csrf(client)}).status_code == 404


def test_manual_cleared_link_stays_clear_after_source_upload(app):
    client = app.test_client()
    assert upload(client, [entry(**{'Father book ID': '00999'}),
        {'Book ID':'00999', 'Name':'Father', 'Phone':'8455551800'}]).status_code == 200
    with app.app_context():
        r = db.session.scalar(db.select(PersonBookRecord).where(PersonBookRecord.book_id == '00157'))
        person_id = r.person_id
        profile_id = db.session.scalar(db.select(SupporterProfile.id).where(SupporterProfile.person_id == person_id))
    assert client.post(f'/supporter-directory/{profile_id}/family-connections', data={
        'csrf':csrf(client), 'father_person_id':''}).status_code == 302
    assert upload(client, [entry(**{'Father book ID':'00999'})]).status_code == 200
    with app.app_context():
        assert db.session.get(PersonFamilyConnection, person_id).father_person_id is None


def test_unassigned_case_rejects_reference_import(app):
    client = app.test_client()
    assert upload(client, [entry()], family_id='999999').status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(PersonBookRecord)) is None


def test_unauthenticated_family_edit_does_not_write(app):
    client = app.test_client(); assert upload(client, [entry()]).status_code == 200
    with app.app_context():
        r = db.session.scalar(db.select(PersonBookRecord))
        profile_id = db.session.scalar(db.select(SupporterProfile.id).where(SupporterProfile.person_id == r.person_id))
        person_id = r.person_id
    csrf_token = csrf(client)
    app.config['DEMO'] = False
    response = client.post(f'/supporter-directory/{profile_id}/family-connections', data={
        'csrf':csrf_token,'father_name':'Unauthorized'})
    assert response.status_code in (302,403)
    with app.app_context():
        assert db.session.get(PersonFamilyConnection, person_id).father_name == 'שלמה'


def test_phone_match_accepts_different_name_and_preserves_existing_name(app):
    client = app.test_client()
    assert upload(client, [{'Name': 'Existing Name', 'Phone': '7185550199'}]).status_code == 200
    assert upload(client, [entry()]).status_code == 200
    with client.session_transaction() as session:
        result = session['people_import_result']
        assert result['duplicates'] == 1
        assert result['skipped'] == result['created'] == 0
    with app.app_context():
        record = db.session.scalar(db.select(PersonBookRecord))
        person = db.session.get(SupporterPerson, record.person_id)
        assert person.name == 'Existing Name'
        assert person.home_address == '12 Main St.'


def test_two_book_sources_share_new_person_and_preserve_first_address(app):
    from person_addresses import PersonAddressDetails, address_details
    client = app.test_client()
    rows = [
        entry('source-a', **{'Book source': 'Book A', 'Apartment': '1'}),
        entry('source-b', **{'Book source': 'Book B', 'Apartment': '2',
                             'Home address': 'Different St.'}),
    ]
    for _ in range(2):
        response = upload(client, rows)
        assert response.status_code == 200
        with app.app_context():
            records = db.session.scalars(db.select(PersonBookRecord).where(
                PersonBookRecord.source.in_(['Book A', 'Book B']))).all()
            assert len(records) == 2
            person_ids = {record.person_id for record in records}
            assert len(person_ids) == 1
            person_id = person_ids.pop()
            assert db.session.scalar(db.select(db.func.count(PersonAddressDetails.id)).where(
                PersonAddressDetails.person_kind == 'person',
                PersonAddressDetails.person_id == person_id)) == 1
            assert address_details('person', person_id).home['unit'] == '1'
            assert db.session.get(SupporterPerson, person_id).home_address == '12 Main St.'


def test_book_import_batches_contact_snapshot_reads(app):
    from sqlalchemy import event
    client = app.test_client()
    csrf(client)
    queries = []
    def record_query(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)
    with app.app_context():
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', record_query)
    try:
        assert upload(client, [entry(str(i), **{'Phone 1': f'845555{i:04d}'})
                               for i in range(10)]).status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', record_query)
    snapshot_reads = [q for q in queries if 'FROM contact' in q
                      and 'contact.person_id' in q.split('WHERE')[-1]]
    assert len(snapshot_reads) == 1, snapshot_reads
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(PersonBookRecord.id))) == 10
        for record in db.session.scalars(db.select(PersonBookRecord)):
            person = db.session.get(SupporterPerson, record.person_id)
            assert person.home_address == '12 Main St.'
