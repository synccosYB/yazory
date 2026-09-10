from datetime import date, timedelta
from io import BytesIO
import pytest
from app import create_app, db, Family, StaffUser, FamilyAssignment, Contact, HouseholdIntake, HouseholdBudget, Expense
from workflow_catalog import CATALOG, ROLES, FIELDS

@pytest.fixture
def env(monkeypatch):
    for k in ('APP_ENV','DATABASE_URL','ADMIN_EMAIL','ADMIN_PASSWORD_HASH','SESSION_SECRET'):monkeypatch.delenv(k,raising=False)
    app=create_app({'TESTING':True,'DEMO':False,'WORKFLOW_ENFORCEMENT':True,'SECRET_KEY':'test','SQLALCHEMY_DATABASE_URI':'sqlite://'})
    M=app.extensions['workflows']['models'];today=date.today()
    with app.app_context():
        db.create_all();f=Family(name='Workflow household',status='Intake');other=Family(name='Private family')
        users=[StaffUser(email=f'{role}@test.example',role='organization_admin' if role=='owner' else 'family_admin',password_hash='unused') for role in ['owner']+list(ROLES)+['second_case','outsider']]
        db.session.add_all([f,other]+users);db.session.flush()
        ids={u.email.split('@')[0]:u.id for u in users};fid=f.id
        for role in ROLES:db.session.add(M['WorkflowRole'](user_id=ids[role],role=role))
        db.session.add(M['WorkflowRole'](user_id=ids['second_case'],role='case_admin'))
        for u in users:
            if u.id!=ids['outsider']:db.session.add(FamilyAssignment(staff_user_id=u.id,family_id=fid))
        db.session.add(HouseholdIntake(family_id=fid,data={'his_income':0,'her_income':0,'other_income':0,'foodstamps':'no','other_assistance':'no','children_count':0}))
        from child_budget import CATEGORIES
        db.session.add(HouseholdBudget(family_id=fid,data={'categories':{k:{'amount':100000 if k=='housing' else 0,'period':'monthly'} for k,_ in CATEGORIES}}))
        c=Contact(family_id=fid,name='Supporter',relationship='Sibling',monthly_cents=0,status='To contact');db.session.add(c);db.session.commit();cid=c.id
    class Env:
        def client(self,role='owner'):
            c=app.test_client()
            with c.session_transaction() as s:s['user_id']=ids[role];s['csrf']='test'
            return c
        def create(self,kind,data=None,role='owner',evidence=True):
            fields={'family_id':fid,'title':kind,'owner_id':ids[role],'due':today.isoformat(),'priority':'Normal','csrf':'test',**(data or {})}
            response=self.client(role).post('/operations/new/'+kind,data=fields)
            assert response.status_code==302,response.text
            wid=int(response.location.split('/')[-1])
            if evidence:
                r=self.client(role).post(f'/operations/{wid}/files',data={'csrf':'test','file':(BytesIO(b'%PDF-1.4 proof'),'proof.pdf')})
                assert r.status_code==302,r.text
            return wid
        def upload(self,wid,purpose='Payment proof',role='owner'):
            return self.client(role).post(f'/operations/{wid}/files',data={'csrf':'test','purpose':purpose,'file':(BytesIO(b'%PDF-1.4 confirmed external payment'),'payment.pdf')})
        def act(self,wid,role='owner',action='Advance',**data):
            with app.app_context():version=db.session.get(M['WorkItem'],wid).version
            return self.client(role).post(f'/operations/{wid}/action',data={'csrf':'test','version':version,'action':action,'note':'Verified supporting evidence',**data})
        def finish(self,wid,extra=None):
            for _ in range(20):
                with app.app_context():
                    w=db.session.get(M['WorkItem'],wid)
                    if w.disposition=='Complete':return
                    role=CATALOG[w.kind]['steps'][w.stage][1]
                    if role=='owner':role='owner'
                    signed=db.session.scalar(db.select(M['WorkflowDecision'].id).where(M['WorkflowDecision'].item_id==wid,M['WorkflowDecision'].stage==w.stage,M['WorkflowDecision'].actor_id==ids.get(role)))
                    if signed and role=='case_admin':role='second_case'
                r=self.act(wid,role,**(extra or {}));assert r.status_code==302,(role,r.text)
            assert False,'Workflow did not complete'
    e=Env();e.app=app;e.M=M;e.ids=ids;e.fid=fid;e.cid=cid;e.today=today
    return e


