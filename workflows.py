"""Connected operations, independent signatures and append-only financial postings.

Money movement is recorded after an external bank/processor operation. This module
never claims that clicking an approval sends a payment or an email.
"""
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from flask import abort, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.utils import secure_filename
from workflow_catalog import CATALOG, FIELDS, ROLES, CHOICES, FINANCIAL, FUNDRAISER_KINDS
from workflow_models import workflow_models
import child_budget


def install_workflows(app, db, entities, helpers):
    Family, StaffUser, Assignment, Contact, Expense, Document, HouseholdBudget, CharityCampaign, CharityDonation = (
        entities[n] for n in ('Family','StaffUser','FamilyAssignment','Contact','Expense','Document','HouseholdBudget',
                              'CharityCampaign','CharityDonation'))
    M=workflow_models(db)
    Work=M['WorkItem']; Decision=M['WorkflowDecision']; Event=M['WorkflowEvent']; Notice=M['WorkflowNotice']
    Grant=M['WorkflowRole']; Access=M['StaffAccess']; Ledger=M['LedgerEntry']; Match=M['BankMatch']
    Policy=M['WorkflowPolicy']; Link=M['SupporterLink']; Control=M['DocumentControl']; File=M['WorkflowFile']
    current_user=helpers['current_user']; org_admin=helpers['organization_admin']; family_access=helpers['can_access_family']
    fail=lambda message: abort(400,message)
    now=lambda: datetime.now(timezone.utc)

    @app.errorhandler(IntegrityError)
    @app.errorhandler(StaleDataError)
    def workflow_conflict(exc):
        db.session.rollback()
        return render_template('error.html',title='Unable to complete request',message='This record changed or the reference already exists. Reload and review before trying again.'),409

    def active_user(user):
        status=db.session.get(Access,user.id) if user else None
        return bool(user and getattr(user, 'status', 'active') == 'active' and (not status or status.active))

    def actor():
        user=current_user()
        if not active_user(user): abort(403,'An active individual staff account is required.')
        return user

    def roles(user=None):
        user=user or current_user()
        if not active_user(user): return set()
        return set(db.session.scalars(select(Grant.role).where(Grant.user_id==user.id)))

    def scope(user,fid):
        return user.role=='organization_admin' or bool(fid and db.session.scalar(select(Assignment.id).where(
            Assignment.staff_user_id==user.id,Assignment.family_id==fid)))

    def status(item):
        if item.disposition not in ('Open','Complete'): return item.disposition
        return CATALOG[item.kind]['steps'][item.stage][0]

    def readable(item,user=None):
        user=user or current_user()
        if not active_user(user): return False
        r=roles(user); spec=CATALOG[item.kind]
        if spec.get('restricted') and user.id not in (item.owner_id,item.created_by) and not r.intersection({'compliance','executive'} | ({'finance'} if item.kind=='unusual' else set())): return False
        if item.kind=='document' and item.data.get('document_privacy') in ('Medical','Finance','Restricted'):
            needed={'Medical':{'medical'},'Finance':{'finance','auditor'},'Restricted':{'compliance','executive'}}[item.data['document_privacy']]
            if not r.intersection(needed):return False
        if item.family_id:
            if not scope(user,item.family_id): return False
        elif item.kind!='vendor' and user.role!='organization_admin' and not r.intersection({'finance','executive','board','compliance','auditor','verifier','payment_approver','payment_releaser','rabbi'}):
            return False
        if item.data.get('snapshot') and any(not scope(user,int(fid)) for fid in item.data['snapshot']):return False
        if item.kind=='payment_batch' and item.data.get('batch_items'):
            try: batch_ids=[int(x.strip()) for x in item.data['batch_items'].split(',')]
            except ValueError:return user.id==item.owner_id
            for wid in batch_ids:
                expense=db.session.get(Work,wid)
                if expense and not scope(user,expense.family_id):return False
        if user.role=='office_employee' and item.kind not in {'referral','intake','verification','assessment','case_approval','support_plan','review','task','document','expense'}: return False
        if user.role=='fundraiser':
            if item.kind not in FUNDRAISER_KINDS or item.owner_id!=user.id: return False
            contact=db.session.get(Link,item.data.get('contact_id'))
            return bool(contact and contact.assigned_to==user.id)
        return True

    def get_item(item_id,lock=False):
        item=db.session.scalar(select(Work).where(Work.id==item_id).with_for_update()) if lock else db.session.get(Work,item_id)
        if not item: abort(404)
        if not readable(item): abort(403,'You do not have permission for this action.')
        return item

    def emit(item,action,detail=None):
        db.session.add(Event(item_id=item.id if item else None,family_id=item.family_id if item else None,
            actor_id=actor().id,action=action,detail=detail or {}))

    def notify(item,message):
        ids={item.owner_id}
        role=CATALOG[item.kind]['steps'][item.stage][1]
        for user in db.session.scalars(select(StaffUser).join(Grant,Grant.user_id==StaffUser.id).where(Grant.role==role)):
            if readable(item,user): ids.add(user.id)
        if item.data.get('escalation_user'): ids.add(item.data['escalation_user'])
        for uid in ids:
            user=db.session.get(StaffUser,uid)
            if user and readable(item,user): db.session.add(Notice(item_id=item.id,user_id=uid,message=message))

    def save():
        try: db.session.commit()
        except (IntegrityError,StaleDataError):
            db.session.rollback()
            abort(409,'This record changed or the reference already exists. Reload and review before trying again.')

    def field(key,required=True,limit=5000):
        value=request.form.get(key,'').strip()
        if len(value)>limit or (required and not value): fail('Complete the required fields.')
        return value

    def money(value,signed=False):
        try:
            n=Decimal(value)
            if not n.is_finite() or n.as_tuple().exponent < -2 or abs(n)>1000000 or (not signed and n<0): raise ValueError()
            return int(n*100)
        except (InvalidOperation,ValueError): fail('Enter a valid amount with up to two decimal places, no greater than $1,000,000.')

    def parse_data(kind):
        data={}
        for key in CATALOG[kind]['fields']:
            typ,label,required=FIELDS[key]; raw=request.form.get(key,'').strip()
            if typ=='check': data[key]=raw=='yes';continue
            if not raw: data[key]=None;continue
            if typ in ('money','signed_money'): value=money(raw,typ=='signed_money')
            elif typ in ('integer','item','family','user','contact','document'):
                try: value=int(raw);assert value>0
                except (ValueError,AssertionError): fail('Choose a valid linked record.')
            elif typ in ('date','month'):
                try: value=date.fromisoformat(raw+('-01' if typ=='month' else '')).isoformat()[:7 if typ=='month' else 10]
                except ValueError: fail('Enter a valid date.')
            else:
                if len(raw)>5000: fail('The text is too long.')
                value=raw
            if typ=='choice' and value not in CHOICES[key]: fail('Choose a valid option.')
            data[key]=value
        return data

    def check_links(item):
        for key in CATALOG[item.kind]['fields']:
            value=item.data.get(key);typ=FIELDS[key][0]
            if not value: continue
            if typ=='item':
                linked=db.session.get(Work,value)
                if not linked or linked.id==item.id or not readable(linked): fail('Choose a valid linked record.')
                if linked.family_id!=item.family_id and key not in ('vendor_id',): fail('The linked record belongs to another case.')
                expected={'assessment_id':'assessment','case_approval_id':'case_approval','plan_id':'support_plan','vendor_id':'vendor'}.get(key)
                if expected and (linked.kind!=expected or linked.disposition!='Complete'): fail('The required linked workflow is not approved.')
            elif typ=='family':
                if value==item.family_id or not scope(actor(),value) or not db.session.get(Family,value): fail('Choose a valid linked record.')
            elif typ=='user':
                user=db.session.get(StaffUser,value)
                if not user or (not active_user(user) and not (key=='user_id' and item.kind in ('onboarding','access_change'))) or (item.family_id and not scope(user,item.family_id)): fail('Choose assigned active staff.')
            elif typ=='contact':
                c=db.session.get(Contact,value)
                if not c or c.family_id!=item.family_id: fail('The linked record belongs to another case.')
                link=db.session.get(Link,value)
                if actor().role=='fundraiser' and (not link or link.assigned_to!=actor().id): abort(403)
            elif typ=='document':
                doc=db.session.get(Document,value)
                if not doc or doc.family_id!=item.family_id: fail('The linked record belongs to another case.')
                document_access(doc)
        if item.kind=='task' and item.data.get('dependency_id'):
            cursor=db.session.get(Work,item.data['dependency_id']); seen={item.id}
            while cursor:
                if cursor.id in seen: fail('Dependencies cannot contain a cycle.')
                seen.add(cursor.id);cursor=db.session.get(Work,cursor.data.get('dependency_id')) if cursor.data.get('dependency_id') else None

    def complete_fields(item):
        for key in CATALOG[item.kind]['fields']:
            if FIELDS[key][2] and (item.data.get(key) is None or item.data.get(key)=='' or (FIELDS[key][0]=='check' and not item.data.get(key))):
                from translations import translate
                fail(translate('Complete the required fields.')+' '+translate(FIELDS[key][1]))
        check_links(item)
        if any(len(item.data.get(key) or '')>180 for key in ('reference','bank_ref')):fail('Use a reference no longer than 180 characters.')
        if item.data.get('end') and item.data.get('start') and item.data['end']<item.data['start']: fail('End date must follow the start date.')
        if item.kind in ('assessment','support_plan') and item.data['review_date']>item.data['end']: fail('Review date must be within the support period.')
        if item.kind=='access_change' and item.data['access_change']=='Role change' and not item.data.get('new_role'):fail('Choose the new access role.')
        if item.kind in ('expense','pledge','collection','refund','transfer','emergency') and item.data.get('amount',0)<=0: fail('Amount must be greater than zero.')
        if CATALOG[item.kind].get('evidence') and not evidence(item): fail('Attach supporting evidence before continuing.')

    def evidence(item,purpose=None,min_stage=None):
        if purpose:
            q=select(File.id).where(File.item_id==item.id,File.purpose==purpose,File.revision==item.revision)
            if min_stage is not None:q=q.where(File.stage>=min_stage)
            return bool(db.session.scalar(q.limit(1)))
        return bool(db.session.scalar(select(File.id).where(File.item_id==item.id).limit(1)) or
                    db.session.scalar(select(M['WorkflowEvidence'].id).where(M['WorkflowEvidence'].item_id==item.id).limit(1)))

    def approved(kind,fid):
        return db.session.scalar(select(Work).where(Work.kind==kind,Work.family_id==fid,Work.disposition=='Complete').order_by(Work.id.desc()))

    def pending(kind,fid):
        return db.session.scalar(select(Work).where(Work.kind==kind,Work.family_id==fid,Work.disposition=='Open',Work.stage>0).order_by(Work.id.desc()))

    def fingerprint(family):
        record=db.session.get(HouseholdBudget,family.id)
        data={'budget':record.data if record else {},'intake':family.intake_record.data if family.intake_record else {},
              'children':[(c.id,c.name,c.age,c.school) for c in sorted(family.children,key=lambda c:c.id)]}
        return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

    def financials(fid):
        entries=db.session.scalars(select(Ledger).where(Ledger.family_id==fid)).all()
        posted_sources={e.source_item_id for e in entries}
        posted_imports=set()
        for item in db.session.scalars(select(Work).where(Work.family_id==fid,Work.kind=='collection')):
            donation_id=item.data.get('abcharity_donation_id')
            if donation_id and item.id in posted_sources:posted_imports.add(donation_id)
        campaign_ids=list(db.session.scalars(select(CharityCampaign.id).where(
            CharityCampaign.family_id==fid,CharityCampaign.currency=='USD')))
        imported=[d for d in db.session.scalars(select(CharityDonation).where(
            CharityDonation.campaign_id.in_(campaign_ids))) if d.id not in posted_imports] if campaign_ids else []
        imported_gross=sum(d.amount_cents for d in imported)
        imported_net=sum(d.net_cents for d in imported)
        balance=sum(e.amount_cents for e in entries)+imported_net
        reserved=0
        for item in db.session.scalars(select(Work).where(Work.family_id==fid,Work.kind.in_(['expense','emergency']),Work.disposition=='Open')):
            if (item.kind=='expense' and item.stage>=4) or (item.kind=='emergency' and item.stage>=4):
                if not any(e.source_item_id==item.id for e in entries): reserved+=item.data.get('amount',0)
        plan=approved('support_plan',fid)
        assessment=approved_assessment(plan) if plan else None
        family=db.session.get(Family,fid)
        protected=min(max(balance-reserved,0),assessment.data.get('reserve',0)) if assessment and family.status in ('Active','Paused') else 0
        held=False
        consistency=app.extensions.get('workflows',{}).get('import_consistent')
        if consistency:
            for w in db.session.scalars(select(Work).where(Work.family_id==fid,Work.kind=='collection')):
                if w.data.get('abcharity_donation_id') and any(e.source_item_id==w.id for e in entries) and not consistency(w):held=True
        return dict(balance=balance,reserved=reserved,protected_reserve=protected,held_for_review=held,available=0 if held else balance-reserved-protected,
                    collected=sum(e.amount_cents for e in entries if e.entry_type in ('Donation','Donation adjustment'))+imported_gross,
                    assistance=-sum(e.amount_cents for e in entries if e.entry_type=='Family assistance'),
                    overhead=-sum(e.amount_cents for e in entries if e.entry_type in ('Organization expense','Processing fee','Processing fee adjustment'))+(imported_gross-imported_net),
                    refunds=-sum(e.amount_cents for e in entries if e.entry_type=='Refund'),
                    imported_pending=len(imported),imported_pending_gross=imported_gross,imported_pending_net=imported_net,
                    unmatched=sum(1 for e in entries if e.entry_type not in ('Transfer in','Transfer out') and not db.session.scalar(select(Match.id).where(Match.ledger_id==e.id))))

    def report_snapshot(fid,period):
        totals=financials(fid)
        entries=[e for e in db.session.scalars(select(Ledger).where(Ledger.family_id==fid)) if e.at.strftime('%Y-%m')==period]
        totals['period_collected']=sum(e.amount_cents for e in entries if e.entry_type in ('Donation','Donation adjustment'))
        totals['period_assistance']=-sum(e.amount_cents for e in entries if e.entry_type=='Family assistance')
        totals['period_overhead']=-sum(e.amount_cents for e in entries if e.entry_type in ('Organization expense','Processing fee','Processing fee adjustment'))
        return totals

    def lock_family(fid):
        return db.session.scalar(select(Family).where(Family.id==fid).with_for_update()) if fid else None

    def policy():
        p=db.session.scalar(select(Policy).order_by(Policy.id.desc()))
        return p.data if p else {}

    def enforced():
        return not app.config['DEMO'] and bool(app.config.get('WORKFLOW_ENFORCEMENT') or policy())

    def conflict(item,uid):
        for c in db.session.scalars(select(Work).where(Work.kind=='conflict',Work.family_id==item.family_id,Work.disposition.notin_(['Rejected','Canceled']))):
            if c.data.get('conflict_user')==uid: return True
        return False

    def required_role(item):
        return CATALOG[item.kind]['steps'][item.stage][1]

    def can_sign(item):
        user=current_user()
        if not user or not readable(item) or item.disposition!='Open': return False
        role=required_role(item)
        if 'auditor' in roles() and len(roles())==1 and role!='auditor': return False
        if role=='owner': return item.owner_id==user.id
        if role not in roles() or conflict(item,user.id): return False
        if item.created_by==user.id or item.data.get('_submitted_by')==user.id: return False
        decisions=db.session.scalars(select(Decision).where(Decision.item_id==item.id,Decision.revision==item.revision,Decision.action=='Approve')).all()
        if any(d.actor_id==user.id and d.stage==item.stage for d in decisions): return False
        if item.kind in FINANCIAL or item.kind=='case_approval':
            if any(d.actor_id==user.id and d.role!=role for d in decisions): return False
        return True

    def approved_assessment(item):
        if item.kind=='assessment': return item
        if item.kind=='case_approval': return db.session.get(Work,item.data.get('assessment_id'))
        if item.kind=='support_plan':
            case=db.session.get(Work,item.data.get('case_approval_id'))
            return db.session.get(Work,case.data.get('assessment_id')) if case else None
        plan=db.session.get(Work,item.data.get('plan_id')) if item.data.get('plan_id') else approved('support_plan',item.family_id)
        return approved_assessment(plan) if plan else None

    def check_budget(item,exclude_self=True):
        family=lock_family(item.family_id)
        if app.extensions['workflows'].get('check_import_case'):app.extensions['workflows']['check_import_case'](item.family_id)
        if family.status!='Active': fail('Only active cases can have expenses approved or paid.')
        plan=db.session.get(Work,item.data.get('plan_id'))
        if not plan or plan.kind!='support_plan' or plan.disposition!='Complete': fail('The required linked workflow is not approved.')
        month=item.data['month'];start=plan.data['start'];end=plan.data['end']
        if not (start[:7]<=month<=end[:7]) or not start<=date.today().isoformat()<=end: fail('The approved support period has ended.')
        review=approved('review',item.family_id)
        review_date=review.data['review_date'] if review and review.data.get('plan_id')==plan.id and review.id>plan.id else plan.data['review_date']
        overdue_review=db.session.scalar(select(Work.id).where(Work.family_id==item.family_id,Work.kind=='review',Work.disposition=='Open',Work.due<date.today()))
        if (review_date<date.today().isoformat() or overdue_review) and not item.data.get('essential'): fail('Complete the overdue case review first.')
        for hold in db.session.scalars(select(Work).where(Work.family_id==item.family_id,Work.kind=='unusual',Work.disposition=='Open')):
            if hold.data.get('source_id')==item.id: fail('This payment is held for compliance review.')
        assessment=approved_assessment(plan)
        if not assessment: fail('The required linked workflow is not approved.')
        limit=assessment.data.get('support_limit',0) if item.data['expense_type']=='Family assistance' else assessment.data['org_cost']+assessment.data['fees']
        other=db.session.scalars(select(Work).where(Work.family_id==item.family_id,Work.kind=='expense',Work.id!=item.id,Work.disposition.notin_(['Rejected','Canceled']))).all()
        used=sum(x.data.get('amount',0) for x in other if x.stage>=4 and x.data.get('month')==month and x.data.get('expense_type')==item.data['expense_type'])
        duplicate=any(x.data.get('vendor_id')==item.data['vendor_id'] and x.data.get('invoice','').strip().casefold()==item.data['invoice'].strip().casefold() for x in other)
        if duplicate: fail('This invoice is already recorded for the vendor and case.')
        p=policy()
        if not p or p.get('review_date','')<date.today().isoformat(): fail('Approve organization policies and limits first.')
        approved_categories={v.strip().casefold() for v in assessment.data.get('approved_categories','').split(',')}
        needs_exception=(item.data['category'].strip().casefold() not in approved_categories or used+item.data['amount']>limit or item.data.get('related_party') or item.data.get('direct_family') or item.data.get('cash') or item.data['amount']>p['large_limit'])
        exceptions=db.session.scalars(select(Work).where(Work.kind=='exception_approval',Work.family_id==item.family_id,Work.disposition=='Complete')).all()
        if needs_exception and not any(x.data.get('source_id')==item.id and x.data.get('source_revision')==item.revision for x in exceptions):
            fail('Complete the expense exception approvals first.')
        if item.data['expense_type']=='Organization expense':
            allocations=db.session.scalars(select(Work).where(Work.kind=='allocation',Work.family_id==item.family_id,Work.disposition=='Complete')).all()
            if not any(x.data.get('source_id')==item.id and x.data.get('amount')==item.data['amount'] and x.data.get('source_revision')==item.revision for x in allocations): fail('Approve the organization-expense allocation first.')
        available=financials(item.family_id)['available']
        if item.stage>=4 and not db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==item.id)):
            available+=item.data['amount']
        if item.data['amount']>available: fail('The case does not have enough collected, available funds.')

    def external_details(item):
        data=dict(item.data)
        for key in ('payment_result','reference','receipt','bank_ref','bank_date'):
            raw=request.form.get(key,'').strip()
            if raw:
                if key in ('reference','bank_ref') and len(raw)>180:fail('Use a reference no longer than 180 characters.')
                if len(raw)>2000: fail('The text is too long.')
                if key=='bank_date':
                    try: date.fromisoformat(raw)
                    except ValueError: fail('Enter a valid date.')
                if key=='reference' and data.get(key) and data[key]!=raw: fail('Submitted references cannot be replaced.')
                data[key]=raw
        fee=request.form.get('processing_fee','').strip()
        if fee and item.kind=='collection':
            parsed=money(fee)
            if item.stage not in (2,3) or parsed>data['amount']:fail('Record processing fees during finance review before posting.')
            if data.get('abcharity_donation_id') and parsed!=data.get('processing_fee',0):fail('The imported receipt changed. Review the original before continuing.')
            data['processing_fee']=parsed
        item.data=data

    def post_ledger(item,entry_type,amount,fid=None,external=True):
        reference=item.data.get('reference') if external else None
        if external and not reference: fail('Record the external transaction reference.')
        db.session.add(Ledger(family_id=fid or item.family_id,source_item_id=item.id,entry_type=entry_type,
            amount_cents=amount,external_reference=reference,actor_id=actor().id))
        emit(item,'Ledger posted',{'entry_type':entry_type,'amount_cents':amount,'family_id':fid or item.family_id})

    def check_reconciliation(item):
        entry=db.session.get(Ledger,item.data.get('ledger_id'))
        if not entry or entry.family_id!=item.family_id: fail('Choose a valid linked record.')
        source=db.session.get(Work,entry.source_item_id)
        expected=entry.amount_cents-source.data.get('processing_fee',0) if entry.entry_type=='Donation' else entry.amount_cents
        if expected!=item.data['bank_amount']: fail('The bank amount does not match the ledger entry.')
        if db.session.scalar(select(Match.id).where(Match.ledger_id==entry.id)): fail('This ledger entry is already reconciled.')
        return entry

    def stage_gate(item,next_label):
        complete_fields(item)
        if item.kind=='transfer':
            for fid in sorted([item.family_id,item.data['target_family']]):lock_family(fid)
        family=lock_family(item.family_id)
        if family and family.status=='Closed' and item.kind not in ('reopening','assessment','verification','case_report','task','document','complaint','conflict','donor_service','refund','transfer','reconciliation'):
            fail('Reopen the case before starting new operations.')
        if item.kind in ('outreach','pledge'):
            link=db.session.get(Link,item.data['contact_id'])
            if not link or not link.verified or link.permission!='Permitted' or not link.assigned_to: fail('Verify the relationship, contact permission and fundraiser assignment first.')
            if family.status!='Active' or not approved('fundraising_plan',item.family_id) or pending('closure',item.family_id): fail('An active, approved fundraising plan is required.')
        if item.stage==0:
            if item.kind=='intake' and not approved('referral',item.family_id): fail('Complete the referral and consent workflow first.')
            if item.kind=='verification':
                if not approved('intake',item.family_id): fail('Complete the intake review first.')
                item.data={**item.data,'fingerprint':fingerprint(family)}
            if item.kind=='assessment':
                verification=approved('verification',item.family_id)
                if not verification or verification.data.get('fingerprint')!=fingerprint(family): fail('Complete information verification first.')
                budget=db.session.get(HouseholdBudget,item.family_id)
                report=child_budget.calculate(budget.data if budget else {},family.intake_record.data if family.intake_record else {},family.children)
                if report['missing']: fail('Complete the household budget before approval.')
                if item.data['support_limit']>max(0,report['gap']-item.data['family_contribution']):fail('The assistance limit exceeds the remaining household need.')
                item.data={**item.data,'gap':report['gap'],'costs':report['costs'],'income':report['earnings'],'assistance':report['usable_help'],
                           'goal':item.data['support_limit']+item.data['org_cost']+item.data['fees']+item.data['reserve'],
                           'fingerprint':fingerprint(family)}
            if item.kind in ('exception_approval','allocation'):
                source=db.session.get(Work,item.data['source_id'])
                if source.kind!='expense': fail('Choose an expense request.')
                item.data={**item.data,'source_revision':source.revision}
            if item.kind=='fundraising_plan':
                assessment=approved_assessment(item)
                if not assessment or item.data['monthly_goal']!=assessment.data['goal']: fail('The fundraising goal must match the approved needs assessment.')
            if item.kind=='conflict': emit(item,'Conflict disclosed',{'user_id':item.data['conflict_user']})
            if item.kind=='access_change' and item.data['access_change']=='Deactivate': deactivate(item)
            if item.kind=='document':
                control=db.session.get(Control,item.data['document_id']) or Control(document_id=item.data['document_id'])
                requested=item.data['document_privacy']
                if control.privacy and control.privacy!=requested and control.privacy!='Household':
                    if requested!='Household':control.privacy='Restricted'
                else:control.privacy=requested
                db.session.add(control)
            if item.kind in ('case_report','org_report'):
                ids=[item.family_id] if item.family_id else [fid for fid in db.session.scalars(select(Family.id)) if scope(actor(),fid)]
                if any(financials(fid)['unmatched'] for fid in ids): fail('Reconcile outstanding bank entries before finalizing a financial report.')
                item.data={**item.data,'snapshot':{str(fid):report_snapshot(fid,item.data['period']) for fid in ids}}
        if item.kind in ('case_approval','support_plan') and next_label in ('Approved','Active'):
            assessment=approved_assessment(item)
            if not assessment or assessment.data.get('fingerprint')!=fingerprint(family): fail('The household budget changed. Submit a new needs assessment.')
        if item.kind=='payment_batch':
            batch_expenses(item, next_label=='Completed')
        if item.kind=='review' and next_label=='Completed' and item.data['review_date']<=date.today().isoformat():fail('Set a future review date.')
        if item.kind=='verification' and next_label=='Completed':
            if item.data.get('fingerprint')!=fingerprint(family):fail('The household information changed. Return the verification for review.')
            incomplete=any(item.data.get(k) not in ('Verified','Not applicable') for k in CATALOG['verification']['fields'] if k.startswith('verify_'))
            if incomplete and not item.data.get('exceptions'):fail('Document unresolved verification findings before approval.')
        if item.kind=='task' and next_label=='Completed' and item.data.get('dependency_id'):
            if db.session.get(Work,item.data['dependency_id']).disposition!='Complete': fail('Complete the dependent workflow first.')
        if item.kind=='supporter' and next_label=='Ready for outreach':
            link=db.session.get(Link,item.data['contact_id'])
            if not link or not link.verified or link.permission!='Permitted' or not link.assigned_to: fail('Verify the relationship, contact permission and fundraiser assignment first.')
        if item.kind=='pledge' and next_label=='Active':
            contact=db.session.get(Contact,item.data['contact_id'])
            for other in db.session.scalars(select(Work).where(
                    Work.kind=='pledge', Work.disposition=='Complete', Work.id!=item.id,
                    Work.family_id==item.family_id)):
                oc=db.session.get(Contact,other.data.get('contact_id'))
                end=other.data.get('end') or ''
                if end and end<date.today().isoformat():continue
                if oc and oc.id==contact.id:fail('Pause the previous pledge before confirming a replacement.')
        if item.kind=='closure' and next_label=='Closed' and 'StripePayment' in entities:
            payment=entities['StripePayment']
            if db.session.scalar(select(payment.id).join(Contact,Contact.id==payment.contact_id).where(
                Contact.family_id==item.family_id,payment.frequency!='One time',payment.status.in_(['pending','creating','incomplete','trialing','active','past_due','unpaid']))):
                fail('Stop the active Stripe subscription before closing this case.')
        if item.kind=='expense' and next_label in ('Approved','Scheduled','Payment release','Paid'): check_budget(item)
        if item.kind in ('expense','emergency','refund') and next_label in ('Paid','Documentation review','Completed'):
            if item.kind=='refund' and item.stage!=3: return
            if item.kind=='emergency' and next_label=='Completed': return
            if not item.data.get('payment_result') or not item.data.get('reference') or not evidence(item,'Payment proof',{'expense':6,'emergency':4,'refund':3}[item.kind]): fail('Attach payment proof and record the external payment result and reference.')
        if item.kind=='unusual' and app.extensions['workflows'].get('import_correction'):
            app.extensions['workflows']['import_correction'](item,next_label,False)
        if item.kind=='collection' and not app.extensions['workflows'].get('import_consistent',lambda w:True)(item):fail('The imported receipt changed. Review the original before continuing.')
        if item.kind=='expense' and next_label=='Paid' and item.data.get('cash') and not evidence(item,'Signed receipt',6):fail('Attach the signed cash receipt.')
        if item.kind=='collection' and next_label in ('Collected','Posted'):
            if not item.data.get('payment_result'): fail('Record the confirmed bank or processor result before posting funds.')
        if item.kind=='collection' and next_label=='Receipt issued' and not item.data.get('receipt'): fail('Record the issued receipt number.')
        if item.kind in ('collection','expense') and next_label=='Reconciled':
            entry=db.session.scalar(select(Ledger).where(Ledger.source_item_id==item.id))
            if not entry or not db.session.scalar(select(Match.id).where(Match.ledger_id==entry.id)): fail('Match the bank transaction in the reconciliation workflow first.')
        if item.kind=='reconciliation': check_reconciliation(item)
        if item.kind in ('refund','transfer','emergency') and next_label in ('Release recorded','Immediate payment','Documentation review','Transfer posted','Completed'):
            if db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==item.id)): return
            totals=financials(item.family_id)
            spendable=totals['available']+(totals['protected_reserve'] if item.kind=='emergency' else 0)
            if item.kind=='emergency' and item.stage>=4:spendable+=item.data['amount']
            if item.data['amount']>spendable: fail('The case does not have enough collected, available funds.')
            if item.kind=='refund':
                source=db.session.get(Work,item.data['source_id'])
                original=db.session.scalar(select(Ledger).where(Ledger.source_item_id==source.id,Ledger.entry_type=='Donation'))
                if not original: fail('Choose a posted donation.')
                prior=db.session.scalars(select(Work).where(Work.kind=='refund',Work.family_id==item.family_id,Work.id!=item.id)).all()
                spent=sum(x.data['amount'] for x in prior if x.data.get('source_id')==source.id and db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==x.id)))
                ceiling=app.extensions['workflows'].get('import_baseline',lambda w:(original.amount_cents,0))(source)[0] if source.data.get('abcharity_donation_id') else original.amount_cents
                if spent+item.data['amount']>ceiling: fail('Refunds cannot exceed the original collected donation.')

        if item.kind=='closure' and next_label=='Closed':
            totals=financials(item.family_id)
            if totals['balance']!=0 or totals['unmatched'] or totals['reserved']: fail('Resolve the case balance, bank reconciliation and unpaid obligations before closing.')
            old=db.session.scalar(select(Expense.id).where(Expense.family_id==item.family_id,Expense.status.in_(['Requested','Approved'])))
            if old: fail('Resolve outstanding expense requests before closing.')
            others=db.session.scalars(select(Work).where(Work.family_id==item.family_id,Work.id!=item.id,Work.kind.in_(['expense','emergency','collection','pledge']))).all()
            if any(x.disposition=='Open' or (x.kind=='pledge' and x.disposition=='Complete') for x in others): fail('Stop recurring pledges and resolve pending financial workflows before closing.')
        if item.kind=='reopening' and family.status!='Closed': fail('Only a closed case can enter reopening review.')

    def batch_expenses(item, release=False):
        try: ids=[int(v.strip()) for v in item.data['batch_items'].split(',')]
        except (ValueError,KeyError): fail('Enter valid expense workflow numbers.')
        if not ids or len(ids)!=len(set(ids)) or len(ids)>100: fail('Enter valid expense workflow numbers.')
        result=[]
        for wid in sorted(ids):
            w=db.session.scalar(select(Work).where(Work.id==wid).with_for_update())
            if not w or w.kind!='expense' or not readable(w) or w.disposition!='Open' or w.stage!=4:
                fail('Batch payments must contain approved, unpaid expenses.')
            if (release or required_role(item) in ('payment_approver','payment_releaser')) and actor().id in (w.created_by,w.data.get('_submitted_by')): fail('The payment releaser cannot be the expense submitter.')
            if release:
                signed=list(db.session.scalars(select(Decision.actor_id).where(Decision.item_id==w.id,Decision.revision==w.revision)))
                if actor().id in signed: fail('The payment releaser cannot be an expense approver.')
                if not item.data.get('payment_result') or not evidence(item,'Payment proof',3): fail('Record the confirmed external batch result.')
            if release and w.data.get('cash') and not evidence(item,'Signed receipt',3):fail('Attach the signed cash receipt.')
            check_budget(w);result.append(w)
        return result

    def monthly_pledged(fid=None,user=None,family_ids=None):
        today=date.today().isoformat();totals={}
        query=select(Work).where(Work.kind=='pledge',Work.disposition=='Complete')
        if fid is not None:query=query.where(Work.family_id==fid)
        if family_ids is not None:query=query.where(Work.family_id.in_(family_ids))
        for w in db.session.scalars(query.order_by(Work.id)):
            frequency=w.data.get('frequency')
            if frequency not in ('Monthly','Weekly'):continue
            start=w.data.get('start') or ''
            end=w.data.get('end') or ''
            if start and today<start:continue
            if end and today>end:continue
            link=db.session.get(Link,w.data.get('contact_id'))
            if user and user.role=='fundraiser' and (not link or link.assigned_to!=user.id):continue
            contact=db.session.get(Contact,w.data.get('contact_id'))
            if not contact or contact.family_id!=w.family_id:continue
            identity=(w.family_id,contact.id)
            amount=w.data.get('amount',0)
            if frequency=='Weekly':amount=round(amount*52/12)
            totals[identity]=amount
        return sum(totals.values())

    def deactivate(item):
        uid=item.data['user_id'];user=db.session.get(StaffUser,uid)
        if user.email==app.config.get('ADMIN_EMAIL','').lower() or uid==actor().id: fail('The owner or current account cannot be deactivated here.')
        access=db.session.get(Access,uid) or Access(user_id=uid);access.active=False;db.session.add(access)
        emit(item,'Access deactivated',{'user_id':uid})

    def schedule_review(source,plan_id,due):
        existing=list(db.session.scalars(select(Work).where(Work.kind=='review',Work.family_id==source.family_id,Work.disposition=='Open')))
        if any(w.data.get('plan_id')==plan_id and w.id!=source.id for w in existing):return
        from datetime import timedelta
        due=min(date.fromisoformat(due),date.today()+timedelta(days=30)).isoformat()
        w=Work(kind='review',family_id=source.family_id,title='Case review and renewal',owner_id=source.owner_id,
               created_by=source.owner_id,due=date.fromisoformat(due),data={'plan_id':plan_id},priority='Normal')
        db.session.add(w);db.session.flush();emit(w,'New assignment',{'source_id':source.id});notify(w,'New assignment')

    def effects(item,next_label):
        data=item.data;family=db.session.get(Family,item.family_id) if item.family_id else None
        if item.kind=='unusual' and next_label=='Completed' and app.extensions['workflows'].get('import_correction'):
            app.extensions['workflows']['import_correction'](item,next_label,True)
        if item.kind=='governance' and next_label=='Approved': db.session.add(Policy(data=dict(data),source_item_id=item.id))
        if item.kind=='case_approval' and next_label=='Approved': family.status='Under review'
        if item.kind=='support_plan' and next_label=='Active':
            family.status='Active'
            schedule_review(item,item.id,data['review_date'])
        if item.kind=='review' and next_label=='Completed':
            if data['review_decision']=='Pause assistance':family.status='Paused'
            elif data['review_decision']=='Continue unchanged':family.status='Active'
            elif data['review_decision'] in ('Begin closure','Reassess assistance','Request documents'):
                kind={'Begin closure':'closure','Reassess assistance':'verification','Request documents':'task'}[data['review_decision']]
                follow=Work(kind=kind,family_id=item.family_id,title=CATALOG[kind]['title'],owner_id=item.owner_id,created_by=item.owner_id,due=date.today(),data={'reason':data['resolution'],'summary':data['summary']})
                db.session.add(follow);db.session.flush();emit(follow,'New assignment',{'review_id':item.id});notify(follow,'New assignment')
            elif data['review_decision']=='Pause fundraising':
                for fp in db.session.scalars(select(Work).where(Work.family_id==item.family_id,Work.kind=='fundraising_plan',Work.disposition=='Complete')):
                    fp.disposition='Paused';emit(fp,'Pause',{'review_id':item.id})
            plan=db.session.get(Work,data['plan_id'])
            if data['review_date']>date.today().isoformat() and data['review_date']<=plan.data['end']:
                schedule_review(item,plan.id,data['review_date'])
        if item.kind=='closure' and next_label=='Closed':
            family.status='Closed'
            for review in db.session.scalars(select(Work).where(Work.kind=='review',Work.family_id==item.family_id,Work.disposition=='Open')):
                review.disposition='Canceled';emit(review,'Canceled',{'closure_id':item.id})
        if item.kind=='reopening' and next_label=='Reopened': family.status='Under review'
        if item.kind=='pledge' and next_label=='Active':
            contact=db.session.get(Contact,data['contact_id']);contact.status='Pledged';contact.monthly_cents=data['amount'];contact.pledge_frequency='One time' if data['frequency']=='One-time' else data['frequency']
        if item.kind=='payment_batch' and next_label=='Completed':
            for w in batch_expenses(item,True):
                w.data={**w.data,'reference':data['reference']+':'+str(w.id),'payment_result':data['payment_result'],'batch_id':item.id}
                post_ledger(w,w.data['expense_type'],-w.data['amount']);w.stage=7
                if w.data.get('expense_id'):
                    e=db.session.get(Expense,w.data['expense_id']);e.status='Paid';e.payment_reference=w.data['reference']
                emit(w,'Batch payment recorded',{'batch_id':item.id})
        if item.kind=='collection' and next_label=='Posted':
            post_ledger(item,'Donation',data['amount'])
            if data.get('processing_fee'):post_ledger(item,'Processing fee',-data['processing_fee'],external=False)
        if item.kind=='expense' and next_label=='Paid':
            post_ledger(item,data['expense_type'],-data['amount'])
            if data.get('expense_id'):
                e=db.session.get(Expense,data['expense_id']);e.status='Paid';e.payment_reference=data['reference']
        if item.kind=='expense' and next_label=='Approved' and data.get('expense_id'):
            db.session.get(Expense,data['expense_id']).status='Approved'
        if item.kind=='emergency' and next_label=='Documentation review':
            post_ledger(item,'Family assistance',-data['amount']);item.due=date.fromisoformat(data['deadline'])
        if item.kind=='refund' and next_label=='Completed': post_ledger(item,'Refund',-data['amount'])
        if item.kind=='transfer' and next_label=='Completed':
            lock_family(data['target_family'])
            post_ledger(item,'Transfer out',-data['amount']);post_ledger(item,'Transfer in',data['amount'],data['target_family'],False)
        if item.kind=='reconciliation' and next_label=='Reconciled':
            entry=check_reconciliation(item)
            db.session.add(Match(ledger_id=entry.id,bank_reference=data['bank_ref'],statement_date=date.fromisoformat(data['bank_date']),actor_id=actor().id))
            fee=db.session.scalar(select(Ledger).where(Ledger.source_item_id==entry.source_item_id,Ledger.entry_type=='Processing fee')) if entry.entry_type=='Donation' else None
            if fee:db.session.add(Match(ledger_id=fee.id,bank_reference=data['bank_ref']+':fee',statement_date=date.fromisoformat(data['bank_date']),actor_id=actor().id))
        if item.kind=='access_change' and next_label=='Completed':
            target=db.session.get(StaffUser,data['handover'])
            if target.id==data['user_id']: fail('Choose a different staff member for handover.')
            for a in db.session.scalars(select(Assignment).where(Assignment.staff_user_id==data['user_id'])):
                if not scope(target,a.family_id):db.session.add(Assignment(staff_user_id=target.id,family_id=a.family_id))
                db.session.delete(a)
            for w in db.session.scalars(select(Work).where(Work.owner_id==data['user_id'],Work.disposition=='Open')):
                w.owner_id=target.id
            for link in db.session.scalars(select(Link).where(Link.assigned_to==data['user_id'])):link.assigned_to=target.id
            db.session.execute(db.delete(Grant).where(Grant.user_id==data['user_id']))
            if data['access_change']=='Role change':
                target_user=db.session.get(StaffUser,data['user_id'])
                if target_user.email==app.config.get('ADMIN_EMAIL','').lower() and data['new_role']!='organization_admin':fail('The owner organization administrator cannot be demoted.')
                target_user.role=data['new_role']
        if item.kind=='document' and next_label=='Approved':
            control=db.session.get(Control,data['document_id']);control.privacy=data['document_privacy'];control.category=data['document_category'];control.previous_id=data.get('previous_document')
            if control.previous_id:
                prev=db.session.get(Control,control.previous_id) or Control(document_id=control.previous_id,privacy=control.privacy)
                prev.archived=True;db.session.add(prev)
        if item.kind=='onboarding' and next_label=='Completed':
            access=db.session.get(Access,data['user_id']) or Access(user_id=data['user_id']);access.active=True;db.session.add(access)

    def choices_for(item):
        users=[u for u in db.session.scalars(select(StaffUser).order_by(StaffUser.email)) if active_user(u) and (not item.family_id or scope(u,item.family_id))]
        contacts=db.session.scalars(select(Contact).where(Contact.family_id==item.family_id)).all() if item.family_id else []
        if actor().role=='fundraiser': contacts=[c for c in contacts if (link:=db.session.get(Link,c.id)) and link.assigned_to==actor().id]
        records=[w for w in db.session.scalars(select(Work).order_by(Work.id.desc())) if w.id!=item.id and readable(w) and (w.family_id==item.family_id or w.kind=='vendor')]
        documents=[]
        if item.family_id and actor().role!='fundraiser':
            documents=[d for d in db.session.scalars(select(Document).where(Document.family_id==item.family_id)) if document_allowed(d)]
        return dict(users=users,all_users=list(db.session.scalars(select(StaffUser).order_by(StaffUser.email))),contacts=contacts,records=records,documents=documents,
                    families=[f for f in db.session.scalars(select(Family).order_by(Family.name)) if scope(actor(),f.id)])

    @app.context_processor
    def workflow_context():
        user=current_user()
        return dict(workflow_roles=ROLES,workflow_user_roles=roles(),workflow_active=active_user(user) and not app.config['DEMO'],workflow_enforced=enforced(),work_status=status,
                    workflow_can_sign=can_sign,workflow_catalog=CATALOG)

    @app.get('/operations')
    def operations():
        user=actor();kind=request.args.get('kind','');fid=request.args.get('family_id',type=int);view=request.args.get('view','open')
        if kind and kind not in CATALOG: abort(404)
        if fid and not scope(user,fid): abort(403)
        query=select(Work).order_by(Work.due,Work.id)
        if kind:query=query.where(Work.kind==kind)
        if fid:query=query.where(Work.family_id==fid)
        items=[w for w in db.session.scalars(query) if readable(w)]
        items=[w for w in items if not (w.kind=='collection' and w.data.get('abcharity_donation_id')
            and (not app.extensions['workflows'].get('import_consistent') or app.extensions['workflows']['import_consistent'](w)))]
        all_items=items
        if view=='open':items=[w for w in items if w.disposition=='Open']
        elif view=='mine':items=[w for w in items if w.owner_id==user.id and w.disposition=='Open']
        elif view=='approvals':items=[w for w in items if can_sign(w)]
        elif view=='overdue':items=[w for w in items if w.disposition=='Open' and w.due<date.today()]
        elif view!='all':abort(400)
        page=max(1,request.args.get('page',1,type=int));pages=max(1,(len(items)+7)//8);page=min(page,pages)
        accessible_families=[f for f in db.session.scalars(select(Family).order_by(Family.name)) if scope(user,f.id)]
        notices=[n for n in db.session.scalars(select(Notice).where(Notice.user_id==user.id,Notice.read_at.is_(None)).order_by(Notice.id.desc()).limit(30)) if readable(db.session.get(Work,n.item_id))]
        family_names={f.id:f.name for f in accessible_families}
        queue=[]
        for item in items[(page-1)*8:page*8]:
            approval=can_sign(item)
            mine=item.owner_id==user.id
            queue.append(dict(item=item,
                reason='Your approval is required' if approval else ('Continue this work' if mine else 'Waiting for assigned staff'),
                next_action='Review and approve' if approval else ('Continue' if mine else 'View'),
                family=family_names.get(item.family_id,'Organization')))
        return render_template('operations.html',title='Operations',catalog=CATALOG,items=items[(page-1)*8:page*8],queue=queue,
            kind=kind,selected_family=fid,view=view,page=page,pages=pages,staff={u.id:u.email for u in db.session.scalars(select(StaffUser))},
            families=accessible_families,today=date.today(),notices=notices,
            counts={'open':sum(w.disposition=='Open' for w in all_items),'mine':sum(w.disposition=='Open' and w.owner_id==user.id for w in all_items),
                    'overdue':sum(w.disposition=='Open' and w.due<date.today() for w in all_items),'approvals':sum(can_sign(w) for w in all_items)})

    @app.route('/operations/new/<kind>',methods=['GET','POST'])
    def work_new(kind):
        user=actor()
        if kind not in CATALOG:abort(404)
        spec=CATALOG[kind]
        fid=request.values.get('family_id',type=int)
        if spec.get('org'):fid=None
        if not spec.get('org') and (not fid or not scope(user,fid) or not db.session.get(Family,fid)): abort(403,'Choose an assigned family first.')
        if user.role=='fundraiser' and kind not in FUNDRAISER_KINDS:abort(403)
        if roles()=={'auditor'}:abort(403)
        item=Work(kind=kind,family_id=fid,title=spec['title'],owner_id=user.id,created_by=user.id,data={},stage=0,disposition='Open',revision=1)
        if not readable(item):abort(403)
        if request.method=='POST':
            item.title=field('title',limit=160);item.data=parse_data(kind)
            try:item.due=date.fromisoformat(field('due'));item.owner_id=int(field('owner_id'))
            except ValueError:fail('Choose an owner and a valid due date.')
            owner=db.session.get(StaffUser,item.owner_id)
            if not active_user(owner) or (fid and not scope(owner,fid)):fail('Choose assigned active staff.')
            if user.role=='fundraiser' and item.owner_id!=user.id:abort(403)
            item.priority=field('priority')
            if item.priority not in ('Normal','High','Urgent'):fail('Choose a valid option.')
            db.session.add(item);db.session.flush();check_links(item);emit(item,'Workflow created',{'data':item.data});notify(item,'New assignment');save()
            return redirect(url_for('work_detail',item_id=item.id))
        return render_template('work_form.html',title=spec['title'],item=item,spec=spec,fields=FIELDS,choices=CHOICES,**choices_for(item))

    @app.route('/operations/<int:item_id>',methods=['GET','POST'])
    def work_detail(item_id):
        actor();item=get_item(item_id,request.method=='POST');spec=CATALOG[item.kind]
        if request.method=='POST':
            if item.owner_id!=actor().id or item.stage!=0 or item.disposition!='Open':abort(403,'Only the owner can edit a draft.')
            if request.form.get('version',type=int)!=item.version:abort(409,'This record changed. Reload before saving.')
            before=dict(item.data);preserved={k:v for k,v in before.items() if k not in spec['fields']}
            item.data={**preserved,**parse_data(item.kind)};item.title=field('title',limit=160)
            try:item.due=date.fromisoformat(field('due'))
            except ValueError:fail('Enter a valid date.')
            check_links(item);item.updated_at=now();emit(item,'Draft updated',{'before':before,'after':item.data});save()
            return redirect(url_for('work_detail',item_id=item.id))
        if request.args.get('edit') and item.stage==0 and item.disposition=='Open':
            return render_template('work_form.html',title=spec['title'],item=item,spec=spec,fields=FIELDS,choices=CHOICES,**choices_for(item))
        for n in db.session.scalars(select(Notice).where(Notice.item_id==item.id,Notice.user_id==actor().id,Notice.read_at.is_(None))):n.read_at=now()
        db.session.commit()
        return render_template('work_detail.html',title=spec['title'],item=item,spec=spec,fields=FIELDS,
            steps=spec['steps'],files=db.session.scalars(select(File).where(File.item_id==item.id)).all(),
            events=db.session.scalars(select(Event).where(Event.item_id==item.id).order_by(Event.id.desc())).all(),
            decisions=db.session.scalars(select(Decision).where(Decision.item_id==item.id).order_by(Decision.id)).all(),
            staff={u.id:u.email for u in db.session.scalars(select(StaffUser))},can_edit=item.owner_id==actor().id and item.stage==0 and item.disposition=='Open',
            totals=financials(item.family_id) if item.family_id and actor().role!='fundraiser' else None)

    @app.post('/operations/<int:item_id>/action')
    def work_action(item_id):
        actor();item=get_item(item_id,True)
        if request.form.get('version',type=int)!=item.version:abort(409,'This record changed. Reload before acting.')
        action=field('action');note=field('note');role=required_role(item)
        if item.disposition not in ('Open','Paused','Failed') and not (item.kind=='pledge' and item.disposition=='Complete' and action in ('Pause','Cancel')):fail('This workflow is already complete.')
        if action=='Resume':
            if item.disposition not in ('Paused','Failed') or item.owner_id!=actor().id:abort(403)
            item.disposition='Open'
            if item.kind=='pledge' and item.stage==len(CATALOG[item.kind]['steps'])-1:
                item.stage=0;item.revision+=1
        elif action in ('Pause','Cancel','Failed'):
            if item.owner_id!=actor().id:abort(403)
            if db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==item.id)):fail('Posted money requires a refund or adjustment workflow.')
            if item.kind in FINANCIAL and item.stage>0:fail('A reviewer must reject or return this financial request.')
            item.disposition='Paused' if action=='Pause' else 'Failed' if action=='Failed' else 'Canceled'
            if item.kind=='pledge':
                db.session.get(Contact,item.data['contact_id']).status='Paused'
        elif action in ('Return','Reject'):
            if item.stage==0 or not can_sign(item):abort(403)
            if db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==item.id)):fail('Posted money requires a refund or adjustment workflow.')
            db.session.add(Decision(item_id=item.id,revision=item.revision,stage=item.stage,actor_id=actor().id,role=role,action=action,note=note))
            if action=='Return':item.revision+=1;item.stage=0
            else:item.disposition='Rejected'
            if item.kind=='expense' and item.data.get('expense_id'):
                db.session.get(Expense,item.data['expense_id']).status='Requested' if action=='Return' else 'Declined'
        elif action=='Advance':
            if not can_sign(item):abort(403,'This step requires a different authorized reviewer.')
            if item.stage>=len(CATALOG[item.kind]['steps'])-1:fail('This workflow is already complete.')
            external_details(item)
            if item.stage==0:item.data={**item.data,'_submitted_by':actor().id}
            next_label=CATALOG[item.kind]['steps'][item.stage+1][0]
            stage_gate(item,next_label)
            if role!='owner':
                db.session.add(Decision(item_id=item.id,revision=item.revision,stage=item.stage,actor_id=actor().id,role=role,action='Approve',note=note));db.session.flush()
                count=db.session.scalar(select(func.count()).select_from(Decision).where(Decision.item_id==item.id,Decision.revision==item.revision,Decision.stage==item.stage,Decision.action=='Approve'))
            else:count=1
            if count>=CATALOG[item.kind]['steps'][item.stage][2]:
                effects(item,next_label);item.stage+=1
                if item.stage==len(CATALOG[item.kind]['steps'])-1:item.disposition='Complete'
        else:abort(400)
        item.updated_at=now();emit(item,action,{'note':note,'stage':item.stage,'status':status(item),'revision':item.revision});notify(item,'Workflow needs attention');save()
        return redirect(url_for('work_detail',item_id=item.id))

    @app.post('/operations/<int:item_id>/files')
    def work_file_upload(item_id):
        item=get_item(item_id,True);actor()
        if item.disposition!='Open' or (item.owner_id!=actor().id and not can_sign(item)):abort(403)
        upload=request.files.get('file');name=secure_filename(upload.filename or '') if upload else ''
        data=upload.read(8*1024*1024+1) if upload else b''
        if not name or len(name)>255 or not data or len(data)>8*1024*1024:fail('Document must be between 1 byte and 8 MB.')
        kinds=[(b'%PDF-','application/pdf',('.pdf',)),(b'\x89PNG\r\n\x1a\n','image/png',('.png',)),(b'\xff\xd8\xff','image/jpeg',('.jpg','.jpeg'))]
        match=next((x for x in kinds if data.startswith(x[0]) and name.lower().endswith(x[2])),None)
        if not match:fail('Choose a PDF, PNG, or JPEG document.')
        purpose=request.form.get('purpose','Supporting evidence')
        if purpose not in ('Supporting evidence','Invoice','Payment proof','Signed receipt','Consent','Verification'):fail('Choose a valid option.')
        db.session.add(File(item_id=item.id,filename=name,content_type=match[1],data=data,actor_id=actor().id,purpose=purpose,revision=item.revision,stage=item.stage));emit(item,'Evidence attached',{'filename':name});save()
        return redirect(url_for('work_detail',item_id=item.id))

    @app.get('/operations/files/<int:file_id>')
    def work_file_download(file_id):
        file=db.get_or_404(File,file_id);item=get_item(file.item_id);emit(item,'Evidence downloaded',{'file_id':file.id});save()
        return send_file(BytesIO(file.data),mimetype=file.content_type,as_attachment=True,download_name=file.filename,max_age=0)

    @app.get('/operations/reports')
    def operating_reports():
        user=actor()
        if user.role in ('fundraiser','office_employee'):abort(403)
        families=[f for f in db.session.scalars(select(Family).order_by(Family.name)) if scope(user,f.id)]
        rows=[]
        for f in families:
            row=financials(f.id);row['family']=f;row['pledged']=monthly_pledged(f.id)
            assessment=approved('assessment',f.id);row['gap']=assessment.data['gap'] if assessment else None
            row['goal']=assessment.data['goal'] if assessment else None
            plan=approved('support_plan',f.id);review=approved('review',f.id)
            row['review_date']=(review.data['review_date'] if review and plan and review.data.get('plan_id')==plan.id else plan.data['review_date'] if plan else None)
            row['due_reviews']=bool(row['review_date'] and row['review_date']<date.today().isoformat())
            row['failed']=db.session.scalar(select(func.count()).select_from(Work).where(Work.family_id==f.id,Work.kind=='collection',Work.disposition=='Failed'))
            rows.append(row)
        return render_template('operating_reports.html',title='Organization-wide report',rows=rows,
            totals={k:sum(r[k] for r in rows) for k in ['collected','assistance','overhead','balance','reserved','available','protected_reserve','pledged','unmatched','failed']})

    @app.get('/families/<int:family_id>/ledger')
    def case_ledger(family_id):
        user=actor()
        if user.role in ('fundraiser','office_employee') or not scope(user,family_id):abort(403)
        family=db.get_or_404(Family,family_id)
        entries=db.session.scalars(select(Ledger).where(Ledger.family_id==family_id).order_by(Ledger.id.desc())).all()
        matched={m.ledger_id:m for m in db.session.scalars(select(Match).where(Match.ledger_id.in_([e.id for e in entries])))}
        return render_template('case_ledger.html',title='Case ledger',family=family,entries=entries,matched=matched,totals=financials(family_id))

    @app.route('/workflow-access',methods=['GET','POST'])
    def workflow_access():
        user=actor()
        if not org_admin():abort(403)
        if request.method=='POST':
            uid=request.form.get('user_id',type=int);role=field('role');target=db.get_or_404(StaffUser,uid)
            if role not in ROLES:abort(400)
            if target.role=='fundraiser' and role not in ('fundraising',):fail('Fundraiser accounts cannot receive confidential workflow responsibilities.')
            grant=db.session.scalar(select(Grant).where(Grant.user_id==uid,Grant.role==role))
            if grant:db.session.delete(grant)
            else:db.session.add(Grant(user_id=uid,role=role))
            emit(None,'Workflow responsibility changed',{'user_id':uid,'role':role,'granted':not bool(grant)});save()
            return redirect(url_for('workflow_access'))
        users=db.session.scalars(select(StaffUser).order_by(StaffUser.email)).all()
        return render_template('workflow_access.html',title='Workflow responsibilities',users=users,grants={u.id:roles(u) for u in users},roles=ROLES)

    def document_allowed(document):
        control=db.session.get(Control,document.id)
        if not control:return True
        required={'Medical':{'medical'},'Finance':{'finance','auditor'},'Restricted':{'compliance','executive'}}.get(control.privacy)
        return not required or bool(roles().intersection(required))

    def document_access(document):
        if not document_allowed(document):abort(403,'This document requires additional privacy access.')

    def protect_document_delete(document):
        fail('Archive documents through the document workflow. Evidence and earlier versions are retained.')

    def legacy_status(family_id,target):
        mapping={'Under review':'intake','Active':'case_approval','Closed':'closure','Declined':'case_approval','Paused':'review'}
        flash('Use the case workflow for recorded reviews and approvals.')
        return redirect(url_for('operations',family_id=family_id,kind='reopening' if db.session.get(Family,family_id).status=='Closed' else mapping.get(target,'review')))

    def legacy_expense(expense_id):
        user=actor();e=db.get_or_404(Expense,expense_id)
        if not scope(user,e.family_id) or user.role=='fundraiser':abort(403)
        for w in db.session.scalars(select(Work).where(Work.kind=='expense',Work.family_id==e.family_id)):
            if w.data.get('expense_id')==e.id:return redirect(url_for('work_detail',item_id=w.id))
        if e.status in ('Paid','Declined','Voided'):fail('This legacy expense is already final. Its history is preserved.')
        data={'expense_id':e.id,'amount':e.amount_cents,'month':e.month,'category':e.category,'payee':e.payee,
              'expense_type':'Organization expense' if e.category=='Organization expense' else 'Family assistance','reason':e.note}
        w=Work(kind='expense',family_id=e.family_id,title=e.payee,owner_id=user.id,created_by=user.id,due=date.today(),data=data)
        db.session.add(w);db.session.flush();emit(w,'Legacy expense linked',{'expense_id':e.id,'legacy_status':e.status});save()
        return redirect(url_for('work_detail',item_id=w.id,edit=1))

    def prepare_stripe_release(expense, recipient, currency):
        item = next((w for w in db.session.scalars(select(Work).where(
            Work.kind=='expense', Work.family_id==expense.family_id).with_for_update())
            if w.data.get('expense_id')==expense.id), None)
        if not item or item.disposition!='Open' or item.stage!=6:
            fail('Complete the expense workflow through payment release before sending through Stripe.')
        if not readable(item) or not can_sign(item):
            abort(403,'This step requires a different authorized reviewer.')
        lock_family(item.family_id)
        complete_fields(item)
        check_budget(item)
        if currency.lower()!='usd' or expense.amount_cents!=item.data['amount'] or expense.month!=item.data['month']:
            fail('The payment must match the approved expense amount, month and currency.')
        vendor=db.session.get(Work,item.data['vendor_id'])
        if not vendor or vendor.disposition!='Complete' or vendor.data.get('stripe_account')!=recipient.stripe_account_id:
            fail('The Stripe recipient must match the connected account in the approved vendor record.')
        if item.data.get('cash'):
            fail('A cash approval cannot be released as a Stripe transfer.')
        return item

    def finish_stripe_release(item, reference, recipient):
        if not reference or len(reference)>180:
            fail('Stripe did not return a valid transfer reference.')
        proof=json.dumps({'transfer_id':reference,'destination':recipient.stripe_account_id,
                          'amount_cents':item.data['amount'],'currency':'usd'}).encode()
        db.session.add(File(item_id=item.id,filename='stripe-transfer.json',content_type='application/json',
            data=proof,actor_id=actor().id,purpose='Payment proof',revision=item.revision,stage=item.stage))
        item.data={**item.data,'reference':reference,'payment_result':'Stripe transfer confirmed'}
        db.session.flush()
        stage_gate(item,'Paid')
        db.session.add(Decision(item_id=item.id,revision=item.revision,stage=item.stage,actor_id=actor().id,
            role='payment_releaser',action='Approve',note='Stripe transfer confirmed: '+reference))
        effects(item,'Paid');item.stage=7;item.updated_at=now()
        emit(item,'Stripe payment released',{'reference':reference,'recipient_id':recipient.id})
        notify(item,'Workflow needs attention')

    def create_onboarding(user):
        if not policy():return
        db.session.add(Access(user_id=user.id,active=False))
        w=Work(kind='onboarding',title='User onboarding',owner_id=actor().id,created_by=actor().id,
               due=date.today(),data={'user_id':user.id})
        db.session.add(w);db.session.flush();emit(w,'New assignment',{'user_id':user.id});notify(w,'New assignment')

    def queue_access_change(user,new_role):
        if not policy():return None
        w=Work(kind='access_change',title='Staff departure or role change',owner_id=actor().id,created_by=actor().id,
               due=date.today(),data={'user_id':user.id,'new_role':new_role,'access_change':'Role change'})
        db.session.add(w);db.session.flush();emit(w,'New assignment',{'user_id':user.id});notify(w,'New assignment');save()
        return redirect(url_for('work_detail',item_id=w.id,edit=1))

    @app.cli.command('workflow-escalate')
    def workflow_escalate():
        count=0
        for item in db.session.scalars(select(Work).where(Work.disposition=='Open',Work.due<date.today())):
            last=db.session.scalar(select(Notice).where(Notice.item_id==item.id,Notice.message=='Overdue workflow').order_by(Notice.id.desc()))
            if not last or last.at.date()<date.today():notify(item,'Overdue workflow');count+=1
        db.session.commit();print(f'Escalated {count} overdue workflows.')

    @app.post('/expenses/<int:expense_id>/workflow')
    def expense_workflow(expense_id):return legacy_expense(expense_id)

    app.extensions['workflows']=dict(models=M,active_user=active_user,enforced=enforced,prepare_stripe_release=prepare_stripe_release,finish_stripe_release=finish_stripe_release,roles=roles,legacy_status=legacy_status,
        legacy_expense=legacy_expense,document_access=document_access,document_allowed=document_allowed,
        protect_document_delete=protect_document_delete,financials=financials,emit=emit,readable=readable,
        status=status,can_sign=can_sign,monthly_pledged=monthly_pledged,approved=approved,create_onboarding=create_onboarding,queue_access_change=queue_access_change)
