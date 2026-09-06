from types import SimpleNamespace
from datetime import date
import pytest
from child_budget import parse, calculate, band


def test_age_boundaries_actual_override_and_cents():
    assert [band(a) for a in (0,2,3,5,6,9,10,13,14,17,18,30)] == [0,0,1,1,2,2,3,3,4,4,5,5]
    children=[SimpleNamespace(id=1,name='One',age=6),SimpleNamespace(id=2,name='Two',age=14)]
    data=parse({'rate_2_food':'100','rate_4_food':'200','child_2_food':'250.25','actual_housing':'12000.01','period_housing':'annual'},children)
    r=calculate(data,{'his_income':50000,'accounts':[{'kind':'grocery','monthly_bill':30000,'budget_treatment':'food'}]},children)
    assert r['children'][1]['total']==25025
    assert r['costs']==135025 and r['gap']==85025
    data['categories']['food']={'amount':50000,'period':'monthly'}
    r=calculate(data,{'food':70000,'accounts':[{'kind':'grocery','monthly_bill':30000,'budget_treatment':'additional'}]},children)
    assert r['costs']==150000  # actual total replaces both provider and child costs
    data['categories']['food']['amount']=0
    assert calculate(data,{},children)['costs']==100000


def test_birthday_and_invalid_values():
    child=SimpleNamespace(id=1,name='Baby',age=15)
    data=parse({'dob_1':date.today().isoformat(),'rate_0_food':'50'},[child])
    report=calculate(data,{},[child])
    assert report['children'][0]['age']==0 and report['children'][0]['total']==5000
    for value in ['NaN','Infinity','-1','0.001','1000001']:
        with pytest.raises(ValueError): parse({'child_1_food':value},[child])
    with pytest.raises(ValueError): parse({'dob_1':'3000-01-01'},[child])


def test_save_permissions_locales_and_intake_isolation(monkeypatch):
    from app import create_app, db, Family, Child, HouseholdBudget, HouseholdIntake, StaffUser, FamilyAssignment
    for k in ('APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET'): monkeypatch.delenv(k,raising=False)
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://','SECRET_KEY':'test','DEMO':False})
    with app.app_context():
        db.create_all()
        f=Family(name='Household'); u=StaffUser(email='a@test',role='family_admin',password_hash='unused')
        db.session.add_all([f,u]); db.session.flush()
        child=Child(family_id=f.id,name='Child',age=8,school='School')
        db.session.add_all([child,FamilyAssignment(staff_user_id=u.id,family_id=f.id),HouseholdIntake(family_id=f.id,data={'rent':100000})]); db.session.commit()
        fid,uid,cid=f.id,u.id,child.id
    c=app.test_client(); url=f'/families/{fid}/expense-report'
    with c.session_transaction() as s: s['user_id']=uid;s['csrf']='test'
    form={'csrf':'test','actual_housing':'1200','rate_2_food':'100',f'age_{cid}':'9'}
    assert c.post(url,data=form).status_code==302
    for lang in ('en','he','yi'):
        c.get('/language/'+lang)
        page=c.get(url)
        assert page.status_code==200 and '$1,300.00' in page.text
        assert f'name="child_{cid}_food"' in page.text
    with app.app_context():
        assert db.session.get(Child,cid).age==9
        assert db.session.get(HouseholdBudget,fid).data['categories']['housing']['amount']==120000
    assert c.post(url,data={**form,'actual_housing':'-2'}).status_code==400
    with app.app_context():
        assert db.session.get(HouseholdBudget,fid).data['categories']['housing']['amount']==120000
        assert db.session.get(HouseholdIntake,fid).data['rent']==100000
        db.session.get(StaffUser,uid).role='fundraiser';db.session.commit()
    assert c.post(url,data=form).status_code==403
    with app.app_context():
        db.session.get(StaffUser,uid).role='family_admin';db.session.execute(db.delete(FamilyAssignment));db.session.commit()
    assert c.get(url).status_code==403 and c.post(url,data=form).status_code==403