def test_catalog_and_all_workflow_forms_render_in_three_locales(env):
    assert sorted(s['number'] for s in CATALOG.values())==list(range(1,36))
    with env.app.app_context():
        env_user=db.session.get(StaffUser,env.ids['owner'])
        db.session.add(env.M['WorkflowRole'](user_id=env_user.id,role='compliance'));db.session.commit()
    c=env.client()
    for lang in ('en','he','yi'):
        c.get('/language/'+lang)
        for kind in CATALOG:
            r=c.get(f'/operations/new/{kind}?family_id={env.fid}')
            assert r.status_code==200,(kind,r.text)
            assert f'lang="{lang}" dir="'+('ltr' if lang=='en' else 'rtl')+'"' in r.text
        for path in ['/operations','/workflow-access',f'/families/{env.fid}/network',f'/families/{env.fid}/ledger']:
            assert c.get(path).status_code==200


def prepare_case(e):
    t=e.today.isoformat();end=(e.today+timedelta(days=365)).isoformat();review=(e.today+timedelta(days=30)).isoformat()
    w=e.create('governance',{'legal_name':'Yazory','banking':'Verified externally','policies':'Approved policy','large_limit':'10000','cash_limit':'100','review_date':end});e.finish(w)
    w=e.create('referral',{'referrer':'Rabbi','relationship':'Rabbi','reason':'Household support','safe_contact':'Phone','consent':'yes'});e.finish(w)
    w=e.create('intake',{'summary':'Intake complete','consent':'yes','privacy':'Confidential','contact_permission':'yes'});e.finish(w)
    w=e.create('verification',{'verification':'Verified bills and income',**{k:'Verified' for k in CATALOG['verification']['fields'] if k.startswith('verify_')}});e.finish(w)
    assessment=e.create('assessment',{'approved_categories':'Groceries, Rent / mortgage','support_limit':'1000','family_contribution':'0','org_cost':'0','fees':'0','reserve':'0','start':t,'end':end,'review_date':review,'surplus':'Donor authorization required'});e.finish(assessment)
    case=e.create('case_approval',{'assessment_id':assessment,'privacy':'Private','contact_permission':'yes','surplus':'Donor authorization required'});e.finish(case)
    plan=e.create('support_plan',{'case_approval_id':case,'summary':'Monthly household assistance','start':t,'end':end,'review_date':review});e.finish(plan)
    vendor=e.create('vendor',{'payee':'Grocery store','banking':'Verified account reference','summary':'Verified vendor'});e.finish(vendor)
    return assessment,case,plan,vendor


def collection(e,amount='1000',reference='bank-in-1'):
    w=e.create('collection',{'contact_id':e.cid,'amount':amount,'reference':reference,'restrictions':'This case','payment_method':'Bank transfer','receipt_preference':'Email'})
    for role in ['owner','owner','finance','finance']:
        r=e.act(w,role,payment_result='Settled by bank');assert r.status_code==302,r.text
    # Posted: funds exist only after confirmed collection, not scheduling.
    return w


def reconcile(e,wid):
    with e.app.app_context():
        le=db.session.scalar(db.select(e.M['LedgerEntry']).where(e.M['LedgerEntry'].source_item_id==wid));lid=le.id;amount=le.amount_cents
    r=e.create('reconciliation',{'ledger_id':lid,'bank_ref':f'bank-match-{lid}','bank_date':e.today.isoformat(),'bank_amount':f'{amount/100:.2f}'})
    e.finish(r)


