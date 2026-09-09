import json
import os
import re

import app_original as _app
from flask import current_app, session
from sqlalchemy import Index, UniqueConstraint, select, text

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


class FamilyPhone(_app.db.Model):
    """Additional home phone numbers for an applicant household."""
    __tablename__ = 'family_phone'
    __table_args__ = (
        UniqueConstraint('family_id', 'phone', name='uq_family_phone'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    family_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('family.id'), nullable=False, index=True)
    phone = _app.db.Column(_app.db.String(80), nullable=False)


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


def _family_phones(family):
    if family is None:
        return []
    rows = _app.db.session.scalars(select(FamilyPhone).where(
        FamilyPhone.family_id == family.id).order_by(FamilyPhone.id)).all()
    phones = [row.phone for row in rows]
    if family.phone and family.phone not in phones:
        phones.insert(0, family.phone)
    return phones


def _replace_family_phones(family_id, phones):
    cleaned = _clean_phones(phones)
    family = _app.db.session.get(_app.Family, family_id)
    if family is None:
        return
    family.phone = cleaned[0] if cleaned else ''
    current = _app.db.session.scalars(select(FamilyPhone).where(
        FamilyPhone.family_id == family_id)).all()
    for row in current:
        _app.db.session.delete(row)
    _app.db.session.flush()
    for phone in cleaned:
        _app.db.session.add(FamilyPhone(family_id=family_id, phone=phone))


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
    _app.db.session.flush()
    for phone in _clean_phones(phones):
        _app.db.session.add(ShulRabbiPhone(institution_id=institution.id, phone=phone))


def _save_primary_rabbi_phone(person, phone):
    """Keep a phone entered on a family form in the shared rabbi directory."""
    phone = (phone or '').strip()[:80]
    if person is None or not phone:
        return
    person.phone = phone
    associations = _app.db.session.scalars(select(ShulRabbiAssociation).where(
        ShulRabbiAssociation.rabbi_person_id == person.id,
        ShulRabbiAssociation.is_primary.is_(True))).all()
    for association in associations:
        institution = association.institution
        phones = _rabbi_phones(institution)
        _replace_rabbi_phones(
            institution, [phone] + [saved for saved in phones if saved != phone])
        _sync_legacy_primary(institution.id)


def _replace_gabbai_phones(gabbai, phones):
    current = _app.db.session.scalars(select(ShulGabbaiPhone).where(
        ShulGabbaiPhone.gabbai_id == gabbai.id)).all()
    for row in current:
        _app.db.session.delete(row)
    _app.db.session.flush()
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
        can_manage_directory = current_app.config['DEMO']
        if not can_manage_directory:
            user = _app.db.session.get(_app.StaffUser, session.get('user_id'))
            can_manage_directory = bool(user and user.role == 'organization_admin')
        rabbi_name = (_app.request.form.get(key + '_rabbi', '').strip()[:160]
                      if can_manage_directory else '')
        phone_field = key + '_rabbi_phone'
        has_phone_fields = can_manage_directory and phone_field in _app.request.form
        phones = (_clean_phones(_app.request.form.getlist(phone_field))
                  if can_manage_directory else [])
        assistant_field = key + '_rabbi_assistant_name'
        has_assistant_fields = can_manage_directory and assistant_field in _app.request.form
        assistant_names = (_app.request.form.getlist(assistant_field)
                           if can_manage_directory else [])
        assistant_phones = (_json_phone_lists(key + '_rabbi_assistant_phones')
                            if can_manage_directory else [])
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
            person = _canonical_rabbi(rabbi_name, first_phone)
            _attach_rabbi(institution, person, make_primary=(
                existing is None or existing.rabbi_name != rabbi_name or
                existing.rabbi_phone != first_phone))
            existing = _app.db.session.get(ShulRabbi, institution.id)
            rabbi_name = existing.rabbi_name
            first_phone = existing.rabbi_phone
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
        selected_institution = None
        for key in ('weekday_shul', 'shabbos_shul'):
            institution = _find_shul(_submitted_institution_name(key))
            primary = _primary_association(institution.id) if institution else None
            if primary:
                person = primary.rabbi_person
                selected_institution = institution
                break
        submitted_name = _app.request.form.get('rabbi', '').strip()
        submitted_phone = _app.request.form.get('rabbi_phone', '').strip()
        if (person is not None and submitted_phone and
                (not submitted_name or
                 _normalize_rabbi_name(submitted_name) == person.normalized_name)):
            _save_primary_rabbi_phone(person, submitted_phone)
        preference.rabbi_person_id = person.id if person else None
        family.rabbi = person.name if person else ''
        family.rabbi_phone = person.phone if person else ''
    elif mode == 'canonical':
        person = _app.db.session.get(RabbiPerson, selected_id) if selected_id else None
        if person is None:
            _app.abort(400, 'Choose a valid rabbi.')
        _save_primary_rabbi_phone(
            person, _app.request.form.get('rabbi_phone', '').strip())
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
            selected_institution = None
            for key in ('weekday_shul', 'shabbos_shul'):
                institution = _find_shul(_submitted_institution_name(key))
                primary = _primary_association(institution.id) if institution else None
                if primary:
                    person = primary.rabbi_person
                    selected_institution = institution
                    break
            preference.rabbi_person_id = person.id if person else None
            family.rabbi = person.name if person else ''
            family.rabbi_phone = person.phone if person else ''
    affiliated_institution = (selected_institution
                              if not preference.overridden else None)
    _upsert_family_rabbi(
        family_id, 'affiliated', affiliated_institution,
        family.rabbi or '', family.rabbi_phone or '')


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
    _sync_automatic_family_rabbis()
    _save_family_rabbi_preference(family_id)
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
    with app.app_context():
        # Models added by this compatibility layer are created after the base
        # application has initialized its database.
        _app.db.create_all()
        _migrate_canonical_rabbis()

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
            gabbais = _app.db.session.scalars(select(ShulGabbaiDirectory).where(
                ShulGabbaiDirectory.institution_id == institution.id
            ).order_by(ShulGabbaiDirectory.id)).all()
            mapping[institution.name] = {
                'name': assignment.rabbi_name if assignment else '',
                'phone': phones[0] if phones else '',
                'phones': phones,
                'assistants': _assistant_payload(institution),
                'gabbais': [
                    {'name': row.name, 'phones': _gabbai_phones(row)}
                    for row in gabbais
                ],
            }
        people = _app.db.session.scalars(select(RabbiPerson).order_by(RabbiPerson.name)).all()
        def family_rabbi_preference(family_id):
            return _app.db.session.get(FamilyRabbiPreference, family_id) if family_id else None
        def family_gabbai_contacts(family_id):
            if not family_id:
                return []
            connections = _app.db.session.scalars(select(FamilyGabbaiConnection).where(
                FamilyGabbaiConnection.family_id == family_id
            ).order_by(FamilyGabbaiConnection.role, FamilyGabbaiConnection.id)).all()
            result = []
            seen = set()
            for connection in connections:
                gabbai = connection.gabbai
                if gabbai.id in seen:
                    continue
                seen.add(gabbai.id)
                result.append({
                    'name': gabbai.name,
                    'phones': _gabbai_phones(gabbai),
                })
            return result
        def family_rabbi_assistant_contacts(family):
            if family is None:
                return []
            result = []
            seen = set()
            for shul_name in (family.weekday_shul, family.shabbos_shul):
                institution = _find_shul(shul_name)
                if institution is None:
                    continue
                primary = _primary_association(institution.id)
                if (primary is None or _normalize_rabbi_name(primary.rabbi_person.name) !=
                        _normalize_rabbi_name(family.rabbi)):
                    continue
                for assistant in _assistant_payload(institution):
                    identity = assistant['name'].casefold()
                    if identity in seen:
                        continue
                    seen.add(identity)
                    result.append(assistant)
            return result
        def family_yeshivah_history(family_id):
            return _app.db.session.execute(select(_app.PersonAffiliation, _app.Institution).join(
                _app.Institution, _app.Institution.id == _app.PersonAffiliation.institution_id
            ).where(
                _app.PersonAffiliation.person_type == 'family',
                _app.PersonAffiliation.person_id == family_id,
                _app.Institution.kind == 'Yeshivah',
            ).order_by(_app.PersonAffiliation.year_from, _app.PersonAffiliation.id)).all()
        return {
            'rabbi_people': people,
            'family_rabbi_preference': family_rabbi_preference,
            'family_gabbai_contacts': family_gabbai_contacts,
            'family_rabbi_assistant_contacts': family_rabbi_assistant_contacts,
            'family_yeshivah_history': family_yeshivah_history,
            'shul_rabbi_map': mapping,
            'family_phone_values': lambda family: (
                _clean_phones(_app.request.form.getlist('phone'))
                if _app.request.method == 'POST' else _family_phones(family)),
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
                    _replace_family_phones(
                        int(family_id), _app.request.form.getlist('phone'))
                    _app.db.session.commit()
            return response

        app.view_functions[endpoint] = wrapped

    return register_native_payments(app)


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
