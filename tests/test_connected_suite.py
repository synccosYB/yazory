"""Focused regression coverage for the connected workspace additions."""
from app import create_app, db, Family, Contact, Receipt, OrganizationSetting, StaffUser


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def test_connected_routes_languages_receipts_and_controls(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})
    client = app.test_client()
    # Demo bootstrap is deliberately fictional and supplies a scoped contact.
    for language in ('en', 'he', 'yi'):
        client.get('/language/' + language)
        for path in ('/', '/cases', '/supporters', '/fundraising', '/collections',
                     '/expenses', '/payouts', '/approvals', '/reports', '/people-access', '/controls'):
            assert client.get(path).status_code == 200, (language, path)
    with app.app_context():
        contact = db.session.scalar(db.select(Contact))
        family = db.session.get(Family, contact.family_id)
        contact_id, family_id = contact.id, family.id
    for language, label in (('en', 'Amount ($)'), ('he', 'סכום ($)'), ('yi', 'סכום ($)')):
        client.get('/language/' + language)
        report = client.get(f'/families/{family_id}/expense-report')
        assert report.status_code == 200
        assert f'aria-label="{label}"' in report.text
    response = client.post('/collections/receipts', data={
        'csrf': csrf(client), 'contact_id': contact_id, 'amount': '12.34',
        'received_on': '2025-01-15', 'reference': 'MANUAL-1', 'note': 'reported'
    })
    assert response.status_code == 302
    with app.app_context():
        receipt = db.session.scalar(db.select(Receipt))
        assert receipt.amount_cents == 1234 and receipt.family_id == family_id
        # Receipt entry never changes the underlying pledge commitment.
        assert db.session.get(Contact, contact_id).monthly_cents == 18000
    january = client.get('/collections?month=2025-01').text
    february = client.get('/collections?month=2025-02').text
    assert '$12.34' in january
    assert f'href="/supporters/{contact_id}"' in january
    assert january.count(f'href="/supporters/{contact_id}"') >= 2
    assert '$12.34' in february  # lifetime column
    assert client.post('/controls', data={'csrf': csrf(client), 'categories': 'Bogus',
                                           'child_bands': '[]'}).status_code == 400
    assert client.post('/controls', data={'csrf': csrf(client), 'categories': 'Groceries\nOther',
                                           'child_bands': '[{"min_age":0,"max_age":30,"amount_cents":100}]'}).status_code == 302
    with app.app_context():
        assert db.session.get(OrganizationSetting, 'expense_categories').value == ['Groceries', 'Other']


def test_people_access_accepts_staff_account_form_submission(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})
    client = app.test_client()

    response = client.post('/people-access', data={
        'csrf': csrf(client),
        'email': 'new-staff@example.test',
        'password': 'new-staff-password',
        'role': 'office_employee',
    })

    assert response.status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'new-staff@example.test'))
        assert user is not None
        assert user.role == 'office_employee'


def test_manual_receipt_can_create_a_new_donor(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'SECRET_KEY': 'test'})
    client = app.test_client()
    with app.app_context():
        family_id = db.session.scalar(db.select(Family.id))
    response = client.post('/collections/receipts', data={
        'csrf': csrf(client), 'contact_id': '__new__',
        'family_id': family_id, 'donor_name': 'Outside Donor',
        'donor_phone': '845-555-0101', 'amount': '250.00',
        'received_on': '2026-09-10', 'reference': 'CASH-1',
    })
    assert response.status_code == 302
    with app.app_context():
        donor = db.session.scalar(db.select(Contact).where(
            Contact.name == 'Outside Donor'))
        assert donor is not None
        assert donor.family_id == family_id
        assert donor.relationship == 'Other'
        assert donor.status == 'Contacted'
        receipt = db.session.scalar(db.select(Receipt).where(
            Receipt.contact_id == donor.id))
        assert receipt.amount_cents == 25000
        assert receipt.family_id == family_id
