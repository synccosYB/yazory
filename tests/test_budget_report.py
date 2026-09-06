import json
import pytest
from budget_report import household_report
from intake import validate_intake, intake_for_form


def test_shortfall_without_duplicate_bills():
    data = dict(rent=200000, food=100000, his_income=100000, her_income=50000,
                other_income=0, foodstamps='yes', foodstamps_amount=30000,
                other_assistance='yes', assistance=[dict(provider='Fund', amount=20000)],
                accounts=[dict(provider='Grocery',kind='grocery',monthly_bill=100000,budget_treatment='food'),
                          dict(provider='Utility',kind='utility',monthly_bill=25000,budget_treatment='additional')])
    r=household_report(data)
    assert (r['costs'],r['earnings'],r['income_gap'],r['gap'],r['missing']) == (325000,150000,175000,125000,0)
    data['his_income']=500000
    r=household_report(data)
    assert r['gap']==0 and r['surplus']==275000


def test_food_stamps_cannot_pay_rent():
    r=household_report(dict(rent=100000,food=10000,his_income=0,her_income=0,other_income=0,
                           foodstamps='yes',foodstamps_amount=30000,other_assistance='no'))
    assert r['usable_help']==10000 and r['gap']==100000


def test_unknown_bills_are_flagged_not_silently_added():
    r=household_report({'accounts':[{'provider':'Old account','monthly_bill':20000}]})
    assert r['missing']>0 and r['costs']==0
    assert household_report({})['missing']>0


def test_treatment_persists_and_validates():
    form={'accounts_json':json.dumps([dict(kind='utility',provider='Electric',monthly_bill='25.10',budget_treatment='additional')])}
    data=validate_intake(form)
    assert data['accounts'][0]['monthly_bill']==2510
    assert intake_for_form(data)['accounts'][0]['budget_treatment']=='additional'
    with pytest.raises(ValueError):
        validate_intake({'accounts_json':json.dumps([dict(kind='utility',provider='Electric',budget_treatment='bad')])})


def test_report_locales_and_permissions(monkeypatch):
    from app import create_app, db, Family, StaffUser, FamilyAssignment, HouseholdIntake
    for key in ['APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET']:
        monkeypatch.delenv(key,raising=False)
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://','SECRET_KEY':'test','DEMO':False})
    with app.app_context():
        db.create_all()
        f=Family(name='Report family')
        user=StaffUser(email='staff@example.test',role='family_admin',password_hash='unused')
        db.session.add_all([f,user]);db.session.flush()
        fid,uid=f.id,user.id
        db.session.add(HouseholdIntake(family_id=fid,data={'rent':200000,'food':50000,'his_income':100000}))
        db.session.add(FamilyAssignment(staff_user_id=uid,family_id=fid));db.session.commit()
    c=app.test_client()
    url=f'/families/{fid}/expense-report'
    assert c.get(url).status_code==302
    with c.session_transaction() as s: s['user_id']=uid
    for lang,label in [('en','Monthly expense report'),('he','דוח הוצאות חודשי'),('yi','חודש׳ליכער הוצאות באריכט')]:
        c.get('/language/'+lang)
        page=c.get(url)
        assert page.status_code==200 and label in page.text and '$1,500.00' in page.text
    with app.app_context():
        db.session.get(StaffUser,uid).role='office_employee';db.session.commit()
    assert c.get(url).status_code==200
    with app.app_context():
        db.session.get(StaffUser,uid).role='fundraiser';db.session.commit()
    assert c.get(url).status_code==403
    with app.app_context():
        db.session.get(StaffUser,uid).role='family_admin'
        db.session.execute(db.delete(FamilyAssignment));db.session.commit()
    assert c.get(url).status_code==403
