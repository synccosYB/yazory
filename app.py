import os
import re

import app_original as _app
from flask import current_app, session
from sqlalchemy import Index, UniqueConstraint, select, text

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


class RabbiPerson(_app.db.Model):
    """One canonical rabbi identity, reusable by any number of shuls."""
    __tablename__ = 'rabbi_person'
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    name = _app.db.Column(_app.db.String(160), nullable=False)
    normalized_name = _app.db.Column(_app.db.String(160), nullable=False, unique=True, index=True)
    phone = _app.db.Column(_app.db.String(80), nullable=False, default='')


class ShulRabbiAssociation(_app.db.Model):
    """The many-to-many shul/rabbi directory, including its single primary."""
    __tablename__ = 'shul_rabbi_association'
    __table_args__ = (
        UniqueConstraint('institution_id', 'rabbi_person_id',
                         name='uq_shul_rabbi_association'),
        Index('uq_shul_rabbi_primary', 'institution_id', unique=True,
              sqlite_where=text('is_primary = 1'),
              postgresql_where=text('is_primary = true')),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=False, index=True)
    rabbi_person_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('rabbi_person.id'), nullable=False, index=True)
    is_primary = _app.db.Column(_app.db.Boolean, nullable=False, default=False)
    institution = _app.db.relationship(
        'Institution', backref=_app.db.backref(
            'rabbi_associations', cascade='all, delete-orphan',
            order_by='ShulRabbiAssociation.id'))
    rabbi_person = _app.db.relationship('RabbiPerson')


class FamilyRabbiPreference(_app.db.Model):
    """Canonical family choice; legacy Family columns remain display snapshots."""
    __tablename__ = 'family_rabbi_preference'
    family_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('family.id'), primary_key=True)
    rabbi_person_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('rabbi_person.id'), nullable=True, index=True)
    overridden = _app.db.Column(_app.db.Boolean, nullable=False, default=False)
    rabbi_person = _app.db.relationship('RabbiPerson')


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


def _normalize_rabbi_name(name):
    return ' '.join((name or '').split()).casefold()


def _canonical_rabbi(name, phone=''):
    name = ' '.join((name or '').split())[:160]
    if not name:
        return None
    normalized = _normalize_rabbi_name(name)
    person = _app.db.session.scalar(select(RabbiPerson).where(
        RabbiPerson.normalized_name == normalized))
    if person is None:
        person = RabbiPerson(name=name, normalized_name=normalized, phone=(phone or '')[:80])
        _app.db.session.add(person)
        _app.db.session.flush()
    elif phone and person.phone != phone[:80]:
        person.phone = phone[:80]
    return person


def _primary_association(institution_id):
    return _app.db.session.scalar(select(ShulRabbiAssociation).where(
        ShulRabbiAssociation.institution_id == institution_id,
        ShulRabbiAssociation.is_primary.is_(True)))


def _sync_legacy_primary(institution_id):
    primary = _primary_association(institution_id)
    legacy = _app.db.session.get(ShulRabbi, institution_id)
    if primary is None:
        if legacy is not None:
            _app.db.session.delete(legacy)
        return
    if legacy is None:
        legacy = ShulRabbi(institution_id=institution_id)
        _app.db.session.add(legacy)
    legacy.rabbi_name = primary.rabbi_person.name
    legacy.rabbi_phone = primary.rabbi_person.phone or ''


def _attach_rabbi(institution, person, make_primary=False):
    association = _app.db.session.scalar(select(ShulRabbiAssociation).where(
        ShulRabbiAssociation.institution_id == institution.id,
        ShulRabbiAssociation.rabbi_person_id == person.id))
    if association is None:
        association = ShulRabbiAssociation(
            institution_id=institution.id, rabbi_person_id=person.id, is_primary=False)
        _app.db.session.add(association)
        _app.db.session.flush()
    if make_primary or _primary_association(institution.id) is None:
        for row in _app.db.session.scalars(select(ShulRabbiAssociation).where(
                ShulRabbiAssociation.institution_id == institution.id)).all():
            row.is_primary = False
        _app.db.session.flush()
        association.is_primary = True
        _app.db.session.flush()
    _sync_legacy_primary(institution.id)
    return association


