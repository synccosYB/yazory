import pytest
from app import create_app, db, Family, Expense, Contact, Audit
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

def test_demo_rejects_shared_database(monkeypatch):
    monkeypatch.delenv('APP_ENV',raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD_HASH',raising=False)
    monkeypatch.setenv('DATABASE_URL','postgresql://example.invalid/yazory')
    with pytest.raises(RuntimeError,match='Demo mode'):
        create_app()
