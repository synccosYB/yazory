from io import BytesIO
import sqlite3
from datetime import date

import pytest
from app import create_app, db, Family, Child, Expense, Contact, ContactChild, Receipt, Audit, Document, StaffUser, FamilyAssignment
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash

@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI':'sqlite://', 'SECRET_KEY':'test-only'})

@pytest.fixture
def client(app):
    return app.test_client()

def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf':csrf})

def test_pages(client):
    for path in ['/', '/families', '/families/new', '/families/1', '/families/1/edit', '/expenses', '/expenses?status=Requested', '/activity', '/health', '/login']:
        assert client.get(path).status_code == 200, path
    assert client.get('/families/999').status_code == 404

def test_case_and_expense_workflow(app, client):
    assert post(client, '/families/new', {'name':'Test family','father':'Father','inlaws':'In-laws'}).status_code == 302
    with app.app_context():
        family_id=db.session.execute(db.select(Family.id).where(Family.name=='Test family')).scalar_one()
    base=f'/families/{family_id}'
    assert post(client, base+'/status', {'status':'Active'}).status_code == 400
    assert post(client, base+'/children', {'name':'Child','age':'8','grade':'3','school':'School','tuition_contact':'Office'}).status_code == 302
    assert post(client, base+'/contacts', {'name':'Sibling','relationship':'Sibling','status':'Pledged','monthly':'18.25'}).status_code == 302
    assert post(client, base+'/expenses', {'category':'Tuition','payee':'School','amount':'125.50','month':'2026-09'}).status_code == 302
    with app.app_context():
        expense_id=db.session.execute(db.select(Expense.id).where(Expense.family_id==family_id)).scalar_one()
    path=f'/expenses/{expense_id}/status'
    assert post(client, path, {'status':'Approved'}).status_code == 400
    for state in ['Under review','Active']:
        assert post(client, base+'/status', {'status':state}).status_code == 302
    assert post(client,path,{'status':'Paid','payment_reference':'x'}).status_code == 400
    assert post(client,path,{'status':'Approved'}).status_code == 302
    assert post(client,path,{'status':'Paid'}).status_code == 400
    assert post(client,path,{'status':'Paid','payment_reference':'CHECK-123'}).status_code == 302
    assert post(client,path,{'status':'Paid','payment_reference':'CHECK-123'}).status_code == 400
    with app.app_context():
        expense=db.session.get(Expense,expense_id)
        assert expense.amount_cents==12550
        assert expense.payment_reference=='CHECK-123'
        assert len(db.session.scalars(db.select(Audit).where(Audit.family_id==family_id)).all())==8
        assert db.session.execute(db.select(Contact.monthly_cents).where(Contact.family_id==family_id)).scalar_one()==1825

