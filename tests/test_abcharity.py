import pytest
from datetime import datetime
from app import create_app, db, Family, StaffUser, FamilyAssignment, CharityCampaign, CharityDonation, CharityDonor, Contact
from abcharity import normalize, fetch_donations, decrypt_api_key, ERROR
from translations import CATALOG

ROW = dict(id=10, campaign_id=55, amount='18.50', net='17.95', donation_time=1788710400, name='Donor', email='one@example.test', phone='123', address='Road', notes='note', team='Cousins', anonymous_donation='0', is_subscription='1')

@pytest.fixture
def setup(monkeypatch):
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://','DEMO':False,'SECRET_KEY':'test'})
    with app.app_context():
        db.create_all()
        db.session.add_all([Family(id=1,name='Family'), Family(id=2,name='Other'), StaffUser(id=1,email='admin@example.test',password_hash='unused',role='organization_admin'), StaffUser(id=2,email='fund@example.test',password_hash='unused',role='fundraiser'), StaffUser(id=3,email='office@example.test',password_hash='unused',role='office_employee')])
        db.session.add_all([FamilyAssignment(staff_user_id=2,family_id=1), FamilyAssignment(staff_user_id=3,family_id=1)])
        db.session.commit()
    client=app.test_client()
    with client.session_transaction() as s: s.update(user_id=1,csrf='token')
    monkeypatch.setenv('ABCHARITY_KEY_TEST','secret-test-value')
    monkeypatch.setattr('abcharity.fetch_donations',lambda key: [ROW.copy()])
    return app,client

def post(client,path,data=None):
    return client.post(path,data={'csrf':'token',**(data or {})})

def connect(client):
    return post(client,'/families/1/campaign',dict(campaign_id='55',label='Family campaign',currency='USD',api_key='secret-test-value'))

def test_import_repeat_update_and_locales(setup,monkeypatch):
    app,client=setup
    assert connect(client).status_code==302
    assert post(client,'/families/1/donations/sync').status_code==302
    with app.app_context():
        assert CharityDonation.query.count()==1
        assert CharityDonor.query.count()==1
        assert CharityDonation.query.one().net_cents==1795
        assert CharityCampaign.query.one().last_sync
        campaign=CharityCampaign.query.one()
        assert campaign.api_key_encrypted
        assert 'secret-test-value' not in campaign.api_key_encrypted
        assert decrypt_api_key(campaign.api_key_encrypted,app.config['SECRET_KEY'])=='secret-test-value'
    monkeypatch.setattr('abcharity.fetch_donations',lambda key:[{**ROW,'net':'17.00'}])
    post(client,'/families/1/donations/sync')
    with app.app_context(): assert CharityDonation.query.one().net_cents==1700
    for lang,direction in [('en','ltr'),('he','rtl'),('yi','rtl')]:
        with client.session_transaction() as s:s['language']=lang
        result=client.get('/families/1/donations')
        assert result.status_code==200
        assert f'dir="{direction}"' in result.text
        assert 'secret-test-value' not in result.text
        assert (CATALOG['ABCharity donations'][lang] if lang!='en' else 'ABCharity donations') in result.text
    result=app.test_cli_runner().invoke(args=['sync-abcharity'])
    assert result.exit_code==0, result.output

def test_donation_page_uses_consistent_money_and_eastern_time(setup):
    app,client=setup
    connect(client)
    post(client,'/families/1/donations/sync')
    body=client.get('/families/1/donations').text
    assert '$18.50' in body
    assert '$17.95' in body
    assert 'USD 18.50' not in body
    assert 'UTC' not in body
    with app.app_context():
        eastern=app.jinja_env.filters['eastern_time']
        assert eastern(datetime(2026,9,9,14,9),'%m/%d/%Y %I:%M %p %Z') == '09/09/2026 10:09 AM EDT'

def test_profile_accepts_and_masks_campaign_key(setup):
    _,client=setup
    body=client.get('/families/1/donations').text
    assert 'name="api_key" type="password"' in body
    assert 'name="key_env"' not in body
    assert 'secret-test-value' not in body
    assert connect(client).status_code==302
    body=client.get('/families/1/donations').text
    assert 'An encrypted API key is saved for this family.' in body
    assert 'secret-test-value' not in body

def test_existing_environment_key_connection_still_syncs(setup):
    app,client=setup
    with app.app_context():
        db.session.add(CharityCampaign(family_id=1,external_id='55',
            key_env='ABCHARITY_KEY_TEST',label='Legacy campaign',currency='USD'))
        db.session.commit()
    assert post(client,'/families/1/donations/sync').status_code==302
    with app.app_context(): assert CharityDonation.query.count()==1

def test_isolation_linking_and_atomic_error(setup,monkeypatch):
    app,client=setup
    connect(client)
    with app.app_context():
        db.session.add(Contact(id=90,family_id=2,name='Other donor',relationship='Other'))
        db.session.commit()
    with client.session_transaction() as s:s['user_id']=2
    body=client.get('/families/1/donations').text
    assert 'Net less recorded paid expenses' not in body
    assert 'API key setting name' not in body
    assert client.get('/families/2/donations').status_code==403
    assert post(client,'/families/2/donations/sync').status_code==403
    assert connect(client).status_code==403
    assert post(client,'/families/1/donors/1/link',{'contact_id':90}).status_code==403
    monkeypatch.setattr('abcharity.fetch_donations',lambda key:[{**ROW,'id':11},{**ROW,'id':12,'campaign_id':999}])
    post(client,'/families/1/donations/sync')
    with app.app_context():
        assert CharityDonation.query.count()==1
        assert CharityCampaign.query.one().last_error==ERROR
    with client.session_transaction() as s:s['user_id']=3
    assert client.get('/families/1/donations').status_code==403
    assert client.post('/families/1/donations/sync').status_code==400

@pytest.mark.parametrize('field,value',[('amount','NaN'),('net','1.001'),('campaign_id',99),('anonymous_donation','maybe'),('donation_time','bad')])
def test_invalid_receipts(field,value):
    with pytest.raises(ValueError):normalize({**ROW,field:value},'55')

def test_http_encoding_and_failure(monkeypatch):
    class Response:
        status_code=200
        def json(self): return {'num_results':1,'donations':[ROW]}
    def get(url,**kwargs):
        assert kwargs['params']['id']=='a+b/c=='
        assert kwargs['allow_redirects'] is False
        return Response()
    monkeypatch.setattr('abcharity.requests.get',get)
    assert fetch_donations('a%2Bb%2Fc%3D%3D')==[ROW]
    monkeypatch.setattr(Response,'json',lambda _: {'num_results':2,'donations':[ROW]})
    with pytest.raises(ValueError): fetch_donations('a%2Bb%2Fc%3D%3D')
