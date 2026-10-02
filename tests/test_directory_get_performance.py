"""Directory rendering stays bounded as the directory grows."""
import pytest
from sqlalchemy import event

from app_entry import create_app
from app import db, Contact, Family, SupporterPerson, SupporterProfile
from book_directory import PersonBookRecord
from person_addresses import PersonAddressDetails


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL',
                'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'directory-get-test'})


def seed(app, first, last, unlinked=False):
    with app.app_context():
        for i in range(first, last):
            person = SupporterPerson(identity_key=f'directory-perf:{i}',
                                     name=f'DirectoryPerf {i:04d}', phone='')
            db.session.add(person)
            db.session.flush()
            profile = SupporterProfile(
                person_id=None if unlinked and i == last - 1 else person.id,
                name=person.name, normalized_phone=f'directory-perf:{i}',
                phone='', email='')
            db.session.add(profile)
            db.session.add(PersonBookRecord(
                person_id=person.id, source='Performance book', book_id=f'{i:05d}',
                notes='Long optional reference detail ' * 100))
            db.session.add(PersonAddressDetails(
                person_kind='person', person_id=person.id,
                home={'unit': f'Apt {i}'}, work={}, mailing_preference=''))
            db.session.add(Contact(
                family_id=1, person_id=person.id, name=person.name,
                phone='', supporter_key='phone:' + profile.normalized_phone,
                relationship='Other'))
        db.session.commit()


def get_with_queries(app, client, **args):
    queries = []
    with app.app_context():
        engine = db.engine

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append((statement, parameters))

    event.listen(engine, 'before_cursor_execute', record)
    try:
        response = client.get('/supporter-directory',
                              query_string={'q': 'DirectoryPerf', **args})
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert response.status_code == 200
    return response.text, queries


def test_directory_get_query_count_and_related_reads_are_page_bounded(app):
    client = app.test_client()
    client.get('/')
    seed(app, 0, 1)
    single, small_queries = get_with_queries(app, client)
    assert single.count('class="supporter-accordion-item"') == 1
    seed(app, 1, 105, unlinked=True)
    page, large_queries = get_with_queries(app, client)
    assert page.count('class="supporter-accordion-item"') == 50
    assert 'DirectoryPerf 0049' in page and 'DirectoryPerf 0050' not in page
    assert len(large_queries) <= len(small_queries) + 1, (
        len(small_queries), len(large_queries))
    book_reads = [(sql, params) for sql, params in large_queries
                  if 'FROM person_book_record' in sql
                  and 'person_book_record.person_id IN' in sql]
    assert len(book_reads) == 1
    sql, params = book_reads[0]
    assert len(params) == 50
    assert 'person_book_record.notes' not in sql
    address_reads = [(sql, params) for sql, params in large_queries
                     if 'FROM person_address_details' in sql]
    assert len(address_reads) == 1
    assert len(address_reads[0][1]) == 100  # 50 composite (kind, person_id) keys.
    assert 'Apt 49' in page
    # Search uses two set-based names subqueries, not one lookup per person.
    assert sum('FROM person_names' in sql for sql, _ in large_queries) <= 2
    family_reads = [sql for sql, _ in large_queries if 'FROM family ' in sql]
    assert family_reads and all('family.circumstances' not in sql
                                for sql in family_reads)

    second, _ = get_with_queries(app, client, page=2)
    assert second.count('class="supporter-accordion-item"') == 50
    assert 'DirectoryPerf 0050' in second and 'DirectoryPerf 0000' not in second
    last, _ = get_with_queries(app, client, page=3)
    assert last.count('class="supporter-accordion-item"') == 5
    assert 'DirectoryPerf 0104' in last  # Unlinked legacy profiles still render.
    searched = client.get('/supporter-directory?q=DirectoryPerf+0104')
    assert searched.status_code == 200
    assert searched.text.count('class="supporter-accordion-item"') == 1


def test_directory_get_preserves_import_summary(app):
    client = app.test_client()
    with client.session_transaction() as state:
        state['people_import_result'] = dict(
            created=42, updated=3, duplicates=5, skipped=1, linked=0,
            family_id=None, relationship='Other', errors=['Import test warning'])
    page, _ = get_with_queries(app, client)
    assert 'people-import-result' in page and 'Import test warning' in page
    assert '<strong>42</strong>' in page and '<strong>5</strong>' in page


def test_directory_moves_connection_controls_to_person_workspace(app):
    seed(app, 0, 2)
    with app.app_context():
        db.session.get(Family, 1).name = 'Case <script>unsafe</script> & name'
        db.session.commit()
    page, _ = get_with_queries(app, app.test_client())
    assert 'Case <script>unsafe</script>' not in page
    assert page.count('Case &lt;script&gt;unsafe&lt;/script&gt; &amp; name') == 1
    assert page.count('action="/supporter-directory/') == 0
    assert page.count('href="/supporter-directory/') >= 2