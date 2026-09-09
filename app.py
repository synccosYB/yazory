import json
import os
import re

import app_original as _app
from sqlalchemy import UniqueConstraint, select

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


class ShulRabbiPhone(_app.db.Model):
    """All phone numbers that belong to the rabbi of a shul."""
    __tablename__ = 'shul_rabbi_phone'
    __table_args__ = (
        UniqueConstraint('institution_id', 'phone', name='uq_shul_rabbi_phone'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=False, index=True)
    phone = _app.db.Column(_app.db.String(80), nullable=False)
    institution = _app.db.relationship('Institution')


class ShulRabbiAssistant(_app.db.Model):
    """An assistant/gabbai of the rabbi, distinct from a gabbai of the shul."""
    __tablename__ = 'shul_rabbi_assistant'
    __table_args__ = (
        UniqueConstraint('institution_id', 'name', name='uq_shul_rabbi_assistant'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=False, index=True)
    name = _app.db.Column(_app.db.String(160), nullable=False)
    institution = _app.db.relationship('Institution')


class ShulRabbiAssistantPhone(_app.db.Model):
    """Multiple phone numbers for one rabbi assistant."""
    __tablename__ = 'shul_rabbi_assistant_phone'
    __table_args__ = (
        UniqueConstraint('assistant_id', 'phone', name='uq_shul_rabbi_assistant_phone'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    assistant_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('shul_rabbi_assistant.id'), nullable=False, index=True)
    phone = _app.db.Column(_app.db.String(80), nullable=False)
    assistant = _app.db.relationship('ShulRabbiAssistant')


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


class ShulGabbaiPhone(_app.db.Model):
    """Multiple phone numbers for a shul gabbai."""
    __tablename__ = 'shul_gabbai_phone'
    __table_args__ = (
        UniqueConstraint('gabbai_id', 'phone', name='uq_shul_gabbai_phone'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    gabbai_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('shul_gabbai_directory.id'), nullable=False, index=True)
    phone = _app.db.Column(_app.db.String(80), nullable=False)
    gabbai = _app.db.relationship('ShulGabbaiDirectory')


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


def _clean_phones(values):
    result = []
    seen = set()
    for raw in values:
        phone = (raw or '').strip()[:80]
        if not phone or phone.casefold() in seen:
            continue
        seen.add(phone.casefold())
        result.append(phone)
    return result


def _json_phone_lists(field):
    result = []
    for raw in _app.request.form.getlist(field):
        try:
            values = json.loads(raw or '[]')
        except (TypeError, ValueError):
            values = []
        result.append(_clean_phones(values if isinstance(values, list) else []))
    return result


def _rabbi_phones(institution):
    rows = _app.db.session.scalars(select(ShulRabbiPhone).where(
        ShulRabbiPhone.institution_id == institution.id).order_by(ShulRabbiPhone.id)).all()
    if rows:
        return [row.phone for row in rows]
    legacy = _app.db.session.get(ShulRabbi, institution.id)
    return [legacy.rabbi_phone] if legacy and legacy.rabbi_phone else []


def _gabbai_phones(gabbai):
    rows = _app.db.session.scalars(select(ShulGabbaiPhone).where(
        ShulGabbaiPhone.gabbai_id == gabbai.id).order_by(ShulGabbaiPhone.id)).all()
    if rows:
        return [row.phone for row in rows]
    return [gabbai.phone] if gabbai.phone else []


def _replace_rabbi_phones(institution, phones):
    current = _app.db.session.scalars(select(ShulRabbiPhone).where(
        ShulRabbiPhone.institution_id == institution.id)).all()
    for row in current:
        _app.db.session.delete(row)
    for phone in _clean_phones(phones):
        _app.db.session.add(ShulRabbiPhone(institution_id=institution.id, phone=phone))


def _replace_gabbai_phones(gabbai, phones):
    current = _app.db.session.scalars(select(ShulGabbaiPhone).where(
        ShulGabbaiPhone.gabbai_id == gabbai.id)).all()
    for row in current:
        _app.db.session.delete(row)
    for phone in _clean_phones(phones):
        _app.db.session.add(ShulGabbaiPhone(gabbai_id=gabbai.id, phone=phone))


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


def _replace_rabbi_assistants(institution, names, phone_lists):
    current = _app.db.session.scalars(select(ShulRabbiAssistant).where(
        ShulRabbiAssistant.institution_id == institution.id).order_by(ShulRabbiAssistant.id)).all()
    existing = {row.name.casefold(): row for row in current}
    keep_ids = set()
    for index, raw_name in enumerate(names):
        name = (raw_name or '').strip()[:160]
        if not name:
            continue
        assistant = existing.get(name.casefold())
        if assistant is None:
            assistant = ShulRabbiAssistant(institution_id=institution.id, name=name)
            _app.db.session.add(assistant)
            _app.db.session.flush()
        else:
            assistant.name = name
        keep_ids.add(assistant.id)
        phones = phone_lists[index] if index < len(phone_lists) else []
        old_phones = _app.db.session.scalars(select(ShulRabbiAssistantPhone).where(
            ShulRabbiAssistantPhone.assistant_id == assistant.id)).all()
        for row in old_phones:
            _app.db.session.delete(row)
        for phone in phones:
            _app.db.session.add(ShulRabbiAssistantPhone(
                assistant_id=assistant.id, phone=phone))
    for assistant in current:
        if assistant.id not in keep_ids:
            for phone in _app.db.session.scalars(select(ShulRabbiAssistantPhone).where(
                    ShulRabbiAssistantPhone.assistant_id == assistant.id)).all():
                _app.db.session.delete(phone)
            _app.db.session.delete(assistant)


def _save_shul_rabbi_connections(family_id):
    family = _app.db.session.get(_app.Family, family_id)
    if family is None:
        return

    submitted = []
    for role, key in (('weekday_shul', 'weekday_shul'), ('shabbos_shul', 'shabbos_shul')):
        shul_name = _submitted_institution_name(key)
        if not shul_name:
            _upsert_family_rabbi(family_id, role, None, '', '')
            continue
        institution = _find_shul(shul_name)
        rabbi_name = _app.request.form.get(key + '_rabbi', '').strip()[:160]
        phone_field = key + '_rabbi_phone'
        has_phone_fields = phone_field in _app.request.form
        phones = _clean_phones(_app.request.form.getlist(phone_field))
        assistant_field = key + '_rabbi_assistant_name'
        has_assistant_fields = assistant_field in _app.request.form
        assistant_names = _app.request.form.getlist(assistant_field)
        assistant_phones = _json_phone_lists(key + '_rabbi_assistant_phones')
        submitted.append((
            role, institution, rabbi_name, phones, has_phone_fields,
            assistant_names, assistant_phones, has_assistant_fields))

    assignments = {}
    inherited_rabbis = []
    for (role, institution, rabbi_name, submitted_phones, has_phone_fields,
         assistant_names, assistant_phones, has_assistant_fields) in submitted:
        if institution is None:
            first_phone = submitted_phones[0] if submitted_phones else ''
            _upsert_family_rabbi(family_id, role, None, rabbi_name, first_phone)
            if rabbi_name:
                inherited_rabbis.append((rabbi_name, first_phone, None))
            continue

        existing = _app.db.session.get(ShulRabbi, institution.id)
        chosen = assignments.get(institution.id)
        if chosen is None:
            if rabbi_name:
                phones = submitted_phones if has_phone_fields else _rabbi_phones(institution)
                chosen = (rabbi_name, phones)
            elif existing is not None:
                chosen = (existing.rabbi_name, _rabbi_phones(institution))
            else:
                chosen = ('', [])
            assignments[institution.id] = chosen

        rabbi_name, phones = chosen
        first_phone = phones[0] if phones else ''
        if rabbi_name:
            if existing is None:
                existing = ShulRabbi(institution_id=institution.id)
                _app.db.session.add(existing)
            existing.rabbi_name = rabbi_name
            existing.rabbi_phone = first_phone
            if has_phone_fields:
                _replace_rabbi_phones(institution, submitted_phones)
            elif not _rabbi_phones(institution) and first_phone:
                _replace_rabbi_phones(institution, [first_phone])
            if has_assistant_fields:
                _replace_rabbi_assistants(
                    institution, assistant_names, assistant_phones)
            inherited_rabbis.append((rabbi_name, first_phone, institution))
        _upsert_family_rabbi(
            family_id, role, institution, rabbi_name, first_phone)

    if not (family.rabbi or '').strip() and inherited_rabbis:
        unique = {}
        for rabbi_name, rabbi_phone, institution in inherited_rabbis:
            unique.setdefault(rabbi_name.casefold(), (rabbi_name, rabbi_phone, institution))
        if len(unique) == 1:
            rabbi_name, rabbi_phone, institution = next(iter(unique.values()))
            family.rabbi = rabbi_name
            family.rabbi_phone = rabbi_phone
            _upsert_family_rabbi(
                family_id, 'affiliated', institution, rabbi_name, rabbi_phone)
        else:
            _upsert_family_rabbi(
                family_id, 'affiliated', None, family.rabbi or '', family.rabbi_phone or '')
    else:
        _upsert_family_rabbi(
            family_id, 'affiliated', None, family.rabbi or '', family.rabbi_phone or '')


def _submitted_gabbais(key):
    names = _app.request.form.getlist(key + '_gabbai_name')
    phone_lists = _json_phone_lists(key + '_gabbai_phones')
    legacy_phones = _app.request.form.getlist(key + '_gabbai_phone')
    rows = []
    seen = set()
    for index, raw_name in enumerate(names):
        name = (raw_name or '').strip()[:160]
        if not name:
            continue
        phones = phone_lists[index] if index < len(phone_lists) else []
        if not phones and index < len(legacy_phones):
            phones = _clean_phones([legacy_phones[index]])
        identity = name.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        rows.append((name, phones))
    return rows


def _replace_shul_gabbais(institution, submitted_rows):
    current = _app.db.session.scalars(select(ShulGabbaiDirectory).where(
        ShulGabbaiDirectory.institution_id == institution.id).order_by(ShulGabbaiDirectory.id)).all()
    existing_by_name = {row.name.casefold(): row for row in current}
    keep_ids = set()
    result = []
    for name, phones in submitted_rows:
        row = existing_by_name.get(name.casefold())
        first_phone = phones[0] if phones else ''
        if row is None:
            row = ShulGabbaiDirectory(
                institution_id=institution.id, name=name, phone=first_phone)
            _app.db.session.add(row)
            _app.db.session.flush()
        else:
            row.name = name
            row.phone = first_phone
        _replace_gabbai_phones(row, phones)
        keep_ids.add(row.id)
        result.append(row)
    for row in current:
        if row.id not in keep_ids:
            linked = _app.db.session.scalar(select(FamilyGabbaiConnection.id).where(
                FamilyGabbaiConnection.gabbai_id == row.id))
            if not linked:
                for phone in _app.db.session.scalars(select(ShulGabbaiPhone).where(
                        ShulGabbaiPhone.gabbai_id == row.id)).all():
                    _app.db.session.delete(phone)
                _app.db.session.delete(row)
    return result


def _sync_family_gabbais(family_id, role, institution, gabbais):
    current = _app.db.session.scalars(select(FamilyGabbaiConnection).where(
        FamilyGabbaiConnection.family_id == family_id,
        FamilyGabbaiConnection.role == role)).all()
    desired_ids = {gabbai.id for gabbai in gabbais} if institution is not None else set()
    existing_by_gabbai = {row.gabbai_id: row for row in current}
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
                    (row.name, _gabbai_phones(row))
                    for row in _app.db.session.scalars(
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


def _assistant_payload(institution):
    assistants = _app.db.session.scalars(select(ShulRabbiAssistant).where(
        ShulRabbiAssistant.institution_id == institution.id).order_by(ShulRabbiAssistant.id)).all()
    result = []
    for assistant in assistants:
        phones = [row.phone for row in _app.db.session.scalars(
            select(ShulRabbiAssistantPhone).where(
                ShulRabbiAssistantPhone.assistant_id == assistant.id
            ).order_by(ShulRabbiAssistantPhone.id)).all()]
        result.append({
            'name': assistant.name,
            'phone': phones[0] if phones else '',
            'phones': phones,
        })
    return result


def create_app(test_config=None):
    app = _app.create_app(test_config)

    @app.get('/api/shul-rabbis')
    def shul_rabbis_api():
        rows = _app.db.session.execute(select(_app.Institution, ShulRabbi).join(
            ShulRabbi, ShulRabbi.institution_id == _app.Institution.id, isouter=True).where(
            _app.Institution.kind == 'Shul')).all()
        result = {}
        for institution, assignment in rows:
            phones = _rabbi_phones(institution) if assignment else []
            result[institution.name] = {
                'name': assignment.rabbi_name if assignment else '',
                'phone': phones[0] if phones else '',
                'phones': phones,
                'assistants': _assistant_payload(institution),
            }
        return result

    @app.get('/api/shul-gabbais')
    def shul_gabbais_api():
        shuls = _app.db.session.scalars(select(_app.Institution).where(
            _app.Institution.kind == 'Shul').order_by(_app.Institution.name)).all()
        result = {}
        for shul in shuls:
            rows = _app.db.session.scalars(select(ShulGabbaiDirectory).where(
                ShulGabbaiDirectory.institution_id == shul.id
            ).order_by(ShulGabbaiDirectory.id)).all()
            result[shul.name] = [
                {
                    'name': row.name,
                    'phone': (_gabbai_phones(row) or [''])[0],
                    'phones': _gabbai_phones(row),
                }
                for row in rows
            ]
        return result

    @app.context_processor
    def shul_rabbi_context():
        rows = _app.db.session.execute(select(_app.Institution, ShulRabbi).join(
            ShulRabbi, ShulRabbi.institution_id == _app.Institution.id, isouter=True).where(
            _app.Institution.kind == 'Shul')).all()
        mapping = {}
        for institution, assignment in rows:
            phones = _rabbi_phones(institution) if assignment else []
            mapping[institution.name] = {
                'name': assignment.rabbi_name if assignment else '',
                'phone': phones[0] if phones else '',
                'phones': phones,
                'assistants': _assistant_payload(institution),
            }
        return {'shul_rabbi_map': mapping}

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
