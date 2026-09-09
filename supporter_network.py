"""Case-owned family relationships, outreach consent, and contact-level assignment."""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

RELATIONS=['Sibling','Child of sibling','Uncle / aunt','First cousin','Second cousin','Child of first cousin','Parent’s first cousin','Parent','Friend','Other']
SIDES=['Husband','Wife','Community']
PERMISSIONS=['Not requested','Permitted','Do not contact']
PREFERENCES=['Phone','Text message','Email','Through family']


def install_network(app,db,entities,helpers):
    Family=entities['Family'];Contact=entities['Contact'];User=entities['StaffUser'];Assignment=entities['FamilyAssignment']
    Link=app.extensions['workflows']['models']['SupporterLink']
    current_user=helpers['current_user'];scope=helpers['can_access_family']

    def allowed(fid,manage=False):
        user=current_user()
        if not user or not app.extensions['workflows']['active_user'](user) or not scope(fid):abort(403)
        if manage and user.role not in ('organization_admin','family_admin'):abort(403)
        if user.role=='office_employee':abort(403)
        return user

    def contact_allowed(contact,edit=False):
        user=allowed(contact.family_id)
        if user.role=='fundraiser':
            link=db.session.get(Link,contact.id)
            if not link or link.assigned_to!=user.id:abort(403,'This supporter is not assigned to you.')
            if edit and link.permission!='Permitted':abort(403,'This supporter has not permitted contact.')

    def emit(fid,action,details):
        E=app.extensions['workflows']['models']['WorkflowEvent']
        db.session.add(E(family_id=fid,actor_id=current_user().id,action=action,detail=details))

    def value(key,required=False):
        v=request.form.get(key,'').strip()
        if (required and not v) or len(v)>1000:abort(400,'Complete the required fields.')
        return v

    @app.route('/families/<int:family_id>/network',methods=['GET','POST'])
    def supporter_network(family_id):
        user=allowed(family_id,request.method=='POST');family=db.get_or_404(Family,family_id)
        contacts=db.session.scalars(select(Contact).where(Contact.family_id==family_id).order_by(Contact.id)).all()
        links={c.contact_id:c for c in db.session.scalars(select(Link).where(Link.contact_id.in_([c.id for c in contacts])))}
        if request.method=='POST':
            if family.status=='Closed':abort(400,'Reopen the case before starting new operations.')
            cid=request.form.get('contact_id',type=int)
            contact=db.session.get(Contact,cid) if cid else Contact(family_id=family_id,status='To contact',monthly_cents=0)
            if not contact or contact.family_id!=family_id:abort(403)
            name=value('name',True)
            if len(name)>160:abort(400,'The text is too long.')
            contact.name=name;contact.phone=value('phone');relation=value('relationship',True);side=value('side',True)
            if len(contact.phone)>80 or relation not in RELATIONS or side not in SIDES:abort(400,'Choose a valid option.')
            contact.relationship=relation;db.session.add(contact);db.session.flush()
            link=links.get(contact.id) or Link(contact_id=contact.id)
            parent=request.form.get('parent_id',type=int)
            if parent:
                p=db.session.get(Contact,parent);pl=db.session.get(Link,parent)
                if not p or p.family_id!=family_id or not pl or pl.side!=side:abort(400,'Choose a parent connection on the same side of this family.')
                seen={contact.id};cursor=parent
                while cursor:
                    if cursor in seen:abort(400,'Family connections cannot contain a cycle.')
                    seen.add(cursor);node=db.session.get(Link,cursor);cursor=node.parent_id if node else None
                expected={'Child of sibling':{'Sibling'},'First cousin':{'Uncle / aunt'},'Second cousin':{'Parent’s first cousin'},'Child of first cousin':{'First cousin'},'Parent’s first cousin':{'Parent'}}
                if relation in expected and pl.relationship not in expected[relation]:abort(400,'The relationship does not match the selected family connection.')
            elif relation in ('Child of sibling','First cousin','Second cousin','Child of first cousin','Parent’s first cousin'):
                abort(400,'Choose the relative this person connects through.')
            uid=request.form.get('assigned_to',type=int)
            if uid:
                staff=db.session.get(User,uid)
                assigned=staff and (staff.role=='organization_admin' or db.session.scalar(select(Assignment.id).where(Assignment.staff_user_id==uid,Assignment.family_id==family_id)))
                if not assigned or staff.role not in ('fundraiser','family_admin','organization_admin') or not app.extensions['workflows']['active_user'](staff):abort(400,'Choose assigned active staff.')
            permission=value('permission',True);preference=value('preference')
            if permission not in PERMISSIONS or (preference and preference not in PREFERENCES):abort(400,'Choose a valid option.')
            before={k:getattr(link,k,None) for k in ('parent_id','side','relationship','assigned_to','permission','verified')}
            if any(x.parent_id==contact.id and x.side!=side for x in links.values()):abort(400,'Update the connected relatives before changing sides.')
            expected_children={'Child of sibling':{'Sibling'},'First cousin':{'Uncle / aunt'},'Second cousin':{'Parent’s first cousin'},'Child of first cousin':{'First cousin'},'Parent’s first cousin':{'Parent'}}
            if any(x.parent_id==contact.id and x.relationship in expected_children and relation not in expected_children[x.relationship] for x in links.values()):abort(400,'Update the connected relatives before changing the relationship.')
            link.parent_id=parent;link.side=side;link.relationship=relation;link.assigned_to=uid
            link.permission=permission;link.preference=preference;link.introduced_by=value('introduced_by');link.verified=value('verified')=='yes'
            if permission=='Do not contact':contact.status='Paused'
            db.session.add(link);emit(family_id,'Supporter relationship updated',{'contact_id':contact.id,'before':before,
                'after':{'parent_id':parent,'side':side,'relationship':relation,'assigned_to':uid,'permission':permission,'verified':link.verified}})
            db.session.commit();flash('Supporter network saved.');return redirect(url_for('supporter_network',family_id=family_id))
        if user.role=='fundraiser':contacts=[c for c in contacts if c.id in links and links[c.id].assigned_to==user.id]
        rows=[];visible={c.id:c for c in contacts}
        def walk(parent,depth,seen):
            for c in contacts:
                link=links.get(c.id)
                pid=link.parent_id if link else None
                if (pid if pid in visible else None)!=parent or c.id in seen:continue
                seen.add(c.id);rows.append({'contact':c,'link':link,'depth':depth,'through':visible.get(pid),
                  'grade':'A' if link and link.relationship=='Sibling' else 'B' if link and link.relationship in ('Child of sibling','Uncle / aunt') else 'C' if link and link.relationship=='First cousin' else 'D' if link and link.relationship=='Second cousin' else ''})
                walk(c.id,depth+1,seen)
        walk(None,0,set())
        staff=[u for u in db.session.scalars(select(User).order_by(User.email)) if u.role in ('fundraiser','family_admin','organization_admin') and
               (u.role=='organization_admin' or db.session.scalar(select(Assignment.id).where(Assignment.staff_user_id==u.id,Assignment.family_id==family_id)))]
        editid=request.args.get('edit',type=int);edit=visible.get(editid);editlink=links.get(editid)
        if editid and user.role=='fundraiser':abort(403)
        return render_template('supporter_network.html',title='Family supporter network',family=family,rows=rows,contacts=contacts,links=links,
             staff=staff,relations=RELATIONS,sides=SIDES,permissions=PERMISSIONS,preferences=PREFERENCES,edit=edit,editlink=editlink,may_manage=user.role!='fundraiser')

    app.extensions['workflows']['contact_allowed']=contact_allowed
