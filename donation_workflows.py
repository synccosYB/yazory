"""Bridge imported ABCharity receipts into independently reviewed USD postings."""
from datetime import date
from flask import abort, redirect, url_for
from sqlalchemy import select


def install_donation_workflows(app,db,Campaign,Donation,Donor,helpers):
    ext=app.extensions['workflows'];M=ext['models'];Work=M['WorkItem'];Ledger=M['LedgerEntry']

    @app.post('/families/<int:family_id>/donations/<int:donation_id>/workflow')
    def donation_workflow(family_id,donation_id):
        user=helpers['current_user']()
        if not user or user.role in ('fundraiser','office_employee') or not helpers['can_access_family'](family_id):abort(403)
        donation=db.session.scalar(select(Donation).join(Campaign,Campaign.id==Donation.campaign_id).where(Donation.id==donation_id,Campaign.family_id==family_id).with_for_update())
        if not donation:abort(404)
        campaign=db.session.get(Campaign,donation.campaign_id);donor=db.session.get(Donor,donation.donor_id)
        if campaign.currency!='USD':abort(400,'The case ledger uses USD. A documented currency conversion is required.')
        if donation.amount_cents<=0 or not 0<=donation.net_cents<=donation.amount_cents:abort(400,'Review this receipt with finance before posting it.')
        for item in db.session.scalars(select(Work).where(Work.kind=='collection',Work.family_id==family_id)):
            if item.data.get('abcharity_donation_id')==donation.id:return redirect(url_for('work_detail',item_id=item.id))
        item=Work(kind='collection',family_id=family_id,title='ABCharity donation '+donation.external_id,
            owner_id=user.id,created_by=user.id,due=date.today(),data={'contact_id':donor.contact_id,
                'amount':donation.amount_cents,'processing_fee':donation.amount_cents-donation.net_cents,
                'reference':'abcharity:'+campaign.external_id+':'+donation.external_id,
                'abcharity_donation_id':donation.id,'abcharity_net':donation.net_cents,
                'restrictions':campaign.label,'payment_method':'ABCharity','receipt_preference':None})
        db.session.add(item);db.session.flush();ext['emit'](item,'Imported receipt linked',{'donation_id':donation.id,'gross_cents':donation.amount_cents,'net_cents':donation.net_cents});db.session.commit()
        return redirect(url_for('work_detail',item_id=item.id,edit=1))

    def baseline(item):
        corrections=db.session.scalars(select(Work).where(Work.kind=='unusual',Work.family_id==item.family_id,Work.disposition=='Complete').order_by(Work.id.desc()))
        for correction in corrections:
            if correction.data.get('source_id')==item.id and correction.data.get('import_correction'):
                return correction.data['corrected_gross'],correction.data['corrected_net']
        return item.data['amount'],item.data['abcharity_net']

    def correction(item,next_label,post):
        source=db.session.get(Work,item.data.get('source_id'))
        if not source or not source.data.get('abcharity_donation_id'):return
        donation=db.session.get(Donation,source.data['abcharity_donation_id'])
        if not donation or not db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==source.id)):return
        if item.stage==0:
            oldgross,oldnet=baseline(source)
            item.data={**item.data,'import_correction':True,'previous_gross':oldgross,'previous_net':oldnet,
                       'corrected_gross':donation.amount_cents,'corrected_net':donation.net_cents}
        if next_label!='Completed':return
        if (donation.amount_cents,donation.net_cents)!=(item.data['corrected_gross'],item.data['corrected_net']):abort(400,'The imported receipt changed. Review the original before continuing.')
        if baseline(source)!=(item.data['previous_gross'],item.data['previous_net']):abort(400,'This receipt already has a newer approved correction.')
        if post:
            deltas=[('Donation adjustment',item.data['corrected_gross']-item.data['previous_gross']),
                    ('Processing fee adjustment',-(item.data['corrected_gross']-item.data['corrected_net']-item.data['previous_gross']+item.data['previous_net']))]
            for typ,amount in deltas:
                if amount:db.session.add(Ledger(family_id=item.family_id,source_item_id=item.id,entry_type=typ,amount_cents=amount,
                    actor_id=helpers['current_user']().id,external_reference=None))
            ext['emit'](item,'Import correction posted',{'source_id':source.id,'deltas':deltas})

    @app.post('/operations/<int:item_id>/refresh-import')
    def refresh_import(item_id):
        user=helpers['current_user']();item=db.get_or_404(Work,item_id)
        if not user or item.owner_id!=user.id or not ext['readable'](item) or item.stage!=0 or item.disposition!='Open':abort(403)
        donation=db.session.get(Donation,item.data.get('abcharity_donation_id'))
        if not donation:abort(404)
        if donation.amount_cents<=0 or not 0<=donation.net_cents<=donation.amount_cents:abort(400,'Review this receipt with finance before posting it.')
        before=dict(item.data);item.data={**item.data,'amount':donation.amount_cents,'abcharity_net':donation.net_cents,'processing_fee':donation.amount_cents-donation.net_cents}
        ext['emit'](item,'Imported receipt refreshed',{'before':before,'after':item.data});db.session.commit()
        return redirect(url_for('work_detail',item_id=item.id))

    def consistent(item):
        did=item.data.get('abcharity_donation_id')
        if not did:return True
        donation=db.session.get(Donation,did)
        campaign=db.session.get(Campaign,donation.campaign_id) if donation else None
        return bool(donation and campaign and campaign.currency=='USD' and campaign.family_id==item.family_id
                    and (donation.amount_cents,donation.net_cents)==baseline(item))

    def check_case(fid):
        for item in db.session.scalars(select(Work).where(Work.kind=='collection',Work.family_id==fid)):
            if item.data.get('abcharity_donation_id') and db.session.scalar(select(Ledger.id).where(Ledger.source_item_id==item.id)) and not consistent(item):
                abort(400,'An imported receipt changed after posting. Finance must reconcile the difference before more spending.')

    ext['import_consistent']=consistent;ext['check_import_case']=check_case;ext['import_correction']=correction;ext['import_baseline']=baseline
