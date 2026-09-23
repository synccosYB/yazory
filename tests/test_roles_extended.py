from app_entry import create_app
from io import BytesIO

from app import db, Family, Expense, Contact, Audit, Document, StaffUser, FamilyAssignment, Askan
from werkzeug.security import generate_password_hash


def test_revoked_assignment_and_deactivated_staff_lose_existing_session(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'revocation-test'})
    with app.app_context():
        family = Family(name='Private assignment', status='Active')
        owner = StaffUser(email='owner@example.test', password_hash='unused',
                          role='organization_admin', status='active')
        worker = StaffUser(email='worker@example.test', password_hash='unused',
                           role='office_employee', status='active')
        db.session.add_all((family, owner, worker))
        db.session.flush()
        db.session.add(FamilyAssignment(staff_user_id=worker.id, family_id=family.id))
        db.session.commit()
        family_id, worker_id, owner_id = family.id, worker.id, owner.id
    admin, staff = app.test_client(), app.test_client()
    with admin.session_transaction() as state:
        state.update(user_id=owner_id, csrf='admin-csrf')
    with staff.session_transaction() as state:
        state.update(user_id=worker_id, csrf='worker-csrf')
    assert staff.get(f'/families/{family_id}').status_code == 200
    assert admin.post(f'/staff/{worker_id}/assignments', data={
        'csrf': 'admin-csrf', 'family_id': family_id, 'operation': 'revoke'}).status_code == 302
    for path in (f'/families/{family_id}', f'/families/{family_id}/edit',
                 f'/families/{family_id}/messages', f'/families/{family_id}/ledger',
                 f'/families/{family_id}/coordination',
                 f'/families/{family_id}/network'):
        assert staff.get(path).status_code == 403, path
    assert staff.post(f'/families/{family_id}/expenses', data={
        'csrf': 'worker-csrf', 'category': 'Groceries', 'payee': 'Denied',
        'amount': '10', 'month': '2026-09'}).status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(Expense).where(Expense.payee == 'Denied')) is None
        db.session.get(StaffUser, worker_id).status = 'inactive'
        db.session.commit()
    assert staff.get('/families').location.endswith('/login')


def test_askan_only_opens_own_read_only_case(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'DEMO': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'askan-test'})
    with app.app_context():
        own = Family(name='Assigned askan family', circumstances='Private notes')
        other = Family(name='Another family', circumstances='Other private notes')
        askan = Askan(name='Assigned askan', email='askan@example.test')
        user = StaffUser(email='askan@example.test', password_hash='unused',
                         role='askan', status='active')
        own.designated_askan = askan
        db.session.add_all((own, other, user))
        db.session.flush()
        db.session.add(FamilyAssignment(staff_user_id=user.id, family_id=own.id))
        db.session.commit()
        own_id, other_id, user_id = own.id, other.id, user.id
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(user_id=user_id, csrf='askan-csrf')
    own_page = client.get(f'/askan/cases/{own_id}')
    assert own_page.status_code == 200
    assert 'Other private notes' not in own_page.text
    assert client.get(f'/askan/cases/{other_id}').status_code == 403
    for path in (f'/families/{own_id}', f'/families/{own_id}/edit',
                 '/supporters', '/payouts', '/workflow-access'):
        assert client.get(path).status_code == 403, path

def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf':csrf})

