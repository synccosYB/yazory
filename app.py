import os
import re

import app_original as _app
from sqlalchemy import UniqueConstraint, select

# Keep the established application intact while extending the supporter
# relationship choices with a distinct shul-friend option.
if 'Shul friend' not in _app.RELATIONSHIPS:
    insert_at = _app.RELATIONSHIPS.index('Friend') if 'Friend' in _app.RELATIONSHIPS else len(_app.RELATIONSHIPS)
    _app.RELATIONSHIPS.insert(insert_at, 'Shul friend')


class ShulRabbi(_app.db.Model):
    """Exactly one rabbi assignment for a shared shul record."""
    __tablename__ = 'shul_rabbi'
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), primary_key=True)
    rabbi_name = _app.db.Column(_app.db.String(160), nullable=False, default='')
    rabbi_phone = _app.db.Column(_app.db.String(80), nullable=False, default='')
    institution = _app.db.relationship('Institution')


class FamilyRabbiConnection(_app.db.Model):
    """A family may have separate affiliated, weekday-shul, and Shabbos-shul rabbis."""
    __tablename__ = 'family_rabbi_connection'
    __table_args__ = (
        UniqueConstraint('family_id', 'role', name='uq_family_rabbi_connection_role'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    family_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('family.id'), nullable=False, index=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=True, index=True)
    role = _app.db.Column(_app.db.String(30), nullable=False)
    rabbi_name = _app.db.Column(_app.db.String(160), nullable=False, default='')
    rabbi_phone = _app.db.Column(_app.db.String(80), nullable=False, default='')
    institution = _app.db.relationship('Institution')


from app_original import *  # noqa: F401,F403,E402
from native_payments import register_native_payments  # noqa: E402


def _submitted_institution_name(key):
    value = _app.request.form.get(key, '').strip()
    if value == '__new__':
        value = _app.request.form.get(key + '_new', '').strip()
    return value[:160]


def _family_id_from_response(response):
    location = getattr(response, 'location', None) or response.headers.get('Location', '')
    match = re.search(r'/families/(\d+)(?:$|[/?#])', location)
    return int(match.group(1)) if match else None


def _upsert_family_rabbi(family_id, role, institution, rabbi_name, rabbi_phone):
    row = _app.db.session.scalar(select(FamilyRabbiConnection).where(
        FamilyRabbiConnection.family_id == family_id,
        FamilyRabbiConnection.role == role))
    if not rabbi_name:
        if row is not None:
            _app.db.session.delete(row)
        return
    if row is None:
        row = FamilyRabbiConnection(family_id=family_id, role=role)
        _app.db.session.add(row)
    row.institution_id = institution.id if institution else None
    row.rabbi_name = rabbi_name
    row.rabbi_phone = rabbi_phone


def _save_shul_rabbi_connections(family_id):
    family = _app.db.session.get(_app.Family, family_id)
    if family is None:
        return

    # Preserve the existing general family-rabbi relationship as one of the
    # applicant's possible rabbi connections.
    _upsert_family_rabbi(
        family_id, 'affiliated', None, family.rabbi or '', family.rabbi_phone or '')

    submitted = []
    for role, key in (('weekday_shul', 'weekday_shul'), ('shabbos_shul', 'shabbos_shul')):
        shul_name = _submitted_institution_name(key)
        if not shul_name:
            _upsert_family_rabbi(family_id, role, None, '', '')
            continue
        institution = _app.db.session.scalar(select(_app.Institution).where(
            _app.Institution.kind == 'Shul', _app.Institution.name == shul_name).order_by(_app.Institution.id))
        rabbi_name = _app.request.form.get(key + '_rabbi', '').strip()[:160]
        rabbi_phone = _app.request.form.get(key + '_rabbi_phone', '').strip()[:80]
        submitted.append((role, institution, rabbi_name, rabbi_phone))

    # One shul has one rabbi. If the same shul is selected twice, use the first
    # entered assignment for both family roles rather than creating two rabbis.
    assignments = {}
    for role, institution, rabbi_name, rabbi_phone in submitted:
        if institution is None:
            _upsert_family_rabbi(family_id, role, None, rabbi_name, rabbi_phone)
            continue
        existing = _app.db.session.get(ShulRabbi, institution.id)
        chosen = assignments.get(institution.id)
        if chosen is None:
            if rabbi_name:
                chosen = (rabbi_name, rabbi_phone)
            elif existing is not None:
                chosen = (existing.rabbi_name, existing.rabbi_phone)
            else:
                chosen = ('', '')
            assignments[institution.id] = chosen
        rabbi_name, rabbi_phone = chosen
        if rabbi_name:
            if existing is None:
                existing = ShulRabbi(institution_id=institution.id)
                _app.db.session.add(existing)
            existing.rabbi_name = rabbi_name
            existing.rabbi_phone = rabbi_phone
        _upsert_family_rabbi(family_id, role, institution, rabbi_name, rabbi_phone)

    _app.db.session.commit()


def create_app(test_config=None):
    app = _app.create_app(test_config)

    @app.context_processor
    def shul_rabbi_context():
        rows = _app.db.session.execute(select(_app.Institution, ShulRabbi).join(
            ShulRabbi, ShulRabbi.institution_id == _app.Institution.id, isouter=True).where(
            _app.Institution.kind == 'Shul')).all()
        return {
            'shul_rabbi_map': {
                institution.name: {
                    'name': assignment.rabbi_name if assignment else '',
                    'phone': assignment.rabbi_phone if assignment else '',
                }
                for institution, assignment in rows
            }
        }

    for endpoint in ('new_family', 'edit_family'):
        original = app.view_functions.get(endpoint)
        if original is None:
            continue

        def wrapped(*args, __original=original, __endpoint=endpoint, **kwargs):
            response = app.make_response(__original(*args, **kwargs))
            if _app.request.method == 'POST' and response.status_code < 400:
                family_id = kwargs.get('family_id') if __endpoint == 'edit_family' else _family_id_from_response(response)
                if family_id:
                    _save_shul_rabbi_connections(int(family_id))
            return response

        app.view_functions[endpoint] = wrapped

    return register_native_payments(app)


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
