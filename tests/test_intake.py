import json
import pytest
from app import create_app, db, Family, HouseholdIntake
from intake import validate_intake


def test_budget_persistence_validation_and_blank_intake(monkeypatch):
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI':'sqlite://', 'SECRET_KEY':'test'})
    client = app.test_client()
    for lang in ['en','he','yi']:
        client.get('/language/'+lang)
        page=client.get('/families/new')
        assert page.status_code == 200
        assert 'intake-wizard' in page.text and 'Sample family' not in page.text
        assert page.text.count('data-intake-page') == 5
        assert page.text.count('data-step=') == 5
        assert 'class="card intake-applicant"' in page.text
        assert 'class="sheet-field circumstances-field"' in page.text
        assert 'id="intake-review"' not in page.text
        assert 'style.css?v=20260910-tasks-grouped-sidebar-v1' in page.text
        assert 'intake.js?v=20260910-preserve-step-v1' in page.text
        label = {'en':'Monthly bill ($)', 'he':'סכום החשבון החודשי ($)', 'yi':'וויפיל איז דער ביל א חודש ($)'}[lang]
        assert label in page.text and 'data-entry="monthly_bill"' in page.text
    with client.session_transaction() as session: csrf=session['csrf']
    values={'csrf':csrf,'name':'Wizard household','intake_version':'1','children_count':'4','rent':'1700.25','food':'','his_income':'0','foodstamps':'yes','foodstamps_amount':'250.75','accounts_json':json.dumps([{'kind':'utility','provider':'Local electric','account':'000123','monthly_bill':'123.45'}]),'assistance_json':json.dumps([{'provider':'Community fund','amount':'150.10'}])}
    response=client.post('/families/new',data=values)
    assert response.status_code == 302
    path=response.location
    with app.app_context():
        f=db.session.scalar(db.select(Family).where(Family.name=='Wizard household'))
        stored=db.session.get(HouseholdIntake,f.id).data
        assert stored['rent']==170025 and stored['food'] is None and stored['his_income']==0
        assert stored['accounts'][0]['account']=='000123'
        assert stored['accounts'][0]['monthly_bill']==12345
        assert stored['assistance'][0]['amount']==15010
    edit=client.get(path+'/edit')
    assert edit.status_code==200 and '1700.25' in edit.text and '000123' in edit.text and '123.45' in edit.text
    bad=client.post(path+'/edit',data={**values,'rent':'-3'})
    assert bad.status_code==400 and 'Wizard household' in bad.text
    with app.app_context(): assert db.session.get(HouseholdIntake,f.id).data['rent']==170025
    cleared=client.post(path+'/edit',data={**values,'foodstamps':'no','accounts_json':'[]','assistance_json':'[]','intake_step':'3'})
    assert cleared.status_code==302
    assert cleared.location.endswith(path+'/edit?step=3')
    reopened=client.get(cleared.location)
    assert 'name="intake_step" value="3"' in reopened.text
    with app.app_context():
        stored=db.session.get(HouseholdIntake,f.id).data
        assert stored['foodstamps_amount'] is None and stored['accounts']==[]

@pytest.mark.parametrize('fields',[
 {'rent':'NaN'}, {'rent':'1.001'}, {'children_count':'-1'},
 {'accounts_json':'{}'},
 {'assistance_json':'[{"provider":"Fund","amount":"-1"}]'},
 {'accounts_json':'[{"kind":"madeup","provider":"Foo"}]'},
])
def test_invalid_budget(fields):
    with pytest.raises(ValueError): validate_intake(fields)

def test_intake_is_private_to_assigned_staff(monkeypatch):
    from app import StaffUser, FamilyAssignment
    from werkzeug.security import generate_password_hash
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://','SECRET_KEY':'test','DEMO':False})
    with app.app_context():
        db.create_all()
        a,b=Family(name='Assigned'),Family(name='Private')
        staff=StaffUser(email='staff@example.test',password_hash=generate_password_hash('test-only'),role='family_admin')
        db.session.add_all([a,b,staff]);db.session.flush()
        db.session.add(FamilyAssignment(staff_user_id=staff.id,family_id=a.id))
        db.session.add(HouseholdIntake(family_id=b.id,data={'accounts':[{'provider':'PRIVATE','account':'000555'}]}))
        db.session.commit();aid,bid,uid=a.id,b.id,staff.id
    c=app.test_client()
    with c.session_transaction() as s: s['user_id']=uid;s['csrf']='test-csrf'
    assert c.get(f'/families/{aid}/edit').status_code==200
    assert c.get(f'/families/{bid}/edit').status_code==403
    assert c.post(f'/families/{bid}/edit',data={'csrf':'test-csrf','name':'Changed','intake_version':'1'}).status_code==403
    with app.app_context():
        assert db.session.get(HouseholdIntake,bid).data['accounts'][0]['account']=='000555'
        db.session.get(StaffUser,uid).role='fundraiser';db.session.commit()
    assert c.get(f'/families/{aid}/edit').status_code==403

@pytest.mark.parametrize('amount', ['-1', 'NaN', 'Infinity', '1.001', '1000000.01'])
def test_invalid_account_bill(amount):
    with pytest.raises(ValueError):
        validate_intake({'accounts_json': json.dumps([{'kind':'utility','provider':'Electric','monthly_bill':amount}])})

def test_legacy_and_blank_account_bills():
    from intake import intake_for_form
    row = {'kind':'utility','provider':'Electric','account':'0001'}
    assert intake_for_form({'accounts':[row]})['accounts'][0]['monthly_bill'] == ''
    for amount, expected in [('', None), ('0', 0), ('12.34', 1234)]:
        data = validate_intake({'accounts_json':json.dumps([{**row,'monthly_bill':amount}])})
        assert data['accounts'][0]['monthly_bill'] == expected
        assert intake_for_form(data)['accounts'][0]['monthly_bill'] == ('' if expected is None else amount if amount != '0' else '0.00')
