from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app_entry import create_app
from app_original import Audit, StaffUser, db
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