def test_married_child_records_spouse(app, client):
    assert post(client, '/families/new', {'name':'Parents'}).status_code == 302
    with app.app_context():
        family_id = db.session.scalar(db.select(Family.id).where(Family.name == 'Parents'))
    assert post(client, f'/families/{family_id}/children', {
        'name':'Married child', 'age':'31', 'married':'yes', 'spouse_name':'Spouse'
    }).status_code == 302
    with app.app_context():
        child = db.session.scalar(db.select(Child).where(Child.family_id == family_id))
        assert child.married is True
        assert child.spouse_name == 'Spouse'
        child_id = child.id
    page = client.get(f'/families/{family_id}').text
    assert 'Spouse' in page
    assert post(client, f'/children/{child_id}', {
        'name':'Married child', 'age':'31', 'married':'yes', 'spouse_name':'Updated spouse'
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Child, child_id).spouse_name == 'Updated spouse'

def test_supporter_connected_to_multiple_cases_has_one_charge(app, client):
    for name in ('Case A', 'Case B'):
        assert post(client, '/families/new', {'name':name}).status_code == 302
    with app.app_context():
        families = db.session.scalars(db.select(Family).where(Family.name.in_(('Case A', 'Case B'))).order_by(Family.name)).all()
        for family in families:
            family.status = 'Active'
        db.session.commit()
        first_id, second_id = (family.id for family in families)
    assert post(client, f'/families/{first_id}/contacts', {
        'name':'Shared supporter', 'phone':'845-555-0123',
        'relationship':'In-law’s maiden family', 'status':'Pledged', 'monthly':'36'}).status_code == 302
    assert post(client, f'/families/{second_id}/contacts', {
        'name':'Shared supporter', 'phone':'(845) 555-0123',
        'relationship':'First cousin', 'status':'To contact', 'monthly':'0'}).status_code == 302
    with app.app_context():
        contacts = db.session.scalars(db.select(Contact).where(Contact.name == 'Shared supporter').order_by(Contact.id)).all()
        assert len(contacts) == 2
        assert contacts[0].supporter_key == contacts[1].supporter_key
        assert all(contact.status == 'Pledged' and contact.monthly_cents == 3600 for contact in contacts)
        first_contact_id = contacts[0].id
        second_contact_id = contacts[1].id
    assert post(client, f'/contacts/{second_contact_id}', {
        'status':'Pledged', 'monthly':'50'}).status_code == 302
    with app.app_context():
        assert all(contact.monthly_cents == 5000 for contact in db.session.scalars(
            db.select(Contact).where(Contact.name == 'Shared supporter')).all())
    dashboard = client.get('/').text
    # The demo fixture already has a separate $180 pledge. The shared $50
    # supporter must be counted once ($230 total), never twice ($280 total).
    assert '$230.00' in dashboard
    assert '$280.00' not in dashboard
    assert '2' in client.get(f'/supporters/{first_contact_id}').text

def test_supporter_history_and_safe_duplicate_deletion(app, client):
    for name in ('History family A', 'History family B'):
        assert post(client, '/families/new', {'name': name}).status_code == 302
    with app.app_context():
        families = db.session.scalars(db.select(Family).where(
            Family.name.in_(('History family A', 'History family B'))).order_by(Family.name)).all()
        first_id, second_id = (family.id for family in families)
    for family_id in (first_id, second_id):
        assert post(client, f'/families/{family_id}/contacts', {
            'name': 'History supporter', 'phone': '845-555-0199',
            'relationship': 'Sibling', 'status': 'Pledged', 'monthly': '25',
            'pledge_frequency': 'Monthly'}).status_code == 302
    with app.app_context():
        contacts = db.session.scalars(db.select(Contact).where(
            Contact.name == 'History supporter').order_by(Contact.id)).all()
        first_contact_id, duplicate_contact_id = (contact.id for contact in contacts)
        db.session.add(Receipt(contact_id=first_contact_id, family_id=first_id,
                               amount_cents=1250, received_on=date(2026, 9, 7),
                               reference='HISTORY-1'))
        db.session.commit()

    supporter_list = client.get('/supporters').text
    assert f'/supporters/{first_contact_id}' in supporter_list
    detail = client.get(f'/supporters/{duplicate_contact_id}').text
    assert 'History family A' in detail and 'History family B' in detail
    assert 'HISTORY-1' in detail and '$12.50' in detail

    assert post(client, f'/contacts/{duplicate_contact_id}/delete', {'next': '/supporters'}).status_code == 302
    with app.app_context():
        assert db.session.get(Contact, duplicate_contact_id) is None
        assert db.session.get(Contact, first_contact_id) is not None
    assert post(client, f'/contacts/{first_contact_id}/delete', {'next': '/supporters'}).status_code == 400
    with app.app_context():
        assert db.session.get(Contact, first_contact_id) is not None

def test_supporter_can_have_multiple_children_and_spouses(app, client):
    assert post(client, '/families/1/contacts', {
        'name':'Supporter parent', 'relationship':'Sibling',
        'status':'To contact', 'monthly':'0'}).status_code == 302
    with app.app_context():
        contact_id = db.session.execute(db.select(Contact.id).where(
            Contact.name == 'Supporter parent')).scalar_one()
    for name, spouse in (('Married child one', 'Spouse one'),
                         ('Married child two', 'Spouse two')):
        assert post(client, f'/contacts/{contact_id}/children', {
            'name':name, 'spouse_name':spouse, 'phone':'845-555-0100'}).status_code == 302
    with app.app_context():
        children = db.session.scalars(db.select(ContactChild).where(
            ContactChild.contact_id == contact_id).order_by(ContactChild.id)).all()
        assert [(child.name, child.spouse_name) for child in children] == [
            ('Married child one', 'Spouse one'), ('Married child two', 'Spouse two')]
    supporter_page = client.get(f'/supporters/{contact_id}').text
    assert 'Married child one' in supporter_page
    assert 'Spouse one' in supporter_page
    assert 'Niece / nephew of applicant' in supporter_page
    assert post(client, f'/contacts/{contact_id}/children', {
        'name':'Married child one', 'spouse_name':'Duplicate'}).status_code == 400

@pytest.mark.parametrize('language,label', [
    ('en', 'Nephew'), ('he', 'אחיין'), ('yi', 'פלימעניק')])
def test_nephew_is_available_as_applicant_relationship(app, client, language, label):
    client.get(f'/language/{language}')
    page = client.get('/supporters?family_id=1').text
    assert f'<option value="Nephew">{label}</option>' in page
    assert post(client, '/families/1/contacts', {
        'name':'Sibling child', 'relationship':'Nephew',
        'status':'To contact', 'monthly':'0'}).status_code == 302
    with app.app_context():
        contact = db.session.scalar(db.select(Contact).where(Contact.name == 'Sibling child'))
        assert contact.relationship == 'Nephew'

def test_supporter_donation_frequency_is_saved_and_used_in_monthly_total(app, client):
    assert post(client, '/families/1/contacts', {
        'name':'Weekly donor', 'relationship':'Friend', 'status':'Pledged',
        'monthly':'12', 'pledge_frequency':'Weekly'}).status_code == 302
    assert post(client, '/families/1/contacts', {
        'name':'One-time donor', 'relationship':'Friend', 'status':'Pledged',
        'monthly':'500', 'pledge_frequency':'One time'}).status_code == 302
    with app.app_context():
        weekly = db.session.scalar(db.select(Contact).where(Contact.name == 'Weekly donor'))
        one_time = db.session.scalar(db.select(Contact).where(Contact.name == 'One-time donor'))
        assert weekly.pledge_frequency == 'Weekly'
        assert weekly.monthly_equivalent_cents == 5200
        assert one_time.pledge_frequency == 'One time'
        assert one_time.monthly_equivalent_cents == 0
        weekly_id, one_time_id = weekly.id, one_time.id
    weekly_edit = client.get(f'/contacts/{weekly_id}/edit').text
    one_time_edit = client.get(f'/contacts/{one_time_id}/edit').text
    assert 'value="Weekly" selected' in weekly_edit
    assert 'value="One time" selected' in one_time_edit
    assert '$232.00' in client.get('/families/1').text

def test_supporter_can_be_edited_and_nested_under_another_supporter(app, client):
    for name, relationship in (('Shlomo supporter', 'Sibling'), ('Hersh son-in-law', 'Nephew')):
        assert post(client, '/families/1/contacts', {
            'name': name, 'relationship': relationship,
            'status': 'To contact', 'monthly': '0'}).status_code == 302
    with app.app_context():
        shlomo = db.session.scalar(db.select(Contact).where(Contact.name == 'Shlomo supporter'))
        hersh = db.session.scalar(db.select(Contact).where(Contact.name == 'Hersh son-in-law'))
        shlomo_id, hersh_id = shlomo.id, hersh.id
    assert post(client, f'/contacts/{hersh_id}/edit', {
        'name': 'Hersh Levy', 'phone': '845-555-0111', 'relationship': 'Nephew',
        'parent_contact_id': str(shlomo_id), 'status': 'Contacted',
        'monthly': '10', 'pledge_frequency': 'Monthly'}).status_code == 302
    with app.app_context():
        hersh = db.session.get(Contact, hersh_id)
        assert (hersh.name, hersh.relationship, hersh.parent_contact_id) == (
            'Hersh Levy', 'Nephew', shlomo_id)
    supporter_list = client.get('/supporters?family_id=1').text
    assert 'Hersh Levy' in supporter_list and 'Shlomo supporter' in supporter_list
    assert 'Son-in-law of Shlomo supporter, Sibling of the applicant' in supporter_list
    supporter_detail = client.get(f'/supporters/{hersh_id}').text
    assert 'Son-in-law of Shlomo supporter, Sibling of the applicant' in supporter_detail
    profile = client.get('/families/1').text
    assert 'Manage supporters' in profile
    assert 'name="pledge_frequency"' not in profile

def test_profile_data_points_have_targeted_pencil_edit_links(client):
    profile = client.get('/families/1').text
    for field in ('name', 'address', 'phone', 'spouse', 'father', 'inlaws',
                  'inlaws_maiden_name', 'inlaws_family', 'rabbi', 'rabbi_phone',
                  'weekday_shul', 'shabbos_shul', 'circumstances'):
        assert f'/families/1/edit?field={field}' in profile
    edit = client.get('/families/1/edit?field=rabbi')
    assert edit.status_code == 200
    assert 'name="rabbi"' in edit.text

def test_rabbi_phone_is_saved_and_shown_with_the_rabbi(app, client):
    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'rabbi': 'Rabbi Rubin',
        'rabbi_phone': '845-555-0101',
    })
    assert response.status_code == 302
    with app.app_context():
        family = db.session.get(Family, 1)
        assert family.rabbi_phone == '845-555-0101'
    profile = client.get('/families/1').text
    rabbi_block = profile[profile.index('Rabbi Rubin'):profile.index('Rabbi Rubin') + 500]
    assert '845-555-0101' in rabbi_block