def test_real_intake_to_payment_reconciliation_and_closure(env):
    a,c,p,v=prepare_case(env)
    with env.app.app_context():
        assert db.session.get(Family,env.fid).status=='Active'
        assert db.session.get(env.M['WorkItem'],a).data['gap']==100000
        decisions=list(db.session.scalars(db.select(env.M['WorkflowDecision']).where(env.M['WorkflowDecision'].item_id==c,env.M['WorkflowDecision'].role=='case_admin')))
        assert len({d.actor_id for d in decisions})==2
    donation=collection(env);reconcile(env,donation)
    env.finish(donation,{'receipt':'Receipt-001'})
    expense=env.create('expense',{'plan_id':p,'vendor_id':v,'amount':'1000','invoice':'INV-1','month':env.today.strftime('%Y-%m'),'category':'Groceries','expense_type':'Family assistance','reason':'Verified bill'})
    for role in ['owner','owner','case_admin','finance','owner','payment_approver','payment_releaser']:
        if role=='payment_releaser':assert env.upload(expense).status_code==302
        r=env.act(expense,role,reference='bank-out-1',payment_result='Paid by bank');assert r.status_code==302,(role,r.text)
    with env.app.app_context():
        assert env.app.extensions['workflows']['financials'](env.fid)['balance']==0
        assert db.session.get(env.M['WorkItem'],expense).stage==7
    reconcile(env,expense);env.finish(expense)
    closure=env.create('closure',{'reason':'Assistance completed','surplus':'No remaining funds','notification':'Required donors notified'})
    env.finish(closure)
    with env.app.app_context():assert db.session.get(Family,env.fid).status=='Closed'


def test_independent_approvals_stale_updates_and_revision_history(env):
    with env.app.app_context():
        db.session.add(env.M['WorkflowRole'](user_id=env.ids['owner'],role='finance'));db.session.commit()
    w=env.create('governance',{'legal_name':'Yazory','banking':'Verified','policies':'Policy','large_limit':'5000','cash_limit':'100','review_date':(env.today+timedelta(days=365)).isoformat()})
    assert env.act(w).status_code==302
    assert env.act(w).status_code==403 # administrator + finance grant still cannot approve own submission
    assert env.act(w,'finance',action='Return').status_code==302
    with env.app.app_context():
        row=db.session.get(env.M['WorkItem'],w);assert row.stage==0 and row.revision==2
        assert db.session.scalar(db.select(db.func.count()).select_from(env.M['WorkflowDecision']))==1
    assert env.client().post(f'/operations/{w}/action',data={'csrf':'test','version':1,'action':'Advance','note':'stale'}).status_code==409
    assert env.client('outsider').get(f'/operations/{w}').status_code==403


def test_no_budget_or_funds_cannot_pay_and_legacy_cannot_bypass(env):
    r=env.client().post(f'/families/{env.fid}/status',data={'csrf':'test','status':'Active'})
    assert r.status_code==302 and '/operations' in r.location
    with env.app.app_context():assert db.session.get(Family,env.fid).status=='Intake'
    a,c,p,v=prepare_case(env)
    expense=env.create('expense',{'plan_id':p,'vendor_id':v,'amount':'10','invoice':'INV-2','month':env.today.strftime('%Y-%m'),'category':'Groceries','expense_type':'Family assistance','reason':'Bill'})
    for role in ['owner','owner','case_admin']:assert env.act(expense,role).status_code==302
    r=env.act(expense,'finance');assert r.status_code==400 and 'enough collected' in r.text
    with env.app.app_context():
        e=Expense(family_id=env.fid,category='Groceries',payee='Store',amount_cents=100,month=env.today.strftime('%Y-%m'),status='Approved');db.session.add(e);db.session.commit();eid=e.id
    r=env.client().post(f'/expenses/{eid}/status',data={'csrf':'test','status':'Paid','payment_reference':'fake'})
    assert '/operations/' in r.location
    with env.app.app_context():assert db.session.get(Expense,eid).status=='Approved'