def _migrate_canonical_rabbis():
    marker_key = 'canonical_rabbis_v1'
    if _app.db.session.get(_app.OrganizationSetting, marker_key) is not None:
        return
    for legacy in _app.db.session.scalars(select(ShulRabbi).order_by(
            ShulRabbi.institution_id)).all():
        person = _canonical_rabbi(legacy.rabbi_name, legacy.rabbi_phone)
        if person is not None:
            institution = _app.db.session.get(_app.Institution, legacy.institution_id)
            if institution is not None:
                _attach_rabbi(institution, person, make_primary=True)
    for family in _app.db.session.scalars(select(_app.Family).order_by(_app.Family.id)).all():
        preference = _app.db.session.get(FamilyRabbiPreference, family.id)
        if preference is None:
            person = _canonical_rabbi(family.rabbi, family.rabbi_phone)
            _app.db.session.add(FamilyRabbiPreference(
                family_id=family.id,
                rabbi_person_id=person.id if person else None,
                overridden=bool(family.rabbi or family.rabbi_phone)))
    _app.db.session.add(_app.OrganizationSetting(key=marker_key, value={'completed': True}))
    _app.db.session.commit()


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
        can_manage_directory = current_app.config['DEMO']
        if not can_manage_directory:
            user = _app.db.session.get(_app.StaffUser, session.get('user_id'))
            can_manage_directory = bool(user and user.role == 'organization_admin')
        rabbi_name = (_app.request.form.get(key + '_rabbi', '').strip()[:160]
                      if can_manage_directory else '')
        rabbi_phone = (_app.request.form.get(key + '_rabbi_phone', '').strip()[:80]
                       if can_manage_directory else '')
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
            person = _canonical_rabbi(rabbi_name, rabbi_phone)
            _attach_rabbi(institution, person, make_primary=(
                existing is None or existing.rabbi_name != rabbi_name or
                existing.rabbi_phone != rabbi_phone))
            existing = _app.db.session.get(ShulRabbi, institution.id)
            rabbi_name = existing.rabbi_name
            rabbi_phone = existing.rabbi_phone
        _upsert_family_rabbi(family_id, role, institution, rabbi_name, rabbi_phone)


def _save_family_rabbi_preference(family_id):
    family = _app.db.session.get(_app.Family, family_id)
    preference = _app.db.session.get(FamilyRabbiPreference, family_id)
    if preference is None:
        preference = FamilyRabbiPreference(family_id=family_id)
        _app.db.session.add(preference)
    mode = _app.request.form.get('rabbi_mode', '').strip()
    selected_id = _app.request.form.get('rabbi_person_id', type=int)
    if mode == 'automatic':
        preference.overridden = False
        person = None
        for key in ('weekday_shul', 'shabbos_shul'):
            institution = _find_shul(_submitted_institution_name(key))
            primary = _primary_association(institution.id) if institution else None
            if primary:
                person = primary.rabbi_person
                break
        preference.rabbi_person_id = person.id if person else None
        family.rabbi = person.name if person else ''
        family.rabbi_phone = person.phone if person else ''
    elif mode == 'canonical':
        person = _app.db.session.get(RabbiPerson, selected_id) if selected_id else None
        if person is None:
            _app.abort(400, 'Choose a valid rabbi.')
        preference.overridden = True
        preference.rabbi_person_id = person.id
        family.rabbi, family.rabbi_phone = person.name, person.phone
    else:
        name = _app.request.form.get('rabbi', '').strip()[:160]
        phone = _app.request.form.get('rabbi_phone', '').strip()[:80]
        # Legacy clients with a nonblank affiliated rabbi are manual overrides;
        # blank legacy submissions retain the historical automatic behavior.
        manual = mode == 'manual' or bool(name or phone)
        if manual:
            person = _canonical_rabbi(name, phone)
            preference.overridden = True
            preference.rabbi_person_id = person.id if person else None
            family.rabbi, family.rabbi_phone = name, phone
        else:
            preference.overridden = False
            person = None
            for key in ('weekday_shul', 'shabbos_shul'):
                institution = _find_shul(_submitted_institution_name(key))
                primary = _primary_association(institution.id) if institution else None
                if primary:
                    person = primary.rabbi_person
                    break
            preference.rabbi_person_id = person.id if person else None
            family.rabbi = person.name if person else ''
            family.rabbi_phone = person.phone if person else ''
    _upsert_family_rabbi(
        family_id, 'affiliated', None, family.rabbi or '', family.rabbi_phone or '')


def _sync_automatic_family_rabbis():
    """Refresh role snapshots and non-overridden family projections."""
    for family in _app.db.session.scalars(select(_app.Family)).all():
        selected_person = None
        for role, name in (('weekday_shul', family.weekday_shul),
                           ('shabbos_shul', family.shabbos_shul)):
            institution = _find_shul(name)
            primary = _primary_association(institution.id) if institution else None
            person = primary.rabbi_person if primary else None
            _upsert_family_rabbi(
                family.id, role, institution,
                person.name if person else '', person.phone if person else '')
            if selected_person is None and person is not None:
                selected_person = person
        preference = _app.db.session.get(FamilyRabbiPreference, family.id)
        if preference is not None and not preference.overridden:
            preference.rabbi_person_id = selected_person.id if selected_person else None
            family.rabbi = selected_person.name if selected_person else ''
            family.rabbi_phone = selected_person.phone if selected_person else ''
            _upsert_family_rabbi(
                family.id, 'affiliated', None, family.rabbi, family.rabbi_phone)


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
    _sync_automatic_family_rabbis()
    _save_family_rabbi_preference(family_id)
    _save_shul_gabbai_connections(family_id)
    _app.db.session.commit()