def test_multiple_shul_gabbais_can_be_added_and_updated(app, client):
    assert post(client, '/families/1/gabbais', {
        'name': 'First Gabbai', 'phone': '845-555-0201'}).status_code == 302
    assert post(client, '/families/1/gabbais', {
        'name': 'Second Gabbai', 'phone': '845-555-0202'}).status_code == 302
    with app.app_context():
        family = db.session.get(Family, 1)
        assert [(g.name, g.phone) for g in family.gabbais] == [
            ('First Gabbai', '845-555-0201'),
            ('Second Gabbai', '845-555-0202'),
        ]
        second_id = family.gabbais[1].id
    assert post(client, f'/gabbais/{second_id}', {
        'name': 'Second Gabbai', 'phone': '845-555-0299'}).status_code == 302
    profile = client.get('/families/1').text
    assert 'First Gabbai' in profile
    assert '845-555-0299' in profile

def test_profile_print_report_lists_and_filters_donations(app, client):
    with app.app_context():
        family = db.session.get(Family, 1)
        contact = family.contacts[0]
        db.session.add(Receipt(contact_id=contact.id, family_id=family.id, amount_cents=4250,
            received_on=date(2026, 9, 2), reference='DON-42', note='Rosh Hashanah'))
        db.session.commit()
    profile = client.get('/families/1').text
    assert '/families/1/print' in profile
    report = client.get('/families/1/print')
    assert report.status_code == 200
    assert 'DON-42' in report.text
    assert '$42.50' in report.text
    assert 'Print / Save PDF' in report.text
    filtered = client.get('/families/1/print?section=donations&q=DON-42&date_from=2026-09-01&date_to=2026-09-30').text
    assert 'DON-42' in filtered
    assert '<h2>Children' not in filtered
    assert client.get('/families/1/print?date_from=2026-10-01&date_to=2026-09-01').status_code == 400

