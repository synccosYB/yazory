import os
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import jsonify
from sqlalchemy import func, select

import app as _base
import app_original as _app


def _family_denial_reason(family):
    record = _app.db.session.get(_app.HouseholdIntake, family.id) if family.id else None
    return ((record.data or {}).get('denial_reason', '') if record else '')


def _set_family_denial_reason(family, value):
    record = _app.db.session.get(_app.HouseholdIntake, family.id) if family.id else None
    if record is None:
        record = _app.HouseholdIntake(family_id=family.id, data={})
        _app.db.session.add(record)
    record.data = {**(record.data or {}), 'denial_reason': value or ''}


# Denial metadata belongs to the intake record so this additive feature does
# not require altering the core family table on existing installations.
_app.Family.denial_reason = property(
    _family_denial_reason, _set_family_denial_reason)


def create_app(test_config=None):
    app = _base.create_app(test_config)

    original_family_status = app.view_functions['family_status']

    def family_status_with_reason(family_id):
        status = _app.request.form.get('status', '').strip()
        if app.extensions['workflows']['enforced']():
            return original_family_status(family_id)
        reason = _app.request.form.get('denial_reason', '').strip()
        if status == 'Declined' and not reason:
            _app.abort(400, 'A reason is required when declining a case.')
        response = original_family_status(family_id)
        family = _app.db.session.get(_app.Family, family_id)
        family.denial_reason = reason if status == 'Declined' else ''
        if reason:
            _app.db.session.add(_app.Audit(
                actor=(current_user().email if current_user() else 'System'),
                action=f'Case denial reason: {reason}', family_id=family_id))
        _app.db.session.commit()
        return response

    app.view_functions['family_status'] = family_status_with_reason
    app.config.setdefault(
        'ENABLE_DB_DIAGNOSTIC',
        os.environ.get('ENABLE_DB_DIAGNOSTIC', '').strip().lower() in ('1', 'true', 'yes'),
    )

    workflows = app.extensions.get('workflows', {})
    financials = workflows.get('financials')
    approved = workflows.get('approved')
    models = workflows.get('models', {})
    Work = models.get('WorkItem')

    def current_user():
        uid = _app.session.get('user_id')
        return _app.db.session.get(_app.StaffUser, uid) if uid else None

    def can_access_family(user, family_id):
        if not user:
            return False
        if user.role == 'organization_admin':
            return True
        return bool(_app.db.session.scalar(select(_app.FamilyAssignment.id).where(
            _app.FamilyAssignment.staff_user_id == user.id,
            _app.FamilyAssignment.family_id == family_id,
        )))

    def require_report_access(family_id=None):
        user = current_user()
        if not user or user.role in ('fundraiser', 'office_employee'):
            _app.abort(403)
        if family_id is not None and not can_access_family(user, family_id):
            _app.abort(403)
        return user

    def case_monthly_pledged(fid=None, user=None, family_ids=None):
        if fid is not None:
            target_ids = [fid]
        elif family_ids is not None:
            target_ids = list(family_ids)
        else:
            target_ids = list(_app.db.session.scalars(select(_app.Family.id)))
        if not target_ids:
            return 0

        contacts = list(_app.db.session.scalars(select(_app.Contact).where(
            _app.Contact.family_id.in_(target_ids))))
        contact_by_id = {contact.id: contact for contact in contacts}
        today = date.today().isoformat()
        workflow_amounts = {}

        if Work is not None:
            query = select(Work).where(
                Work.kind == 'pledge',
                Work.disposition == 'Complete',
                Work.family_id.in_(target_ids),
            ).order_by(Work.id)
            for item in _app.db.session.scalars(query):
                frequency = item.data.get('frequency')
                if frequency not in ('Monthly', 'Weekly'):
                    continue
                start = item.data.get('start') or ''
                end = item.data.get('end') or ''
                if start and today < start:
                    continue
                if end and today > end:
                    continue
                contact_id = item.data.get('contact_id')
                contact = contact_by_id.get(contact_id)
                if contact is None or contact.family_id != item.family_id:
                    continue
                if user and user.role == 'fundraiser':
                    Link = models.get('SupporterLink')
                    link = _app.db.session.get(Link, contact.id) if Link else None
                    if not link or link.assigned_to != user.id:
                        continue
                amount = item.data.get('amount', 0)
                if frequency == 'Weekly':
                    amount = round(amount * 52 / 12)
                workflow_amounts[(item.family_id, contact.id)] = amount

        total = sum(workflow_amounts.values())
        covered = set(workflow_amounts)
        for contact in contacts:
            key = (contact.family_id, contact.id)
            if key in covered or contact.status != 'Pledged':
                continue
            if user and user.role == 'fundraiser':
                Link = models.get('SupporterLink')
                link = _app.db.session.get(Link, contact.id) if Link else None
                if not link or link.assigned_to != user.id:
                    continue
            total += contact.monthly_equivalent_cents
        return total

    if workflows:
        workflows['monthly_pledged'] = case_monthly_pledged
    monthly_pledged = case_monthly_pledged

    def manual_shortfall(family_id):
        record = _app.db.session.get(_app.HouseholdBudget, family_id)
        if not record:
            return None
        value = (record.data or {}).get('manual_shortfall_cents')
        return value if isinstance(value, int) and value >= 0 else None

    @app.get('/admin/db-diagnostic')
    def live_db_diagnostic():
        if not app.config['ENABLE_DB_DIAGNOSTIC']:
            _app.abort(404)
        user = current_user()
        if not user or user.role != 'organization_admin':
            _app.abort(403)
        family_id = _app.request.args.get('family_id', 2, type=int)
        uri = app.config.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL', '')
        safe_uri = uri.replace('postgresql+psycopg://', 'postgresql://', 1).replace('postgres://', 'postgresql://', 1)
        parsed = urlparse(safe_uri)
        family = _app.db.session.get(_app.Family, family_id)
        contacts = list(_app.db.session.scalars(select(_app.Contact).where(
            _app.Contact.family_id == family_id).order_by(_app.Contact.id)))
        pledge_rows = []
        if Work is not None:
            for item in _app.db.session.scalars(select(Work).where(
                    Work.family_id == family_id,
                    Work.kind == 'pledge').order_by(Work.id)):
                pledge_rows.append({
                    'id': item.id,
                    'stage': item.stage,
                    'disposition': item.disposition,
                    'contact_id': item.data.get('contact_id'),
                    'amount_cents': item.data.get('amount'),
                    'frequency': item.data.get('frequency'),
                    'start': item.data.get('start'),
                    'end': item.data.get('end'),
                })
        return jsonify({
            'database': {'host': parsed.hostname, 'name': parsed.path.lstrip('/')},
            'counts': {
                'families': _app.db.session.scalar(select(func.count()).select_from(_app.Family)),
                'contacts': _app.db.session.scalar(select(func.count()).select_from(_app.Contact)),
            },
            'family': None if family is None else {'id': family.id, 'name': family.name, 'status': family.status},
            'contacts': [{
                'id': contact.id,
                'name': contact.name,
                'status': contact.status,
                'monthly_cents': contact.monthly_cents,
                'frequency': contact.pledge_frequency,
                'supporter_key_present': bool(contact.supporter_key),
            } for contact in contacts],
            'pledge_workflows': pledge_rows,
            'calculated_monthly_pledged_cents': case_monthly_pledged(family_id),
        })

    @app.post('/operations/reports/<int:family_id>/shortfall')
    def update_report_shortfall(family_id):
        user = require_report_access(family_id)
        family = _app.db.get_or_404(_app.Family, family_id)
        raw = _app.request.form.get('monthly_shortfall', '').strip().replace(',', '').replace('$', '')
        try:
            amount = Decimal(raw)
            if not amount.is_finite() or amount < 0 or amount > 1000000 or amount.as_tuple().exponent < -2:
                raise ValueError
            cents = int(amount * 100)
        except (InvalidOperation, ValueError):
            _app.flash('Enter a valid monthly shortfall.', 'error')
            return _app.redirect(_app.url_for('operating_reports'))
        record = _app.db.session.get(_app.HouseholdBudget, family_id)
        if record is None:
            record = _app.HouseholdBudget(family_id=family_id, data={})
            _app.db.session.add(record)
        before = (record.data or {}).get('manual_shortfall_cents')
        record.data = {**(record.data or {}), 'manual_shortfall_cents': cents}
        _app.db.session.add(_app.Audit(actor=user.email, action=f'Updated report monthly shortfall for {family.name}: {before} -> {cents}'))
        _app.db.session.commit()
        _app.flash('Monthly shortfall saved.', 'success')
        return _app.redirect(_app.url_for('operating_reports'))

    def operating_reports_override():
        user = require_report_access()
        families = [f for f in _app.db.session.scalars(select(_app.Family).order_by(_app.Family.name)) if can_access_family(user, f.id)]
        rows = []
        for family in families:
            row = financials(family.id)
            row['family'] = family
            row['pledged'] = monthly_pledged(family.id)
            assessment = approved('assessment', family.id)
            entered = manual_shortfall(family.id)
            row['gap'] = entered if entered is not None else (assessment.data['gap'] if assessment else None)
            row['gap_manual'] = entered is not None
            row['goal'] = assessment.data['goal'] if assessment else None
            plan = approved('support_plan', family.id)
            review = approved('review', family.id)
            row['review_date'] = (review.data['review_date'] if review and plan and review.data.get('plan_id') == plan.id else plan.data['review_date'] if plan else None)
            row['due_reviews'] = bool(row['review_date'] and row['review_date'] < date.today().isoformat())
            row['failed'] = _app.db.session.scalar(select(func.count()).select_from(Work).where(
                Work.family_id == family.id,
                Work.kind == 'collection',
                Work.disposition == 'Failed',
            ))
            rows.append(row)
        totals = {k: sum(r[k] for r in rows) for k in [
            'collected', 'assistance', 'overhead', 'balance', 'reserved', 'available',
            'protected_reserve', 'pledged', 'unmatched', 'failed'
        ]}
        return _app.render_template('operating_reports.html', title='Organization-wide report', rows=rows, totals=totals)

    app.view_functions['operating_reports'] = operating_reports_override
    return app
