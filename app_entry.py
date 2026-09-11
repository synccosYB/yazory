from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

import app as _base
import app_original as _app


def create_app(test_config=None):
    app = _base.create_app(test_config)

    workflows = app.extensions.get('workflows', {})
    financials = workflows.get('financials')
    original_monthly_pledged = workflows.get('monthly_pledged')
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
        """Return commitments by case, never by shared supporter identity.

        One real person may be connected to several families, but a promise to one
        family is not a promise to every family. Completed pledge workflows are
        authoritative when present; older case-level Contact pledges remain visible
        as a fallback so existing commitments do not disappear from the profile.
        """
        if Work is None:
            return original_monthly_pledged(fid=fid, user=user, family_ids=family_ids) \
                if original_monthly_pledged else 0

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
        shared_keys = {contact.supporter_key for contact in contacts if contact.supporter_key}
        aliases = list(_app.db.session.scalars(select(_app.Contact).where(
            _app.Contact.supporter_key.in_(shared_keys)))) if shared_keys else []
        # Always include the target case contacts themselves. A legacy contact may
        # have no supporter_key yet and its valid case pledge must still count.
        alias_by_id = dict(contact_by_id)
        alias_by_id.update({contact.id: contact for contact in aliases})
        today = date.today().isoformat()
        workflow_amounts = {}
        supporter_keys_with_workflow = set()

        # Look at all completed pledges for these shared people, not only the
        # requested family. This lets us distinguish a real case pledge from an
        # old copied Contact status left behind by the former shared-pledge bug.
        query = select(Work).where(
            Work.kind == 'pledge',
            Work.disposition == 'Complete',
        ).order_by(Work.id)
        for item in _app.db.session.scalars(query):
            frequency = item.data.get('frequency')
            if frequency not in ('Monthly', 'Weekly'):
                continue
            # A completed pledge remains valid when no explicit date bound was
            # entered. Apply start/end only when that bound actually exists.
            start = item.data.get('start') or ''
            end = item.data.get('end') or ''
            if start and today < start:
                continue
            if end and today > end:
                continue
            contact_id = item.data.get('contact_id')
            alias = alias_by_id.get(contact_id)
            if alias is None:
                continue
            if alias.supporter_key:
                supporter_keys_with_workflow.add(alias.supporter_key)
            if alias.family_id not in target_ids or item.family_id != alias.family_id:
                continue
            if user and user.role == 'fundraiser':
                Link = models.get('SupporterLink')
                link = _app.db.session.get(Link, alias.id) if Link else None
                if not link or link.assigned_to != user.id:
                    continue
            amount = item.data.get('amount', 0)
            if frequency == 'Weekly':
                amount = round(amount * 52 / 12)
            # Latest active completed pledge for this contact/case wins.
            workflow_amounts[(item.family_id, alias.id)] = amount

        total = sum(workflow_amounts.values())
        covered = set(workflow_amounts)
        for contact in contacts:
            key = (contact.family_id, contact.id)
            if key in covered or contact.status != 'Pledged':
                continue
            # If this shared person has a real workflow pledge somewhere, do not
            # trust a legacy copied Contact pledge on another family. Only that
            # family's own workflow may count there.
            if contact.supporter_key and contact.supporter_key in supporter_keys_with_workflow:
                continue
            if user and user.role == 'fundraiser':
                Link = models.get('SupporterLink')
                link = _app.db.session.get(Link, contact.id) if Link else None
                if not link or link.assigned_to != user.id:
                    continue
            total += contact.monthly_equivalent_cents
        return total

    # Replace the workflow total everywhere (family profile and reports). The
    # shared supporter key remains useful for charging one person once, but it
    # must never merge commitments belonging to different family cases.
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
        if not snapshot:
            return
        changed = False
        for contact_id, values in snapshot.items():
            row = _app.db.session.get(_app.Contact, contact_id)
            if row is None:
                continue
            row.status, row.monthly_cents, row.pledge_frequency = values
            changed = True
        if changed:
            _app.db.session.commit()

    original_update_contact = app.view_functions.get('update_contact')
    if original_update_contact:
        def update_contact_case_specific(contact_id):
            snapshot = pledge_snapshot(contact_id)
            response = original_update_contact(contact_id)
            restore_other_case_pledges(snapshot)
            return response
        app.view_functions['update_contact'] = update_contact_case_specific

    original_edit_contact = app.view_functions.get('edit_contact')
    if original_edit_contact:
        def edit_contact_case_specific(contact_id):
            snapshot = pledge_snapshot(contact_id) if _app.request.method == 'POST' else {}
            response = original_edit_contact(contact_id)
            restore_other_case_pledges(snapshot)
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
                    # The legacy route used to overwrite these three fields from
                    # another case sharing the same supporter_key. Preserve what
                    # was actually entered for this case instead.
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

    def manual_shortfall(family_id):
        record = _app.db.session.get(_app.HouseholdBudget, family_id)
        if not record:
            return None
        value = (record.data or {}).get('manual_shortfall_cents')
        return value if isinstance(value, int) and value >= 0 else None

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
        _app.db.session.add(_app.Audit(
            actor=user.email,
            action=f'Updated report monthly shortfall for {family.name}: {before} -> {cents}',
        ))
        _app.db.session.commit()
        _app.flash('Monthly shortfall saved.', 'success')
        return _app.redirect(_app.url_for('operating_reports'))

    def operating_reports_override():
        user = require_report_access()
        families = [f for f in _app.db.session.scalars(select(_app.Family).order_by(_app.Family.name))
                    if can_access_family(user, f.id)]
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
            row['review_date'] = (review.data['review_date']
                                  if review and plan and review.data.get('plan_id') == plan.id
                                  else plan.data['review_date'] if plan else None)
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