@pytest.mark.parametrize('amount',['NaN','Infinity','-1','0','1.001','1000001','bad'])
def test_invalid_money(client,amount):
    assert post(client,'/families/1/expenses',{'category':'Groceries','payee':'Shop','amount':amount,'month':'2026-09'}).status_code==400

def test_csrf_and_escaping(client):
    assert client.post('/families/new', data={'name':'Forged'}).status_code==400
    assert post(client,'/families/new',{'name':'<script>alert(1)</script>'}).status_code==302
    body=client.get('/families').text
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;' in body

def test_auth(app,client,monkeypatch):
    app.config.update(DEMO=False,ADMIN_EMAIL='staff@example.test',ADMIN_PASSWORD_HASH=generate_password_hash('testing-password'))
    monkeypatch.setattr('time.sleep',lambda _:None)
    assert client.get('/families').status_code==302
    client.get('/login')
    with client.session_transaction() as s: token=s['csrf']
    assert client.post('/login',data={'csrf':token,'email':'staff@example.test','password':'wrong'}).status_code==200
    assert client.get('/families').status_code==302
    assert client.post('/login',data={'csrf':token,'email':'staff@example.test','password':'testing-password'}).status_code==302
    assert client.get('/families').status_code==200
    assert post(client,'/logout',{}).status_code==302
    assert client.get('/families').status_code==302

