"""Review existing manual and Stripe receipts without counting them as cash twice."""
from datetime import date
from flask import abort, redirect, url_for
from sqlalchemy import select


def install_receipt_workflows(app, db, Receipt, helpers):
    ext=app.extensions['workflows']; Work=ext['models']['WorkItem']
    previous_consistent=ext['import_consistent']

    def consistent(item):
        if not previous_consistent(item):return False
        rid=item.data.get('receipt_id')
        if not rid:return True
        receipt=db.session.get(Receipt,rid)
        return bool(receipt and receipt.family_id==item.family_id
            and receipt.contact_id==item.data.get('contact_id')
            and receipt.amount_cents==item.data.get('amount')
            and item.data.get('reference')=='receipt:'+(receipt.reference[:160] or str(receipt.id)))

    @app.post('/collections/receipts/<int:receipt_id>/workflow')
    def receipt_workflow(receipt_id):
        user=helpers['current_user']()
        if not ext['active_user'](user) or user.role in ('fundraiser','office_employee'):abort(403)
        receipt=db.session.scalar(select(Receipt).where(Receipt.id==receipt_id).with_for_update())
        if not receipt:abort(404)
        if not helpers['can_access_family'](receipt.family_id):abort(403)
        for item in db.session.scalars(select(Work).where(Work.kind=='collection',Work.family_id==receipt.family_id)):
            if item.data.get('receipt_id')==receipt.id:
                return redirect(url_for('work_detail',item_id=item.id))
        if receipt.amount_cents<=0:abort(400,'Review this receipt with finance before posting it.')
        item=Work(kind='collection',family_id=receipt.family_id,title='Donation collection',
            owner_id=user.id,created_by=user.id,due=date.today(),data={
                'receipt_id':receipt.id,'contact_id':receipt.contact_id,'amount':receipt.amount_cents,
                'processing_fee':0,'reference':'receipt:'+(receipt.reference[:160] or str(receipt.id)),
                'payment_method':'Stripe' if 'Stripe' in receipt.note else 'Manual receipt',
                'receipt':receipt.reference or str(receipt.id),'restrictions':receipt.note})
        db.session.add(item);db.session.flush()
        ext['emit'](item,'Imported receipt linked',{'receipt_id':receipt.id,'amount_cents':receipt.amount_cents})
        db.session.commit()
        return redirect(url_for('work_detail',item_id=item.id,edit=1))

    ext['import_consistent']=consistent