def test_missing_assistance_and_edited_budget_invalidate_assessment(env):
    from child_budget import calculate,CATEGORIES
    b={'categories':{k:{'amount':0,'period':'monthly'} for k,_ in CATEGORIES}}
    assert calculate(b,{'his_income':0,'her_income':0,'other_income':0,'foodstamps':'yes','other_assistance':'yes'},[])['missing']>=2
    a,c,p,v=prepare_case(env)
    with env.app.app_context():
        budget=db.session.get(HouseholdBudget,env.fid);budget.data={'categories':{k:{'amount':1,'period':'monthly'} for k,_ in CATEGORIES}};db.session.commit()
    w=env.create('support_plan',{'case_approval_id':c,'summary':'Changed plan','start':env.today.isoformat(),'end':(env.today+timedelta(days=90)).isoformat(),'review_date':(env.today+timedelta(days=20)).isoformat()})
    for role in ['owner','owner','case_admin']:assert env.act(w,role).status_code==302
    r=env.act(w,'finance');assert r.status_code==400 and 'budget changed' in r.text


def test_contact_assignment_privacy_tree_cycle_and_do_not_contact(env):
    with env.app.app_context():
        user=db.session.get(StaffUser,env.ids['fundraising']);user.role='fundraiser';db.session.commit()
    c=env.client()
    data={'csrf':'test','contact_id':env.cid,'name':'Sibling','phone':'00123','relationship':'Sibling','side':'Husband','permission':'Permitted','verified':'yes','assigned_to':env.ids['fundraising']}
    assert c.post(f'/families/{env.fid}/network',data=data).status_code==302
    assert 'Sibling' in env.client('fundraising').get(f'/families/{env.fid}/network').text
    assert env.client('fundraising').get(f'/families/{env.fid}/ledger').status_code==403
    assert c.post(f'/families/{env.fid}/network',data={**data,'parent_id':env.cid}).status_code==400
    assert c.post(f'/families/{env.fid}/network',data={**data,'permission':'Do not contact'}).status_code==302
    assert env.client('fundraising').post(f'/contacts/{env.cid}',data={'csrf':'test','status':'Pledged','monthly':'20'}).status_code==403
    assert env.client('outsider').get(f'/families/{env.fid}/network').status_code==403


def test_posted_transactions_cannot_cancel_or_double_post(env):
    w=collection(env)
    assert env.act(w,action='Cancel').status_code==400
    with env.app.app_context():assert env.app.extensions['workflows']['financials'](env.fid)['balance']==100000
    duplicate=env.create('collection',{'contact_id':env.cid,'amount':'1000','reference':'bank-in-1','restrictions':'Case','payment_method':'Bank','receipt_preference':'Email'})
    for role in ['owner','owner','finance']:assert env.act(duplicate,role,payment_result='Settled').status_code==302
    assert env.act(duplicate,'finance',payment_result='Settled').status_code==409
    with env.app.app_context():assert env.app.extensions['workflows']['financials'](env.fid)['balance']==100000


def test_staff_deactivation_revokes_existing_session(env):
    user=env.ids['intake'];c=env.client('intake')
    w=env.create('access_change',{'user_id':user,'access_change':'Deactivate','handover':env.ids['case_admin'],'reason':'Staff departed'})
    assert env.act(w).status_code==302
    assert c.get('/families').status_code==302


def test_escalation_is_idempotent_and_evidence_is_preserved(env):
    w=env.create('task',{'summary':'Call family','documents':'Consent','escalation_user':env.ids['case_admin']})
    with env.app.app_context():
        db.session.get(env.M['WorkItem'],w).due=env.today-timedelta(days=1);db.session.commit()
    runner=env.app.test_cli_runner()
    assert runner.invoke(args=['workflow-escalate']).exit_code==0
    assert runner.invoke(args=['workflow-escalate']).output.strip()=='Escalated 0 overdue workflows.'
    with env.app.app_context():f=db.session.scalar(db.select(env.M['WorkflowFile']).where(env.M['WorkflowFile'].item_id==w));fileid=f.id
    assert env.client('outsider').get(f'/operations/files/{fileid}').status_code==403
    assert env.client().get(f'/operations/files/{fileid}').status_code==200