def test_production_requires_configuration(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.delenv('ADMIN_PASSWORD_HASH',raising=False)
    with pytest.raises(RuntimeError,match='Production requires'):
        create_app()
    monkeypatch.setenv('ADMIN_EMAIL','owner@example.test')
    monkeypatch.setenv('ADMIN_PASSWORD_HASH','plaintext-is-not-a-hash')
    monkeypatch.setenv('SESSION_SECRET','x'*32)
    monkeypatch.setenv('DATABASE_URL','postgresql://example.invalid/yazory')
    with pytest.raises(RuntimeError,match='valid Werkzeug'):
        create_app()

def test_demo_rejects_shared_database(monkeypatch):
    monkeypatch.delenv('APP_ENV',raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD_HASH',raising=False)
    monkeypatch.setenv('DATABASE_URL','postgresql://example.invalid/yazory')
    with pytest.raises(RuntimeError,match='Demo mode'):
        create_app()

def test_existing_demo_database_is_upgraded_before_navigation(monkeypatch, tmp_path):
    database_path = tmp_path / 'legacy.db'
    connection = sqlite3.connect(database_path)
    connection.execute(
        'CREATE TABLE family ('
        'id INTEGER PRIMARY KEY, name VARCHAR(160) NOT NULL, '
        "spouse VARCHAR(160) DEFAULT '', phone VARCHAR(80) DEFAULT '', "
        "address VARCHAR(300) DEFAULT '', father VARCHAR(160) DEFAULT '', "
        "inlaws VARCHAR(160) DEFAULT '', rabbi VARCHAR(160) DEFAULT '', "
        "weekday_shul VARCHAR(160) DEFAULT '', shabbos_shul VARCHAR(160) DEFAULT '', "
        "circumstances TEXT DEFAULT '', status VARCHAR(30) NOT NULL DEFAULT 'Intake')"
    )
    connection.execute("INSERT INTO family (name) VALUES ('Existing family')")
    connection.execute(
        'CREATE TABLE child ('
        'id INTEGER PRIMARY KEY, family_id INTEGER NOT NULL, '
        'name VARCHAR(160) NOT NULL, age INTEGER NOT NULL, '
        "grade VARCHAR(80) DEFAULT '', school VARCHAR(160) NOT NULL, "
        "tuition_contact VARCHAR(300) DEFAULT '')"
    )
    connection.execute(
        "INSERT INTO child (family_id, name, age, school) "
        "VALUES (1, 'Existing child', 18, 'Existing school')"
    )
    connection.commit()
    connection.close()
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        'SECRET_KEY': 'test-only',
    })
    client = app.test_client()

    assert client.get('/families').status_code == 200
    assert client.get('/families/1').status_code == 200
    with app.app_context():
        family_columns = {column['name'] for column in inspect(db.engine).get_columns('family')}
        child_columns = {column['name'] for column in inspect(db.engine).get_columns('child')}
        child = db.session.get(Child, 1)
        assert child.married is False
        assert child.spouse_name == ''
    assert {'city', 'state', 'zip_code'} <= family_columns
    assert {'married', 'spouse_name'} <= child_columns

