"""Per-staff unread activity feed for Yazory."""
import re
import time
from datetime import datetime, timezone

from flask import abort, g, redirect, render_template, session, url_for
from sqlalchemy import func, select, text

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
    # The unread badge appears on nearly every staff page. Recounting the
    # entire growing audit feed for every render makes unrelated navigation
    # slower as history grows. Keep a tiny process-local cache; correctness is
    # bounded to a few seconds and explicit read actions invalidate it.
    unread_cache = {}
    unread_cache_seconds = 15.0

    def invalidate_unread(user_id):
        unread_cache.pop(user_id, None)

    def ensure_schema():
        StaffActivityCursor.__table__.create(core.db.engine, checkfirst=True)
        StaffActivityRead.__table__.create(core.db.engine, checkfirst=True)
        # The unread badge is calculated on every authenticated staff page.
        # Keep its growing audit scan on indexed columns rather than allowing
        # navigation latency to increase with the lifetime of the application.
        # Keep index DDL out of ORM metadata: app factories can run repeatedly
        # in a single process, and transient Index objects would accumulate.
        core.db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_audit_at ON audit (at)'))
        core.db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_audit_family_at ON audit (family_id, at)'))
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
        user_id = session.get('user_id')
        if not user_id:
            return None, None
        user = core.db.session.get(core.StaffUser, user_id)
        if not user:
            return None, None
        cursor = core.db.session.get(StaffActivityCursor, user.id)
        if cursor is None:
            # A missing cursor is a read-only fallback on page navigation.
            # The explicit mark-read POST persists it when the user acts.
            cursor = StaffActivityCursor(
                staff_user_id=user.id,
                last_seen_at=user.last_login_at or user.activated_at or _now())
        return user, cursor

    def audit_filters(user, since):
        filters = [
            core.Audit.at > since,
            ~select(StaffActivityRead.audit_id).where(
                StaffActivityRead.staff_user_id == user.id,
                StaffActivityRead.audit_id == core.Audit.id).exists(),
        ]
        if user.role != 'organization_admin':
            filters.append(select(core.FamilyAssignment.family_id).where(
                core.FamilyAssignment.staff_user_id == user.id,
                core.FamilyAssignment.family_id == core.Audit.family_id).exists())
        return filters

    def audit_statement(user, since):
        return select(core.Audit).where(*audit_filters(user, since))

    def unread_count(user):
        cached = unread_cache.get(user.id)
        now = time.monotonic()
        if cached is not None and now - cached[0] < unread_cache_seconds:
            return cached[1]
        # Read the cursor as part of the count query rather than issuing a
        # second SELECT. The result is reused briefly across page requests so
        # the audit table is not scanned for every ordinary navigation.
        last_seen = select(StaffActivityCursor.last_seen_at).where(
            StaffActivityCursor.staff_user_id == user.id).scalar_subquery()
        since = func.coalesce(
            last_seen, user.last_login_at or user.activated_at or _now())
        count = core.db.session.scalar(select(func.count(core.Audit.id)).where(
            *audit_filters(user, since))) or 0
        unread_cache[user.id] = (now, count)
        return count

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
        sponsorship_match = re.fullmatch(
            r'Updated (\d{4}-(?:0[1-9]|1[0-2])) sponsorship for (.+)',
            row.action)
        if sponsorship_match:
            month, page_label = sponsorship_match.groups()
            from sponsorships import PAGE_SLOTS
            page_key = next((key for key, label in PAGE_SLOTS
                             if label == page_label), None)
            if page_key:
                return url_for('sponsorship_edit', page_key=page_key, month=month)

        # Resolve the source object named by older audit rows. A notification
        # click must open the work it describes, never a generic dashboard.
        follow_up_match = re.fullmatch(
            r'Created automatic supporter follow-up: (.+)', row.action)
        if follow_up_match:
            from app import StaffTask
            supporter_name = follow_up_match.group(1).strip()
            task = core.db.session.scalar(
                select(StaffTask)
                .join(core.Contact, StaffTask.source_contact_id == core.Contact.id)
                .where(core.Contact.name == supporter_name)
                .order_by(StaffTask.id.desc())
                .limit(1))
            if task:
                return url_for('task_detail', task_id=task.id)
            contact = core.db.session.scalar(
                select(core.Contact).where(core.Contact.name == supporter_name)
                .order_by(core.Contact.id.desc()).limit(1))
            if contact:
                return url_for('supporter_detail', contact_id=contact.id)

        askan_match = re.fullmatch(r'Updated askan network profile: (.+)', row.action)
        if askan_match:
            askan = core.db.session.scalar(
                select(core.Askan).where(core.Askan.name == askan_match.group(1).strip())
                .order_by(core.Askan.id.desc()).limit(1))
            if askan:
                return url_for('network_askan_detail', askan_id=askan.id)

        if any(word in lowered for word in ('message', 'email', 'replied')):
            return url_for('communications', _anchor='general-inbox')
        if any(word in lowered for word in ('receipt', 'donation', 'pledge', 'stripe')):
            if row.family_id:
                return url_for('family_detail', family_id=row.family_id)
            return url_for('collections')
        if 'expense' in lowered:
            return url_for('expenses')
        if 'payout' in lowered or 'check' in lowered:
            return url_for('payouts')
        if 'task' in lowered:
            return url_for('tasks')
        if row.family_id:
            return url_for('family_detail', family_id=row.family_id)
        # Unknown legacy audit rows remain in What's new rather than lying
        # about their destination by sending staff to the dashboard.
        return url_for('notifications')

    @app.context_processor
    def notification_context():
        if not session.get('user_id'):
            return {'new_activity_count': 0}
        if app.config.get('DEMO'):
            return {'new_activity_count': 0}
        if hasattr(g, '_yazory_unread_activity_count'):
            return {'new_activity_count': g._yazory_unread_activity_count}
        user = core.db.session.get(core.StaffUser, session.get('user_id'))
        if not user:
            return {'new_activity_count': 0}
        count = unread_count(user)
        g._yazory_unread_activity_count = count
        return {'new_activity_count': count}

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
        for provider in app.extensions.get('notification_item_providers', ()):
            items.extend(provider(user, cursor.last_seen_at))
        items.sort(key=lambda item: item['at'], reverse=True)
        return render_template('notifications.html', title='What’s new', items=items,
                               unread_count=len(items), since=cursor.last_seen_at)

    @app.post('/notifications/<int:audit_id>/open')
    def notification_open(audit_id):
        user, cursor = user_and_cursor()
        if not user:
            abort(403)
        statement = select(core.Audit).where(core.Audit.id == audit_id)
        if user.role != 'organization_admin':
            statement = statement.where(select(core.FamilyAssignment.family_id).where(
                core.FamilyAssignment.staff_user_id == user.id,
                core.FamilyAssignment.family_id == core.Audit.family_id).exists())
        row = core.db.session.scalar(statement)
        if row is None:
            abort(404)
        if row.at > cursor.last_seen_at and core.db.session.get(
                StaffActivityRead, (user.id, row.id)) is None:
            core.db.session.add(StaffActivityRead(
                staff_user_id=user.id, audit_id=row.id, read_at=_now()))
            core.db.session.commit()
            invalidate_unread(user.id)
        return redirect(activity_url(row))

    @app.post('/notifications/mark-read')
    def notifications_mark_read():
        user, cursor = user_and_cursor()
        if not user:
            abort(403)
        if cursor not in core.db.session:
            core.db.session.add(cursor)
        cursor.last_seen_at = _now()
        # This write belongs to the explicit POST action; ordinary page views
        # never create the missing cursor as a side effect.
        core.db.session.add(cursor)
        core.db.session.commit()
        invalidate_unread(user.id)
        return redirect(url_for('notifications'))
