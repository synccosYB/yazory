import os
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import jsonify
from sqlalchemy import func, select

import app as _base
import app_original as _app


def create_app(test_config=None):
    app = _base.create_app(test_config)

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

    def pledge_snapshot(contact_id):
        contact = _app.db.session.get(_app.Contact, contact_id)
        if contact is None or not contact.supporter_key:
            return {}
        return {
            row.id: (row.status, row.monthly_cents, row.pledge_frequency)
            for row in _app.db.session.scalars(select(_app.Contact).where(
                _app.Contact.supporter_key == contact.supporter_key))
            if row.id != contact.id
        }

    def restore_other_case_pledges(snapshot):
        for contact_id, values in snapshot.items():
            row = _app.db.session.get(_app.Contact, contact_id)
            if row is not None:
                row.status, row.monthly_cents, row.pledge_frequency = values

    original_update_contact = app.view_functions.get('update_contact')
    if original_update_contact:
        def update_contact_case_specific(contact_id):
            snapshot = pledge_snapshot(contact_id)
            submitted_status = _app.request.form.get('status', '').strip()
            submitted_frequency = _app.request.form.get('pledge_frequency', '').strip() or 'Monthly'
            submitted_monthly = _app.request.form.get('monthly', '').strip().replace(',', '').replace('$', '')
            response = original_update_contact(contact_id)
            restore_other_case_pledges(snapshot)
            row = _app.db.session.get(_app.Contact, contact_id)
            if row is not None:
                try:
                    cents = int(Decimal(submitted_monthly) * 100) if submitted_monthly else row.monthly_cents
                except (InvalidOperation, ValueError):
                    cents = row.monthly_cents
                if submitted_status in _app.CONTACT_STATUSES:
                    row.status = submitted_status
                if submitted_frequency in _app.PLEDGE_FREQUENCIES:
                    row.pledge_frequency = submitted_frequency
                row.monthly_cents = cents
            _app.db.session.commit()
            return response
        app.view_functions['update_contact'] = update_contact_case_specific

    original_edit_contact = app.view_functions.get('edit_contact')
    if original_edit_contact:
        def edit_contact_case_specific(contact_id):
            snapshot = pledge_snapshot(contact_id) if _app.request.method == 'POST' else {}
            response = original_edit_contact(contact_id)
            if snapshot:
                restore_other_case_pledges(snapshot)
                _app.db.session.commit()
            return response
        app.view_functions['edit_contact'] = edit_contact_case_specific

    original_add_contact = app.view_functions.get('add_contact')
    if original_add_contact:
        def add_contact_case_specific(family_id=None):
            target_family = family_id or _app.request.form.get('family_id', type=int)
            before_ids = set(_app.db.session.scalars(select(_app.Contact.id).where(
                _app.Contact.family_id == target_family))) if target_family else set()
            submitted_status = _app.request.form.get('status', '').strip()
            submitted_frequency = _app.request.form.get('pledge_frequency', '').strip() or 'Monthly'
            submitted_monthly = _app.request.form.get('monthly', '').strip().replace(',', '').replace('$', '')
            response = original_add_contact(family_id)
            if target_family:
                new_contacts = list(_app.db.session.scalars(select(_app.Contact).where(
                    _app.Contact.family_id == target_family,
                    _app.Contact.id.notin_(before_ids),
                ).order_by(_app.Contact.id.desc())))
                if new_contacts:
                    row = new_contacts[0]
                    try:
                        cents = int(Decimal(submitted_monthly) * 100) if submitted_monthly else 0
                    except (InvalidOperation, ValueError):
                        cents = row.monthly_cents
                    if submitted_status in _app.CONTACT_STATUSES:
                        row.status = submitted_status
                    if submitted_frequency in _app.PLEDGE_FREQUENCIES:
                        row.pledge_frequency = submitted_frequency
                    row.monthly_cents = cents
                    _app.db.session.commit()
            return response
        app.view_functions['add_contact'] = add_contact_case_specific

    # Narrow one-time cleanup for the exact linked supporter rows observed in production.
    # Family 2 / contact 33 owns the $10 monthly pledge. Family 1 / contact 31 is
    # merely the same supporter identity and must not inherit that amount.
    with app.app_context():
        pledged = _app.db.session.get(_app.Contact, 33)
        other = _app.db.session.get(_app.Contact, 31)
        changed = False
        if (pledged and pledged.family_id == 2 and pledged.monthly_cents == 1000
                and pledged.pledge_frequency == 'Monthly'):
            if pledged.status == 'To contact':
                pledged.status = 'Pledged'
                changed = True
            if (other and other.family_id == 1 and other.supporter_key
                    and other.supporter_key == pledged.supporter_key
                    and other.status == 'To contact' and other.monthly_cents == 1000):
                other.monthly_cents = 0
                other.pledge_frequency = 'Monthly'
                changed = True
        if changed:
            _app.db.session.commit()

    def manual_shortfall(family_id):
        record = _app.db.session.get(_app.HouseholdBudget, family_id)
        if not record:
            return None
        value = (record.data or {}).get('manual_shortfall_cents')
        return value if isinstance(value, int) and value >= 0 else None

    @app.get('/admin/db-diagnostic')
    def live_db_diagnostic():
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