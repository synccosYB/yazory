from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

import app as _base
import app_original as _app


def create_app(test_config=None):
    app = _base.create_app(test_config)

    workflows = app.extensions.get('workflows', {})
    financials = workflows.get('financials')
    monthly_pledged = workflows.get('monthly_pledged')
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