def test_refund_limits_transfer_balances_and_batch_release(env):
    a,c,p,v=prepare_case(env);donation=collection(env,'1000')
    expense=env.create('expense',{'plan_id':p,'vendor_id':v,'amount':'100','invoice':'Batch-1','month':env.today.strftime('%Y-%m'),'category':'Groceries','expense_type':'Family assistance','reason':'Bill'})
    for role in ['owner','owner','case_admin','finance']:assert env.act(expense,role).status_code==302
    batch=env.create('payment_batch',{'summary':'Verified batch','reference':'batch-1','batch_items':str(expense)})
    for role in ['owner','finance','payment_approver']:assert env.act(batch,role).status_code==302
    assert env.upload(batch).status_code==302
    assert env.act(batch,'payment_releaser',payment_result='Confirmed bank batch').status_code==302
    with env.app.app_context():assert env.app.extensions['workflows']['financials'](env.fid)['balance']==90000
    refund=env.create('refund',{'source_id':donation,'amount':'100','reason':'Donor requested','reference':'refund-1','notification':'Donor notified'})
    for role in ['owner','finance','case_admin','second_case']:assert env.act(refund,role).status_code==302
    assert env.upload(refund).status_code==302
    assert env.act(refund,'payment_releaser',payment_result='Refund settled').status_code==302
    with env.app.app_context():
        other=db.session.scalar(db.select(Family).where(Family.id!=env.fid));otherid=other.id
        for role in ['finance','rabbi','payment_releaser']:db.session.add(FamilyAssignment(staff_user_id=env.ids[role],family_id=otherid))
        db.session.commit()
    transfer=env.create('transfer',{'target_family':otherid,'amount':'200','reason':'Authorized transfer','donor_authorization':'yes','reference':'transfer-1'})
    env.finish(transfer)
    with env.app.app_context():
        assert env.app.extensions['workflows']['financials'](env.fid)['balance']==60000
        assert env.app.extensions['workflows']['financials'](otherid)['balance']==20000


def test_onboarding_blocks_login_until_independent_approval(env):
    a,c,p,v=prepare_case(env)
    response=env.client().post('/staff',data={'csrf':'test','email':'newstaff@example.test','password':'valid-password-123','role':'office_employee'})
    assert response.status_code==302
    with env.app.app_context():
        u=db.session.scalar(db.select(StaffUser).where(StaffUser.email=='newstaff@example.test'));uid=u.id
        assert not db.session.get(env.M['StaffAccess'],uid).active
        w=db.session.scalar(db.select(env.M['WorkItem']).where(env.M['WorkItem'].kind=='onboarding'));wid=w.id;version=w.version
    response=env.client().post(f'/operations/{wid}',data={'csrf':'test','version':version,'title':'Onboard staff','due':env.today.isoformat(),'user_id':uid,'training':'Identity and training verified'})
    assert response.status_code==302
    env.finish(wid)
    with env.app.app_context():assert db.session.get(env.M['StaffAccess'],uid).active


def test_workflow_labels_have_hebrew_and_yiddish_translations():
    from translations import CATALOG as translations
    labels=set(ROLES.values())|{s['title'] for s in CATALOG.values()}|{st[0] for s in CATALOG.values() for st in s['steps']}|{f[1] for f in FIELDS.values()}
    assert not [label for label in labels if label not in translations or not all(translations[label].get(lang) for lang in ('he','yi'))]