def test_office_and_fundraiser_permissions_and_isolation(monkeypatch):
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING':True, 'SQLALCHEMY_DATABASE_URI':'sqlite://',
                      'SECRET_KEY':'test-only', 'DEMO':False,
                      'ADMIN_EMAIL':'owner@example.test',
                      'ADMIN_PASSWORD_HASH':generate_password_hash('owner-passphrase-123')})
    with app.app_context():
        db.create_all()
        assigned = Family(name='Assigned household', address='CONFIDENTIAL ADDRESS',
                          circumstances='CONFIDENTIAL MEDICAL NOTES', status='Active')
        private = Family(name='Private household', circumstances='PRIVATE NOTES', status='Active')
        db.session.add_all([assigned, private])
        db.session.flush()
        assigned_contact = Contact(family_id=assigned.id, name='Assigned donor',
                                   relationship='Friend', monthly_cents=2500, status='Pledged')
        private_contact = Contact(family_id=private.id, name='Private donor',
                                  relationship='Friend', monthly_cents=5000, status='Pledged')
        private_expense = Expense(family_id=private.id, category='Groceries',
                                  payee='PRIVATE PAYEE', amount_cents=1000, month='2026-09')
        db.session.add_all([assigned_contact, private_contact, private_expense])
        db.session.commit()
        assigned_id, private_id = assigned.id, private.id
        assigned_contact_id, private_contact_id = assigned_contact.id, private_contact.id
        private_expense_id = private_expense.id
    monkeypatch.setattr('time.sleep', lambda _:None)

    def login(email, password):
        client = app.test_client()
        client.get('/login')
        with client.session_transaction() as session:
            csrf = session['csrf']
        assert client.post('/login', data={'csrf':csrf, 'email':email, 'password':password}).status_code == 302
        return client

    owner = login('owner@example.test', 'owner-passphrase-123')
    for email, role in [('office@example.test','office_employee'), ('fundraiser@example.test','fundraiser')]:
        assert post(owner, '/staff', {'email':email, 'password':'staff-passphrase-123', 'role':role}).status_code == 302
    with app.app_context():
        office = db.session.scalar(db.select(StaffUser).where(StaffUser.role == 'office_employee'))
        fundraiser = db.session.scalar(db.select(StaffUser).where(StaffUser.role == 'fundraiser'))
        office_id, fundraiser_id = office.id, fundraiser.id
    for user_id in (office_id, fundraiser_id):
        assert post(owner, f'/staff/{user_id}/assignments', {'family_id':assigned_id}).status_code == 302
    with app.app_context():
        contact_count = db.session.scalar(db.select(db.func.count()).select_from(Contact))
        audit_count = db.session.scalar(db.select(db.func.count()).select_from(Audit))
    assert post(owner, '/families/999999/contacts',
                {'name':'Orphan','relationship':'Friend','status':'Contacted','monthly':'0'}).status_code == 404
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Contact)) == contact_count
        assert db.session.scalar(db.select(db.func.count()).select_from(Audit)) == audit_count

    office_client = login('office@example.test', 'staff-passphrase-123')
    assert office_client.get(f'/families/{assigned_id}').status_code == 200
    assert office_client.get(f'/families/{private_id}').status_code == 403
    assert office_client.get('/fundraising').status_code == 403
    assert office_client.get('/staff').status_code == 403
    assert post(office_client, f'/families/{assigned_id}/contacts',
                {'name':'Denied','relationship':'Friend','status':'Pledged','monthly':'5'}).status_code == 403
    assert post(office_client, f'/contacts/{assigned_contact_id}',
                {'status':'Contacted','monthly':'0'}).status_code == 403
    assert post(office_client, f'/families/{assigned_id}/expenses',
                {'category':'Groceries','payee':'Allowed','amount':'12','month':'2026-09'}).status_code == 302
    assert post(office_client, f'/families/{private_id}/expenses',
                {'category':'Groceries','payee':'Denied','amount':'12','month':'2026-09'}).status_code == 403
    assert post(office_client, f'/expenses/{private_expense_id}/status',
                {'status':'Approved'}).status_code == 403
    assert post(office_client, '/families/new', {'name':'Office intake'}).status_code == 302
    assert post(office_client, f'/families/{assigned_id}/documents',
                {'document':(BytesIO(b'%PDF-1.4 test'), 'case-note.pdf')}).status_code == 302
    assert post(office_client, f'/families/{assigned_id}/documents',
                {'document':(BytesIO(b'not a PDF'), 'spoofed.pdf', 'application/pdf')}).status_code == 400
    assert post(office_client, f'/families/{assigned_id}/documents',
                {'document':(BytesIO(b'%PDF-1.4 mismatch'), 'mismatch.png')}).status_code == 400
    assert post(office_client, f'/families/{assigned_id}/documents',
                {'document':(BytesIO(b'%PDF-' + b'x' * (8 * 1024 * 1024)), 'oversized.pdf')}).status_code == 400
    with app.app_context():
        intake = db.session.scalar(db.select(Family).where(Family.name == 'Office intake'))
        assert db.session.scalar(db.select(FamilyAssignment.id).where(
            FamilyAssignment.staff_user_id == office_id,
            FamilyAssignment.family_id == intake.id))
        document_id = db.session.scalar(db.select(Document.id).where(
            Document.family_id == assigned_id))
    download = office_client.get(f'/documents/{document_id}')
    assert download.status_code == 200
    assert download.headers['Content-Disposition'].startswith('attachment;')

    # A family assignment no longer exposes every donor: individual contact assignment is required.
    with app.app_context():
        Link=app.extensions['workflows']['models']['SupporterLink']
        db.session.add(Link(contact_id=assigned_contact_id,side='Husband',relationship='Friend',assigned_to=fundraiser_id,permission='Permitted',verified=True))
        db.session.commit()
    fundraiser_client = login('fundraiser@example.test', 'staff-passphrase-123')
    assert fundraiser_client.get('/').location == '/fundraising'
    summary = fundraiser_client.get('/fundraising').text
    assert 'Assigned household' in summary and 'Private household' not in summary
    assert 'CONFIDENTIAL' not in summary and 'PRIVATE PAYEE' not in summary
    detail = fundraiser_client.get(f'/fundraising/{assigned_id}')
    assert detail.status_code == 200 and f'/supporters?family_id={assigned_id}' in detail.text
    for confidential in ('CONFIDENTIAL ADDRESS', 'CONFIDENTIAL MEDICAL NOTES', 'PRIVATE PAYEE'):
        assert confidential not in detail.text
    assert fundraiser_client.get(f'/fundraising/{private_id}').status_code == 403
    assert fundraiser_client.get(f'/families/{assigned_id}').status_code == 403
    assert fundraiser_client.get('/expenses').status_code == 403
    assert fundraiser_client.get('/staff').status_code == 403
    assert fundraiser_client.get(f'/documents/{document_id}').status_code == 403
    assert post(fundraiser_client, f'/families/{assigned_id}/documents',
                {'document':(BytesIO(b'%PDF-1.4 denied'), 'denied.pdf')}).status_code == 403
    assert post(fundraiser_client, f'/families/{assigned_id}/contacts',
                {'name':'New donor','relationship':'Friend','status':'Contacted','monthly':'0'}).status_code == 302
    assert post(fundraiser_client, f'/contacts/{assigned_contact_id}',
                {'status':'Pledged','monthly':'30'}).status_code == 302
    assert post(fundraiser_client, f'/contacts/{private_contact_id}',
                {'status':'Contacted','monthly':'0'}).status_code == 403
    assert post(fundraiser_client, f'/families/{assigned_id}/children',
                {'name':'Denied child','age':'8','school':'School'}).status_code == 403
    assert post(fundraiser_client, f'/families/{assigned_id}/expenses',
                {'category':'Groceries','payee':'Denied','amount':'12','month':'2026-09'}).status_code == 403

    for language, direction, label in [('en','ltr','Fundraising workspace'),
                                       ('he','rtl','מרחב גיוס תרומות'),
                                       ('yi','rtl','געלט־זאמלער ארבעטס פלאץ')]:
        fundraiser_client.get(f'/language/{language}')
        page = fundraiser_client.get('/fundraising')
        assert page.status_code == 200
        assert f'lang="{language}" dir="{direction}"' in page.text
        assert label in page.text
