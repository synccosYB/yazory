from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash

from app_entry import create_app
from app import StaffTask
from app_original import Askan, Audit, Contact, Family, StaffUser, db
from notifications import StaffActivityCursor


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH',
                'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({
        'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test', 'DEMO': False,
        'ADMIN_EMAIL': 'owner@example.test',
        'ADMIN_PASSWORD_HASH': generate_password_hash('owner-pass-123'),
    })


@pytest.fixture
def client(app):
    browser = app.test_client()
    browser.get('/login')
    with browser.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    browser.post('/login', data={
        'csrf': csrf, 'email': 'owner@example.test', 'password': 'owner-pass-123'})
    return browser


def test_header_and_feed_show_new_activity(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        db.session.add(Audit(actor='Stripe', action='Received Stripe donation: $18.00'))
        db.session.commit()

    response = client.get('/notifications')
    assert response.status_code == 200
    assert b'Received Stripe donation' in response.data
    assert b'notification-bell has-new' in response.data


def test_mark_all_read_clears_count(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        db.session.add(Audit(actor='Applicant', action='Applicant sent portal message'))
        db.session.commit()
    client.get('/notifications')
    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    response = client.post('/notifications/mark-read', data={'csrf': csrf}, follow_redirects=True)
    assert response.status_code == 200
    assert b'There is no new activity' in response.data
    assert b'notification-bell has-new' not in response.data


def test_opening_one_notification_marks_only_that_item_read(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(minutes=5)
        first = Audit(actor='Email sender', action='New message in Yazory inbox')
        second = Audit(actor='Staff', action='Replied to Yazory inbox message')
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id

    page = client.get('/notifications')
    assert page.data.count(b'class="notification-item"') == 2
    assert b'>2</b>' in page.data

    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    assert client.get(f'/notifications/{first_id}/open').status_code in (404, 405)
    opened = client.post(
        f'/notifications/{first_id}/open', data={'csrf': csrf}, follow_redirects=False)
    assert opened.status_code == 302
    assert opened.location.endswith('/communications#general-inbox')

    page = client.get('/notifications')
    assert page.data.count(b'class="notification-item"') == 1
    assert b'>1</b>' in page.data
    assert b'New message in Yazory inbox' not in page.data
    assert b'Replied to Yazory inbox message' in page.data


    # A saved link or a second click still opens the activity after it is read.
    opened_again = client.post(f'/notifications/{first_id}/open', data={'csrf': csrf})
    assert opened_again.status_code == 302
    assert opened_again.location.endswith('/communications#general-inbox')

    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        db.session.get(StaffActivityCursor, user.id).last_seen_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=1))
        db.session.commit()
    opened_after_clear = client.post(
        f'/notifications/{first_id}/open', data={'csrf': csrf})
    assert opened_after_clear.status_code == 302
    assert opened_after_clear.location.endswith('/communications#general-inbox')


def test_notifications_page_always_links_back_to_communications(app, client):
    response = client.get('/notifications')
    assert response.status_code == 200
    assert b'href="/communications#general-inbox"' in response.data
    assert b'Open Communications' in response.data


def test_authenticated_get_does_not_create_missing_activity_cursor(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        db.session.delete(db.session.get(StaffActivityCursor, user.id))
        db.session.commit()

    response = client.get('/notifications')

    assert response.status_code == 200
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        assert db.session.get(StaffActivityCursor, user.id) is None

    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    response = client.post('/notifications/mark-read', data={'csrf': csrf})
    assert response.status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        assert db.session.get(StaffActivityCursor, user.id) is not None


def test_audit_hot_query_indexes_are_declared(app):
    with app.app_context():
        indexes = {index['name'] for index in inspect(db.engine).get_indexes('audit')}

    assert {'ix_audit_at_id', 'ix_audit_family_at_id'} <= indexes


def test_opening_sponsorship_notification_opens_exact_page_and_month(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(minutes=5)
        activity = Audit(
            actor='owner@example.test',
            action='Updated 2026-09 sponsorship for Overview')
        db.session.add(activity)
        db.session.commit()
        activity_id = activity.id

    client.get('/notifications')
    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    opened = client.post(
        f'/notifications/{activity_id}/open', data={'csrf': csrf}, follow_redirects=False)

    assert opened.status_code == 302
    assert opened.location.endswith('/sponsorships/overview?month=2026-09')


def test_automatic_supporter_follow_up_opens_exact_task(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(minutes=5)
        family = Family(name='Notification family')
        db.session.add(family)
        db.session.flush()
        contact = Contact(
            family_id=family.id, name='Notification supporter',
            relationship='Friend', status='To contact')
        db.session.add(contact)
        db.session.flush()
        task = StaffTask(
            family_id=family.id, source_contact_id=contact.id,
            assigned_to=user.id, created_by=user.id,
            title='Contact supporter', status='To do')
        db.session.add(task)
        db.session.flush()
        activity = Audit(
            actor=user.email,
            action='Created automatic supporter follow-up: Notification supporter')
        db.session.add(activity)
        db.session.commit()
        task_id = task.id
        activity_id = activity.id

    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    opened = client.post(
        f'/notifications/{activity_id}/open',
        data={'csrf': csrf}, follow_redirects=False)

    assert opened.status_code == 302
    assert opened.location.endswith(f'/tasks/{task_id}')


def test_askan_profile_update_opens_exact_askan(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(minutes=5)
        askan = Askan(name='Notification askan')
        db.session.add(askan)
        db.session.flush()
        activity = Audit(
            actor=user.email,
            action='Updated askan network profile: Notification askan')
        db.session.add(activity)
        db.session.commit()
        askan_id = askan.id
        activity_id = activity.id

    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    opened = client.post(
        f'/notifications/{activity_id}/open',
        data={'csrf': csrf}, follow_redirects=False)

    assert opened.status_code == 302
    assert opened.location.endswith(f'/network/askanim/{askan_id}')


def test_unknown_activity_never_falls_back_to_dashboard(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser))
        cursor = db.session.get(StaffActivityCursor, user.id)
        cursor.last_seen_at = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(minutes=5)
        activity = Audit(actor=user.email, action='Unmapped legacy activity')
        db.session.add(activity)
        db.session.commit()
        activity_id = activity.id

    with client.session_transaction() as browser_session:
        csrf = browser_session['csrf']
    opened = client.post(
        f'/notifications/{activity_id}/open',
        data={'csrf': csrf}, follow_redirects=False)

    assert opened.status_code == 302
    assert opened.location.endswith('/notifications')
    assert not opened.location.endswith('/')
