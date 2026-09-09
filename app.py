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


class ShulGabbaiDirectory(_app.db.Model):
    """A shul can have multiple gabbaim, each stored once on the shul itself."""
    __tablename__ = 'shul_gabbai_directory'
    __table_args__ = (
        UniqueConstraint('institution_id', 'name', 'phone', name='uq_shul_gabbai_identity'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=False, index=True)
    name = _app.db.Column(_app.db.String(160), nullable=False)
    phone = _app.db.Column(_app.db.String(80), nullable=False, default='')
    institution = _app.db.relationship('Institution')


class FamilyGabbaiConnection(_app.db.Model):
    """An applicant inherits all gabbaim from each selected shul."""
    __tablename__ = 'family_gabbai_connection'
    __table_args__ = (
        UniqueConstraint('family_id', 'role', 'gabbai_id', name='uq_family_gabbai_connection'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    family_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('family.id'), nullable=False, index=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=False, index=True)
    gabbai_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('shul_gabbai_directory.id'), nullable=False, index=True)
    role = _app.db.Column(_app.db.String(30), nullable=False)
    gabbai = _app.db.relationship('ShulGabbaiDirectory')
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


def _find_shul(shul_name):
    if not shul_name:
        return None
    return _app.db.session.scalar(select(_app.Institution).where(
        _app.Institution.kind == 'Shul',
        _app.Institution.name == shul_name).order_by(_app.Institution.id))


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

    _upsert_family_rabbi(
        family_id, 'affiliated', None, family.rabbi or '', family.rabbi_phone or '')

    submitted = []
    for role, key in (('weekday_shul', 'weekday_shul'), ('shabbos_shul', 'shabbos_shul')):
        shul_name = _submitted_institution_name(key)
        if not shul_name:
            _upsert_family_rabbi(family_id, role, None, '', '')
            continue
        institution = _find_shul(shul_name)
        rabbi_name = _app.request.form.get(key + '_rabbi', '').strip()[:160]
        rabbi_phone = _app.request.form.get(key + '_rabbi_phone', '').strip()[:80]
        submitted.append((role, institution, rabbi_name, rabbi_phone))

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


def _submitted_gabbais(key):
    names = _app.request.form.getlist(key + '_gabbai_name')
    phones = _app.request.form.getlist(key + '_gabbai_phone')
    rows = []
    seen = set()
    for index, raw_name in enumerate(names):
        name = raw_name.strip()[:160]
        phone = (phones[index].strip() if index < len(phones) else '')[:80]
        if not name:
            continue
        identity = (name.casefold(), phone)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append((name, phone))
    return rows


def _replace_shul_gabbais(institution, submitted_rows):
    current = _app.db.session.scalars(select(ShulGabbaiDirectory).where(
        ShulGabbaiDirectory.institution_id == institution.id).order_by(ShulGabbaiDirectory.id)).all()
    existing_by_identity = {(row.name.casefold(), row.phone): row for row in current}
    keep_ids = set()
    result = []
    for name, phone in submitted_rows:
        identity = (name.casefold(), phone)
        row = existing_by_identity.get(identity)
        if row is None:
            row = ShulGabbaiDirectory(institution_id=institution.id, name=name, phone=phone)
            _app.db.session.add(row)
            _app.db.session.flush()
        keep_ids.add(row.id)
        result.append(row)
    for row in current:
        if row.id not in keep_ids:
            linked = _app.db.session.scalar(select(FamilyGabbaiConnection.id).where(
                FamilyGabbaiConnection.gabbai_id == row.id))
            if not linked:
                _app.db.session.delete(row)
    return result


def _sync_family_gabbais(family_id, role, institution, gabbais):
    current = _app.db.session.scalars(select(FamilyGabbaiConnection).where(
        FamilyGabbaiConnection.family_id == family_id,
        FamilyGabbaiConnection.role == role)).all()
    desired_ids = {gabbai.id for gabbai in gabbais} if institution is not None else set()
    existing_by_gabbai = {row.gabbai_id: row for row in current}

    # Keep existing links that still belong to the selected shul. This makes
    # repeated profile saves idempotent and avoids delete/reinsert collisions on
    # the unique (family, role, gabbai) key.
    for row in current:
        if row.gabbai_id not in desired_ids:
            _app.db.session.delete(row)
        elif institution is not None:
            row.institution_id = institution.id

    if institution is None:
        return
    for gabbai in gabbais:
        if gabbai.id not in existing_by_gabbai:
            _app.db.session.add(FamilyGabbaiConnection(
                family_id=family_id, institution_id=institution.id,
                gabbai_id=gabbai.id, role=role))


def _save_shul_gabbai_connections(family_id):
    # If weekday and Shabbos use the same shul, keep one canonical gabbai list
    # for that shul and attach that same list to both applicant roles.
    submitted_by_institution = {}
    role_rows = []
    for role, key in (('weekday_shul', 'weekday_shul'), ('shabbos_shul', 'shabbos_shul')):
        shul_name = _submitted_institution_name(key)
        institution = _find_shul(shul_name)
        submitted = _submitted_gabbais(key)
        if institution is not None and institution.id not in submitted_by_institution:
            if submitted:
                submitted_by_institution[institution.id] = submitted
            else:
                submitted_by_institution[institution.id] = [
                    (row.name, row.phone) for row in _app.db.session.scalars(
                        select(ShulGabbaiDirectory).where(
                            ShulGabbaiDirectory.institution_id == institution.id
                        ).order_by(ShulGabbaiDirectory.id)).all()
                ]
        role_rows.append((role, institution))

    saved_by_institution = {}
    for institution_id, rows in submitted_by_institution.items():
        institution = _app.db.session.get(_app.Institution, institution_id)
        saved_by_institution[institution_id] = _replace_shul_gabbais(institution, rows)

    for role, institution in role_rows:
        gabbais = saved_by_institution.get(institution.id, []) if institution else []
        _sync_family_gabbais(family_id, role, institution, gabbais)


def _save_shul_connections(family_id):
    _save_shul_rabbi_connections(family_id)
    _save_shul_gabbai_connections(family_id)
    _app.db.session.commit()


def create_app(test_config=None):
    app = _app.create_app(test_config)

    @app.get('/api/shul-rabbis')
    def shul_rabbis_api():
        rows = _app.db.session.execute(select(_app.Institution, ShulRabbi).join(
            ShulRabbi, ShulRabbi.institution_id == _app.Institution.id, isouter=True).where(
            _app.Institution.kind == 'Shul')).all()
        return {
            institution.name: {
                'name': assignment.rabbi_name if assignment else '',
                'phone': assignment.rabbi_phone if assignment else '',
            }
            for institution, assignment in rows
        }

    @app.get('/api/shul-gabbais')
    def shul_gabbais_api():
        shuls = _app.db.session.scalars(select(_app.Institution).where(
            _app.Institution.kind == 'Shul').order_by(_app.Institution.name)).all()
        result = {}
        for shul in shuls:
            result[shul.name] = [
                {'name': row.name, 'phone': row.phone}
                for row in _app.db.session.scalars(select(ShulGabbaiDirectory).where(
                    ShulGabbaiDirectory.institution_id == shul.id
                ).order_by(ShulGabbaiDirectory.id)).all()
            ]
        return result

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
                    _save_shul_connections(int(family_id))
            return response

        app.view_functions[endpoint] = wrapped

    return register_native_payments(app)


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