def test_imported_receipt_fees_reconciliation_and_reviewed_correction(env):
    from app import CharityCampaign,CharityDonor,CharityDonation
    from datetime import datetime
    with env.app.app_context():
        camp=CharityCampaign(family_id=env.fid,external_id='55',key_env='ABCHARITY_KEY_TEST',label='Case campaign',currency='USD')
        db.session.add(camp);db.session.flush()
        donor=CharityDonor(campaign_id=camp.id,identity='receipt:1',name='Donor',email='',phone='',address='',contact_id=env.cid);db.session.add(donor);db.session.flush()
        d=CharityDonation(campaign_id=camp.id,donor_id=donor.id,external_id='1',amount_cents=10000,net_cents=9700,donation_time=datetime.now(),anonymous=False,subscription=False,team='',notes='')
        db.session.add(d);db.session.commit();did=d.id
        f=env.app.extensions['workflows']['financials'](env.fid)
        assert f['collected']==10000 and f['balance']==9700 and f['overhead']==300 and f['imported_pending']==1
    response=env.client().post(f'/families/{env.fid}/donations/{did}/workflow',data={'csrf':'test'})
    assert response.status_code==302
    wid=int(response.location.split('/')[-1].split('?')[0])
    queue=env.client().get('/operations')
    assert queue.status_code==200
    assert 'Action queue' in queue.text
    assert 'All workflows' not in queue.text
    assert 'ABCharity donation 1' not in queue.text
    with env.app.app_context():w=db.session.get(env.M['WorkItem'],wid);version=w.version
    assert env.client().post(f'/operations/{wid}',data={'csrf':'test','version':version,'title':'Imported donation','due':env.today.isoformat(),'contact_id':env.cid,'amount':'100','reference':'abcharity:55:1','restrictions':'Family','payment_method':'ABCharity','receipt_preference':'Email'}).status_code==302
    assert env.upload(wid,'Supporting evidence').status_code==302
    for role in ['owner','owner','finance','finance']:assert env.act(wid,role,payment_result='Settled receipt').status_code==302
    with env.app.app_context():
        f=env.app.extensions['workflows']['financials'](env.fid)
        assert f['balance']==9700 and f['collected']==10000 and f['overhead']==300 and f['imported_pending']==0
        entry=db.session.scalar(db.select(env.M['LedgerEntry']).where(env.M['LedgerEntry'].source_item_id==wid,env.M['LedgerEntry'].entry_type=='Donation'));lid=entry.id
    r=env.create('reconciliation',{'ledger_id':lid,'bank_ref':'processor-deposit-1','bank_date':env.today.isoformat(),'bank_amount':'97'})
    env.finish(r)
    with env.app.app_context():
        assert env.app.extensions['workflows']['financials'](env.fid)['unmatched']==0
        d=db.session.get(CharityDonation,did);d.net_cents=9600;db.session.commit()
    with env.app.test_request_context():
        from flask import session
        session['user_id']=env.ids['owner']
        with pytest.raises(Exception) as error:env.app.extensions['workflows']['check_import_case'](env.fid)
        assert error.value.code==400
    correction=env.create('unusual',{'source_id':wid,'risk':'Processor changed fee','resolution':'Verified a further one-dollar fee'})
    env.finish(correction)
    with env.app.app_context():
        f=env.app.extensions['workflows']['financials'](env.fid);assert f['balance']==9600 and f['overhead']==400
        assert env.app.extensions['workflows']['import_consistent'](db.session.get(env.M['WorkItem'],wid))


def test_governance_cutover_is_durable_and_respects_staff_status(env):
    env.app.config['WORKFLOW_ENFORCEMENT']=False
    with env.app.app_context():
        assert not env.app.extensions['workflows']['enforced']()
    prepare_case(env)
    with env.app.app_context():
        assert env.app.extensions['workflows']['enforced']()
        policy=db.session.scalar(db.select(env.M['WorkflowPolicy']))
        policy.data={**policy.data,'review_date':'2000-01-01'}
        user=db.session.get(StaffUser,env.ids['finance']);user.status='deactivated'
        db.session.commit()
        assert env.app.extensions['workflows']['enforced']()
        assert not env.app.extensions['workflows']['active_user'](user)
    assert env.client('finance').get('/operations').status_code==302