def create_app(test_config=None):
    app = _app.create_app(test_config)
    with app.app_context():
        _migrate_canonical_rabbis()

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
        people = _app.db.session.scalars(select(RabbiPerson).order_by(RabbiPerson.name)).all()
        def family_rabbi_preference(family_id):
            return _app.db.session.get(FamilyRabbiPreference, family_id) if family_id else None
        return {
            'rabbi_people': people,
            'family_rabbi_preference': family_rabbi_preference,
            'shul_rabbi_map': {
                institution.name: {
                    'name': assignment.rabbi_name if assignment else '',
                    'phone': assignment.rabbi_phone if assignment else '',
                }
                for institution, assignment in rows
            }
        }

    def require_org_admin():
        if app.config['DEMO']:
            return
        user = _app.db.session.get(_app.StaffUser, _app.session.get('user_id'))
        if user is None or user.role != 'organization_admin':
            _app.abort(403)

    def add_audit(action):
        user = (_app.db.session.get(_app.StaffUser, _app.session.get('user_id'))
                if _app.session.get('user_id') else None)
        _app.db.session.add(_app.Audit(
            actor=user.email if user else 'Demo user', action=action))

    @app.post('/community-directories/shuls/<int:institution_id>/rabbis')
    def add_shul_rabbi(institution_id):
        require_org_admin()
        institution = _app.db.get_or_404(_app.Institution, institution_id)
        if institution.kind != 'Shul':
            _app.abort(400, 'Choose a valid shul.')
        person_id = _app.request.form.get('rabbi_person_id', type=int)
        if person_id:
            person = _app.db.get_or_404(RabbiPerson, person_id)
        else:
            name = _app.request.form.get('rabbi_name', '').strip()[:160]
            if not name:
                _app.abort(400, 'Rabbi name is required.')
            person = _canonical_rabbi(
                name, _app.request.form.get('rabbi_phone', '').strip()[:80])
        association = _attach_rabbi(
            institution, person, make_primary=_app.request.form.get('make_primary') == '1')
        _sync_automatic_family_rabbis()
        add_audit(f'Connected rabbi to shul: {person.name} / {institution.name}')
        _app.db.session.commit()
        _app.flash('Rabbi connected.')
        return _app.redirect(_app.url_for('community_directories', kind='Shul'))

    @app.post('/community-directories/shul-rabbis/<int:association_id>/primary')
    def make_shul_rabbi_primary(association_id):
        require_org_admin()
        association = _app.db.get_or_404(ShulRabbiAssociation, association_id)
        _attach_rabbi(association.institution, association.rabbi_person, make_primary=True)
        _sync_automatic_family_rabbis()
        add_audit(f'Changed primary rabbi: {association.institution.name}')
        _app.db.session.commit()
        return _app.redirect(_app.url_for('community_directories', kind='Shul'))

    @app.post('/community-directories/shul-rabbis/<int:association_id>/delete')
    def delete_shul_rabbi(association_id):
        require_org_admin()
        association = _app.db.get_or_404(ShulRabbiAssociation, association_id)
        institution = association.institution
        was_primary = association.is_primary
        name = association.rabbi_person.name
        _app.db.session.delete(association)
        _app.db.session.flush()
        if was_primary:
            replacement = _app.db.session.scalar(select(ShulRabbiAssociation).where(
                ShulRabbiAssociation.institution_id == institution.id
            ).order_by(ShulRabbiAssociation.id))
            if replacement:
                replacement.is_primary = True
                _app.db.session.flush()
        _sync_legacy_primary(institution.id)
        _sync_automatic_family_rabbis()
        add_audit(f'Removed rabbi from shul: {name} / {institution.name}')
        _app.db.session.commit()
        return _app.redirect(_app.url_for('community_directories', kind='Shul'))

    for endpoint in ('new_family', 'edit_family'):
        original = app.view_functions.get(endpoint)
        if original is None:
            continue

        def wrapped(*args, __original=original, __endpoint=endpoint, **kwargs):
            if (_app.request.method == 'POST' and
                    _app.request.form.get('rabbi_mode') == 'canonical'):
                selected_id = _app.request.form.get('rabbi_person_id', type=int)
                if selected_id is None or _app.db.session.get(RabbiPerson, selected_id) is None:
                    _app.abort(400, 'Choose a valid rabbi.')
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
