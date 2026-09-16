"""Per-staff unread activity feed for Yazory."""
from datetime import datetime, timezone

from flask import abort, redirect, render_template, session, url_for
from sqlalchemy import func, select

import app_original as core


class StaffActivityCursor(core.db.Model):
    __tablename__ = 'staff_activity_cursor'
    staff_user_id = core.db.Column(
        core.db.Integer, core.db.ForeignKey('staff_user.id'), primary_key=True)
    last_seen_at = core.db.Column(core.db.DateTime, nullable=False, index=True)


class StaffActivityRead(core.db.Model):
    """One activity item opened by one staff member."""
    __tablename__ = 'staff_activity_read'
    staff_user_id = core.db.Column(
        core.db.Integer, core.db.ForeignKey('staff_user.id'), primary_key=True)
    audit_id = core.db.Column(
        core.db.Integer, core.db.ForeignKey('audit.id'), primary_key=True)
    read_at = core.db.Column(core.db.DateTime, nullable=False, default=lambda: _now())


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def install(app):
    def ensure_schema():
        StaffActivityCursor.__table__.create(core.db.engine, checkfirst=True)
        StaffActivityRead.__table__.create(core.db.engine, checkfirst=True)
        now = _now()
        for user in core.db.session.scalars(select(core.StaffUser)).all():
            if core.db.session.get(StaffActivityCursor, user.id) is None:
                core.db.session.add(StaffActivityCursor(
                    staff_user_id=user.id,
                    last_seen_at=user.last_login_at or user.activated_at or now))
        core.db.session.commit()

    app.extensions.setdefault('init_db_hooks', []).append(ensure_schema)
    if app.config.get('DEMO') or app.config.get('TESTING'):
        with app.app_context():
            ensure_schema()

    def user_and_cursor():
        user = core.db.session.get(core.StaffUser, session.get('user_id'))
        if not user:
            return None, None
        cursor = core.db.session.get(StaffActivityCursor, user.id)
        if cursor is None:
            cursor = StaffActivityCursor(
                staff_user_id=user.id,
                last_seen_at=user.last_login_at or user.activated_at or _now())
            core.db.session.add(cursor)
            core.db.session.commit()
        return user, cursor

    def visible_family_ids(user):
        if user.role == 'organization_admin':
            return None
        return list(core.db.session.scalars(select(core.FamilyAssignment.family_id).where(
            core.FamilyAssignment.staff_user_id == user.id)))

    def audit_statement(user, since):
        statement = select(core.Audit).where(
            core.Audit.at > since,
            ~select(StaffActivityRead.audit_id).where(
                StaffActivityRead.staff_user_id == user.id,
                StaffActivityRead.audit_id == core.Audit.id).exists())
        family_ids = visible_family_ids(user)
        if family_ids is not None:
            statement = statement.where(core.Audit.family_id.in_(family_ids))
        return statement

    def unread_count(user, cursor):
        return core.db.session.scalar(select(func.count()).select_from(
            audit_statement(user, cursor.last_seen_at).subquery())) or 0

    def activity_kind(action):
        lowered = action.lower()
        if any(word in lowered for word in ('receipt', 'donation', 'pledge', 'stripe')):
            return 'Donation'
        if any(word in lowered for word in ('message', 'email', 'replied')):
            return 'Message'
        if any(word in lowered for word in ('application', 'intake', 'family')):
            return 'Application'
        if any(word in lowered for word in ('expense', 'payout', 'check')):
            return 'Money and approval'
        if 'task' in lowered:
            return 'Task'
        return 'Activity'

    def activity_url(row):
        lowered = row.action.lower()
        if any(word in lowered for word in ('message', 'email', 'replied')):
            return url_for('communications', _anchor='general-inbox')
        if any(word in lowered for word in ('receipt', 'donation', 'pledge', 'stripe')):
            return url_for('collections')
        if 'expense' in lowered:
            return url_for('expenses')
        if 'payout' in lowered or 'check' in lowered:
            return url_for('payouts')
        if 'task' in lowered:
            return url_for('tasks')
        if row.family_id:
            return url_for('family_detail', family_id=row.family_id)
        return url_for('dashboard')

    @app.context_processor
    def notification_context():
        if not session.get('user_id'):
            return {'new_activity_count': 0}
        user, cursor = user_and_cursor()
        if not user or app.config.get('DEMO'):
            return {'new_activity_count': 0}
        return {'new_activity_count': unread_count(user, cursor)}

    @app.get('/notifications')
    def notifications():
        user, cursor = user_and_cursor()
        if not user:
            abort(403)
        rows = core.db.session.scalars(audit_statement(user, cursor.last_seen_at).order_by(
            core.Audit.at.desc(), core.Audit.id.desc()).limit(100)).all()
        items = [{
            'id': row.id,
            'action': row.action,
            'actor': row.actor,
            'at': row.at,
            'kind': activity_kind(row.action),
            'url': activity_url(row),
        } for row in rows]
        return render_template('notifications.html', title='What’s new', items=items,
                               unread_count=len(items), since=cursor.last_seen_at)

    @app.get('/notifications/<int:audit_id>/open')
    def notification_open(audit_id):
        user, cursor = user_and_cursor()
        if not user:
            abort(403)
        row = core.db.session.scalar(
            audit_statement(user, cursor.last_seen_at).where(core.Audit.id == audit_id))
        if row is None:
            abort(404)
        core.db.session.add(StaffActivityRead(
            staff_user_id=user.id, audit_id=row.id, read_at=_now()))
        core.db.session.commit()
        return redirect(activity_url(row))

    @app.post('/notifications/mark-read')
    def notifications_mark_read():
        user, cursor = user_and_cursor()
        if not user:
            abort(403)
        cursor.last_seen_at = _now()
        core.db.session.commit()
        return redirect(url_for('notifications'))