def test_stripe_release_requires_workflow_signature_funds_and_verified_destination(env,monkeypatch):
    import app_original as app_module
    from app import StripeRecipient,StripeTransfer
    _,_,plan,_=prepare_case(env);collection(env)
    vendor=env.create('vendor',{'payee':'Grocery store','banking':'Verified by finance',
        'stripe_account':'acct_verified','summary':'Verified vendor'})
    env.finish(vendor)
    env.app.config['STRIPE_SECRET_KEY']='sk_test_fixture'
    with env.app.app_context():
        releaser=db.session.get(StaffUser,env.ids['payment_releaser']);releaser.role='organization_admin'
        expense=Expense(family_id=env.fid,category='Groceries',payee='Grocery store',
            amount_cents=10000,month=env.today.strftime('%Y-%m'),status='Requested')
        recipient=StripeRecipient(kind='vendor',recipient_key='vendor-fixture',email='vendor@example.test',name='Grocery store',stripe_account_id='acct_verified',payouts_enabled=True)
        db.session.add_all([expense,recipient]);db.session.commit();eid=expense.id;rid=recipient.id
    response=env.client().post(f'/expenses/{eid}/workflow',data={'csrf':'test'})
    wid=int(response.location.split('/')[-1].split('?')[0])
    with env.app.app_context():version=db.session.get(env.M['WorkItem'],wid).version
    response=env.client().post(f'/operations/{wid}',data={'csrf':'test','version':version,
        'title':'Grocery invoice','due':env.today.isoformat(),'plan_id':plan,'vendor_id':vendor,
        'amount':'100','invoice':'STRIPE-INV-1','month':env.today.strftime('%Y-%m'),
        'category':'Groceries','expense_type':'Family assistance','reason':'Verified bill'})
    assert response.status_code==302
    assert env.upload(wid,'Invoice').status_code==302
    for role in ['owner','owner','case_admin','finance','owner','payment_approver']:
        assert env.act(wid,role).status_code==302
    calls=[]
    def transfer(secret,params,key):
        calls.append(params)
        assert params['destination']=='acct_verified' and params['amount']==10000
        assert key==f'yazory-expense-{eid}'
        return {'id':'tr_workflow_fixture'}
    monkeypatch.setattr(app_module,'create_transfer',transfer)
    payload={'csrf':'test','recipient_id':rid}
    assert env.client().post(f'/expenses/{eid}/stripe-transfer',data=payload).status_code==403
    assert not calls
    with env.app.app_context():
        recipient=db.session.get(StripeRecipient,rid);recipient.stripe_account_id='acct_wrong';db.session.commit()
    assert env.client('payment_releaser').post(f'/expenses/{eid}/stripe-transfer',data=payload).status_code==400
    assert not calls
    with env.app.app_context():
        recipient=db.session.get(StripeRecipient,rid);recipient.stripe_account_id='acct_verified';db.session.commit()
    assert env.client('payment_releaser').post(f'/expenses/{eid}/stripe-transfer',data=payload).status_code==302
    assert len(calls)==1
    assert env.client('payment_releaser').post(f'/expenses/{eid}/stripe-transfer',data=payload).status_code==400
    with env.app.app_context():
        assert db.session.get(env.M['WorkItem'],wid).stage==7
        assert env.app.extensions['workflows']['financials'](env.fid)['balance']==90000
        assert db.session.get(Expense,eid).payment_reference=='tr_workflow_fixture'
        assert db.session.scalar(db.select(db.func.count()).select_from(StripeTransfer))==1
        assert db.session.scalar(db.select(env.M['WorkflowFile']).where(env.M['WorkflowFile'].purpose=='Payment proof'))