@pytest.mark.parametrize('language,direction,label',[('en','ltr','Overview'),('he','rtl','לוח בקרה'),('yi','rtl','איבערבליק')])
def test_shared_language_screens(client,language,direction,label):
    result=client.get(f'/language/{language}?next=/expenses%3Fstatus%3DRequested')
    assert result.status_code==302
    assert result.location=='/expenses?status=Requested'
    for path in ['/','/families','/families/new','/families/1','/families/1/edit','/expenses','/activity','/login']:
        page=client.get(path)
        assert page.status_code==200
        assert f'lang="{language}" dir="{direction}"' in page.text
        assert label in page.text
        assert '/static/style.css' in page.text
        assert '/static/yazory-logo.png' in page.text
        for code in ['en','he','yi']:
            assert f'/language/{code}?' in page.text
    # Translations are labels, never database workflow values.
    page=client.get('/expenses').text
    assert 'value="Approved"' in page
    assert post(client,'/expenses/1/status',{'status':'Approved'}).status_code==302

def test_language_redirect_safety(client):
    for target in ['https://example.com','//example.com','/\\example.com']:
        response=client.get('/language/he',query_string={'next':target})
        assert response.location=='/'
    assert client.get('/language/unknown').status_code==404

def test_language_keeps_user_content(client):
    client.get('/language/yi')
    post(client,'/families/new',{'name':'Original family name'})
    assert 'Original family name' in client.get('/families').text

def test_family_address_parts_are_saved_and_displayed(app, client):
    response = post(client, '/families/new', {
        'name':'Address family', 'address':'12 Main Street', 'city':'Monroe',
        'state':'NY', 'zip_code':'10950',
    })
    assert response.status_code == 302
    with app.app_context():
        family = db.session.scalar(db.select(Family).where(Family.name == 'Address family'))
        assert (family.address, family.city, family.state, family.zip_code) == (
            '12 Main Street', 'Monroe', 'NY', '10950')
        family_id = family.id
    page = client.get(f'/families/{family_id}').text
    assert '12 Main Street, Monroe, NY 10950' in page

