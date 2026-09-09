from io import BytesIO

from app import create_app, db, Family, Expense, Contact, Audit, Document, StaffUser, FamilyAssignment
from werkzeug.security import generate_password_hash

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
    assert detail.status_code == 200 and 'Assigned donor' in detail.text
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
