"""One read-only view of assignments from staff tasks and operating workflows."""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, render_template, request, session, url_for
from sqlalchemy import select

import app as extended
import app_original as core


def install(app):
    @app.get('/work-queue')
    def work_queue():
        user = core.db.session.get(core.StaffUser, session.get('user_id'))
        if not user or user.status != 'active':
            abort(403)
        if user.role == 'askan':
            abort(403)
        workflow = app.extensions['workflows']
        if not workflow['active_user'](user):
            abort(403)
        now_local = datetime.now(ZoneInfo('America/New_York')).replace(tzinfo=None)
        today = now_local.date()
        view = request.args.get('view', 'mine')
        if view not in ('mine', 'overdue', 'all') or (view == 'all' and user.role != 'organization_admin'):
            abort(400)

        tasks = core.db.session.scalars(select(extended.StaffTask).where(
            extended.StaffTask.status.notin_(('Completed', 'Cancelled')))).all()
        callbacks = app.extensions['scheduled_callback_map'](tasks)
        records = []
        for task in tasks:
            if view != 'all' and task.assigned_to != user.id:
                continue
            callback = callbacks.get(task.source_contact_id)
            overdue = (callback.scheduled_for < now_local if callback else
                       bool(task.due_date and task.due_date < today))
            if view == 'overdue' and not overdue:
                continue
            records.append(dict(kind='Staff task', title=task.title,
                                parent_title=task.parent.title if task.parent else '',
                                family=task.family.name if task.family else '',
                                assignee=task.assignee.name or task.assignee.email,
                                due=task.due_date, status=task.status,
                                callback_at=callback.scheduled_for if callback else None,
                                url=url_for('task_detail', task_id=task.id),
                                mine=task.assigned_to == user.id))

        Work = workflow['models']['WorkItem']
        for item in core.db.session.scalars(select(Work).where(
                Work.disposition == 'Open')).all():
            if not workflow['readable'](item, user):
                continue
            if item.kind == 'collection' and item.data.get('abcharity_donation_id'):
                consistent = workflow.get('import_consistent')
                if not consistent or consistent(item):
                    continue
            mine = item.owner_id == user.id or workflow['can_sign'](item)
            if view != 'all' and not mine:
                continue
            if view == 'overdue' and item.due >= today:
                continue
            owner = core.db.session.get(core.StaffUser, item.owner_id)
            family = core.db.session.get(core.Family, item.family_id) if item.family_id else None
            records.append(dict(kind='Operations', title=item.title,
                                parent_title='',
                                family=family.name if family else '',
                                assignee=(owner.name or owner.email) if owner else '',
                                due=item.due, status=workflow['status'](item),
                                callback_at=None,
                                url=url_for('work_detail', item_id=item.id), mine=mine))

        records.sort(key=lambda row: (row['due'] is None, row['due'] or today,
                                      not row['mine'], row['title'].casefold()))
        return render_template('work_queue.html', title='Work queue',
                               records=records, view=view, today=today,
                               callback_now=now_local)