def test_existing_receipt_review_preserves_source_and_posts_once(env):
    from app import Receipt
    with env.app.app_context():
        receipt=Receipt(contact_id=env.cid,family_id=env.fid,amount_cents=1800,
            received_on=env.today,reference='pi_fixture',note='Processed securely by Stripe')
        db.session.add(receipt);db.session.commit();rid=receipt.id
    response=env.client().post(f'/collections/receipts/{rid}/workflow',data={'csrf':'test'})
    wid=int(response.location.split('/')[-1].split('?')[0])
    assert env.client().post(f'/collections/receipts/{rid}/workflow',data={'csrf':'test'}).location.endswith(f'/operations/{wid}')
    with env.app.app_context():
        assert env.app.extensions['workflows']['financials'](env.fid)['balance']==0
        version=db.session.get(env.M['WorkItem'],wid).version
    payload={'csrf':'test','version':version,'title':'Receipt review','due':env.today.isoformat(),
        'contact_id':env.cid,'amount':'19','reference':'receipt:pi_fixture',
        'restrictions':'This case','payment_method':'Stripe','receipt_preference':'Email'}
    assert env.client().post(f'/operations/{wid}',data=payload).status_code==302
    assert env.upload(wid,'Supporting evidence').status_code==302
    denied=env.act(wid)
    assert denied.status_code==400 and 'receipt changed' in denied.text
    with env.app.app_context():payload['version']=db.session.get(env.M['WorkItem'],wid).version
    payload['amount']='18'
    assert env.client().post(f'/operations/{wid}',data=payload).status_code==302
    for role in ['owner','owner','finance','finance']:
        assert env.act(wid,role,payment_result='Verified Stripe receipt',**({'processing_fee':'0.80'} if role=='finance' else {})).status_code==302
    with env.app.app_context():
        assert db.session.get(Receipt,rid).amount_cents==1800
        assert env.app.extensions['workflows']['financials'](env.fid)['balance']==1720
        assert db.session.scalar(db.select(db.func.count()).select_from(env.M['LedgerEntry']))==2


def test_central_lists_and_hierarchies_keep_contact_level_privacy(env):
    from app import Receipt
    with env.app.app_context():
        user=db.session.get(StaffUser,env.ids['fundraising']);user.role='fundraiser'
        parent=Contact(family_id=env.fid,name='Hidden parent identity',relationship='Sibling',phone='hidden phone')
        db.session.add(parent);db.session.flush()
        child=db.session.get(Contact,env.cid);child.parent_contact_id=parent.id;child.parent_connection='Son'
        db.session.add(env.M['SupporterLink'](contact_id=env.cid,side='Husband',relationship='Nephew',
            assigned_to=user.id,permission='Permitted',verified=True))
        db.session.add(Receipt(family_id=env.fid,contact_id=parent.id,amount_cents=1234,
            received_on=env.today,reference='HIDDEN-RECEIPT',note='Hidden private note'))
        db.session.commit();parent_id=parent.id
    client=env.client('fundraising')
    assert env.client().post(f'/supporters/{env.cid}/native-payment',data={'csrf':'test'}).status_code==400
    assert client.post(f'/supporters/{parent_id}/embedded-checkout-session',data={'csrf':'test'}).status_code==403
    for path in ['/supporters','/collections',f'/supporters/{env.cid}',f'/fundraising/{env.fid}']:
        response=client.get(path)
        assert response.status_code==200,(path,response.text)
        assert 'Hidden parent identity' not in response.text
        assert 'HIDDEN-RECEIPT' not in response.text


def test_network_preserves_shul_friend_shared_identity_and_son_in_law(env):
    with env.app.app_context():
        parent=db.session.get(Contact,env.cid)
        child=Contact(family_id=env.fid,name='Son in law',relationship='Nephew',
            phone='8455550144',parent_contact_id=parent.id,parent_connection='Son-in-law',supporter_key='phone:8455550144')
        db.session.add(child);db.session.commit();cid=child.id
    payload={'csrf':'test','contact_id':cid,'name':'Son in law','phone':'8455550144',
        'relationship':'Nephew','side':'Husband','parent_id':env.cid,'parent_connection':'Son-in-law',
        'permission':'Permitted','verified':'yes','assigned_to':env.ids['fundraising']}
    assert env.client().post(f'/families/{env.fid}/network',data=payload).status_code==302
    with env.app.app_context():
        child=db.session.get(Contact,cid)
        assert child.parent_connection=='Son-in-law' and child.parent_contact_id==env.cid
        assert child.supporter_key=='phone:8455550144'
    page=env.client().get(f'/families/{env.fid}/network?new=1')
    assert 'Shul friend' in page.text
