import time

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from app_entry import create_app
from app_original import Contact, Family, db


@pytest.fixture(scope='module')
def page_app():
    with pytest.MonkeyPatch.context() as monkeypatch:
        for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH',
                    'SESSION_SECRET'):
            monkeypatch.delenv(key, raising=False)
        app = create_app({
            'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'SECRET_KEY': 'page-query-test', 'DEMO': False,
            'ADMIN_EMAIL': 'owner@example.test',
            'ADMIN_PASSWORD_HASH': generate_password_hash('owner-pass-123'),
        })
    return app


@pytest.fixture(scope='module')
def authenticated_client(page_app):
    client = page_app.test_client()
    client.get('/login')
    with client.session_transaction() as session:
        csrf = session['csrf']
    client.post('/login', data={
        'csrf': csrf, 'email': 'owner@example.test', 'password': 'owner-pass-123'})
    return client


def profile_get(app, client, path):
    timings = []

    def before_execute(conn, cursor, statement, parameters, context, executemany):
        context._staff_page_query_started = time.perf_counter()

    def after_execute(conn, cursor, statement, parameters, context, executemany):
        started = getattr(context, '_staff_page_query_started', None)
        if started is not None:
            timings.append((time.perf_counter() - started) * 1000)

    with app.app_context():
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', before_execute)
        event.listen(engine, 'after_cursor_execute', after_execute)
    try:
        response = client.get(path)
    finally:
        with app.app_context():
            event.remove(engine, 'before_cursor_execute', before_execute)
            event.remove(engine, 'after_cursor_execute', after_execute)
    assert response.status_code == 200
    return len(timings), sum(timings)


def add_family(name):
    family = Family(name=name)
    db.session.add(family)
    db.session.flush()
    return family


def add_contact(family_id, name, supporter_key=None, parent_contact_id=None):
    contact = Contact(
        family_id=family_id, name=name, relationship='Friend',
        supporter_key=supporter_key or f'person:{name}',
        parent_contact_id=parent_contact_id,
        parent_connection='Son' if parent_contact_id else '')
    db.session.add(contact)
    db.session.flush()
    return contact


def test_cases_directory_query_count_does_not_grow_with_families(
        page_app, authenticated_client):
    with page_app.app_context():
        add_family('Case 1')
        db.session.commit()

    baseline, _ = profile_get(page_app, authenticated_client, '/cases')

    with page_app.app_context():
        for number in range(2, 22):
            add_family(f'Case {number}')
        db.session.commit()

    grown, _ = profile_get(page_app, authenticated_client, '/cases')
    assert grown <= baseline + 1


def test_family_detail_query_count_does_not_grow_with_supporters(
        page_app, authenticated_client):
    with page_app.app_context():
        family = add_family('Household')
        root = add_contact(family.id, 'Primary supporter')
        family_id, root_id = family.id, root.id
        for number in range(4):
            add_contact(family_id, f'Existing supporter {number}',
                        parent_contact_id=root_id)
        db.session.commit()

    baseline, _ = profile_get(
        page_app, authenticated_client, f'/families/{family_id}')

    with page_app.app_context():
        for number in range(4, 20):
            add_contact(family_id, f'Supporter {number}', parent_contact_id=root_id)
        db.session.commit()

    grown, _ = profile_get(
        page_app, authenticated_client, f'/families/{family_id}')
    # A populated relationship loader can add a small fixed number of batch
    # statements; the count must not scale with the added rows.
    assert grown <= baseline + 3


def test_supporters_directory_query_count_does_not_grow_with_contacts(
        page_app, authenticated_client):
    with page_app.app_context():
        family = add_family('Household')
        add_contact(family.id, 'Supporter 1')
        family_id = family.id
        db.session.commit()

    baseline, _ = profile_get(page_app, authenticated_client, '/supporters')

    with page_app.app_context():
        for number in range(2, 22):
            add_contact(family_id, f'Supporter {number}')
        db.session.commit()

    grown, _ = profile_get(page_app, authenticated_client, '/supporters')
    assert grown <= baseline + 1


def test_supporter_history_query_count_does_not_grow_with_linked_contacts(
        page_app, authenticated_client):
    with page_app.app_context():
        family = add_family('Household')
        primary = add_contact(family.id, 'Shared supporter', supporter_key='shared:person')
        family_id, primary_id = family.id, primary.id
        for number in range(4):
            add_contact(family_id, f'Existing connected person {number}',
                        supporter_key='shared:person', parent_contact_id=primary_id)
        db.session.commit()

    baseline, _ = profile_get(
        page_app, authenticated_client, f'/supporters/{primary_id}')

    with page_app.app_context():
        for number in range(4, 20):
            add_contact(
                family_id, f'Connected person {number}',
                supporter_key='shared:person', parent_contact_id=primary_id)
        db.session.commit()

    grown, _ = profile_get(
        page_app, authenticated_client, f'/supporters/{primary_id}')
    assert grown <= baseline + 2