def test_roles_assignments_and_bootstrap_isolation(monkeypatch):
    """Roles are enforced from the database, including after an assignment is revoked."""
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    owner_hash = generate_password_hash('owner-password-123')
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI':'sqlite://',
                      'SECRET_KEY':'test-only', 'DEMO':False,
                      'ADMIN_EMAIL':'owner@example.test', 'ADMIN_PASSWORD_HASH':owner_hash})
    with app.app_context():
        db.create_all()
    monkeypatch.setattr('time.sleep', lambda _: None)
    owner = app.test_client()
    owner.get('/login')
    with owner.session_transaction() as s: csrf = s['csrf']
    assert owner.post('/login', data={'csrf':csrf, 'email':'owner@example.test',
                                      'password':'owner-password-123'}).status_code == 302
    assert post(owner, '/families/new', {'name':'Assigned family'}).status_code == 302
    assert post(owner, '/families/new', {'name':'Private family'}).status_code == 302
    with app.app_context():
        assigned = db.session.scalar(db.select(Family).where(Family.name == 'Assigned family'))
        private = db.session.scalar(db.select(Family).where(Family.name == 'Private family'))
        # Repeated bootstrap checks preserve records and do not duplicate the owner.
        assert len(db.session.scalars(db.select(StaffUser.id)).all()) == 1
    assert post(owner, '/staff', {'email':'family@example.test', 'password':'family-password-123',
                                  'role':'family_admin'}).status_code == 302
    with app.app_context():
        family_admin = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'family@example.test'))
    assert post(owner, f'/staff/{family_admin.id}/assignments', {'family_id':assigned.id}).status_code == 302
    with app.app_context():
        owner_user = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'owner@example.test'))
    assert post(owner, f'/staff/{owner_user.id}/role', {'role':'family_admin'}).status_code == 400
    with app.app_context():
        assert db.session.get(StaffUser, owner_user.id).role == 'organization_admin'
    staff = app.test_client()
    staff.get('/login')
    with staff.session_transaction() as s: csrf = s['csrf']
    assert staff.post('/login', data={'csrf':csrf, 'email':'family@example.test',
                                      'password':'family-password-123'}).status_code == 302
    assert staff.get(f'/families/{assigned.id}').status_code == 200
    assert staff.get(f'/families/{private.id}').status_code == 403
    assert staff.get('/activity').status_code == 403
    assert staff.get('/settings').status_code == 403
    assert staff.get('/staff').status_code == 403
    assert post(staff, f'/families/{private.id}/contacts',
                {'name':'Denied','relationship':'Sibling','status':'Pledged','monthly':'1'}).status_code == 403
    assert post(staff, f'/families/{assigned.id}/status', {'status':'Under review'}).status_code == 403
    assert post(staff, '/staff', {'email':'nope@example.test','password':'password-password','role':'organization_admin'}).status_code == 403
    assert post(staff, f'/families/{assigned.id}/children',
                {'name':'Allowed','age':'8','school':'School'}).status_code == 302
    assert post(staff, f'/families/{assigned.id}/expenses',
                {'category':'Groceries','payee':'Allowed shop','amount':'10','month':'2026-09'}).status_code == 302
    with app.app_context():
        allowed_contact = Contact(family_id=assigned.id, name='Allowed contact', relationship='Sibling')
        private_contact = Contact(family_id=private.id, name='Private contact', relationship='Sibling')
        private_expense = Expense(family_id=private.id, category='Groceries', payee='Private shop',
                                  amount_cents=1000, month='2026-09')
        db.session.add_all([allowed_contact, private_contact, private_expense])
        db.session.commit()
        private_contact_id = private_contact.id
        private_expense_id = private_expense.id
    assert post(staff, f'/contacts/{private_contact_id}',
                {'status':'Contacted','monthly':'0'}).status_code == 403
    assert post(staff, f'/expenses/{private_expense_id}/status',
                {'status':'Approved'}).status_code == 403
    expense_page = staff.get('/expenses').text
    assert 'Allowed shop' in expense_page
    assert 'Private shop' not in expense_page
    assert 'Staff & assignments' not in staff.get('/').text
    assert 'Sign out' in staff.get('/').text
    owner.get('/language/he')
    assert 'הוקצה מנהל משפחה:' in owner.get(f'/families/{assigned.id}').text
    owner.get('/language/yi')
    assert 'צוגעטיילט א משפחה אדמיניסטראטאר:' in owner.get(f'/families/{assigned.id}').text
    assert post(owner, f'/staff/{family_admin.id}/assignments', {'family_id':assigned.id}).status_code == 302
    assert staff.get(f'/families/{assigned.id}').status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(FamilyAssignment.id).where(
            FamilyAssignment.staff_user_id == family_admin.id,
            FamilyAssignment.family_id == assigned.id)) is None

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
