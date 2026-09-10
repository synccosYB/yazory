import json
import os
import re

import app_original as _app
from flask import current_app, has_request_context, session
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


class HelperPerson(_app.db.Model):
    """One reusable helper identity that may serve any number of shuls."""
    __tablename__ = 'helper_person'
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    name = _app.db.Column(_app.db.String(160), nullable=False)
    normalized_name = _app.db.Column(
        _app.db.String(160), nullable=False, unique=True, index=True)


class HelperPhone(_app.db.Model):
    """Phone numbers belong to the helper, rather than to one shul link."""
    __tablename__ = 'helper_phone'
    __table_args__ = (
        UniqueConstraint('helper_person_id', 'phone', name='uq_helper_phone'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    helper_person_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('helper_person.id'), nullable=False, index=True)
    phone = _app.db.Column(_app.db.String(80), nullable=False)
    helper_person = _app.db.relationship('HelperPerson')


class ShulHelperAssociation(_app.db.Model):
    """Many-to-many shul/helper link, with the helper's role at that shul."""
    __tablename__ = 'shul_helper_association'
    __table_args__ = (
        UniqueConstraint('institution_id', 'helper_person_id', 'role',
                         name='uq_shul_helper_association'),
    )
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    institution_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('institution.id'), nullable=False, index=True)
    helper_person_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('helper_person.id'), nullable=False, index=True)
    role = _app.db.Column(_app.db.String(40), nullable=False)
    institution = _app.db.relationship(
        'Institution', backref=_app.db.backref(
            'helper_associations', cascade='all, delete-orphan',
            order_by='ShulHelperAssociation.id'))
    helper_person = _app.db.relationship('HelperPerson')


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


class StaffTask(_app.db.Model):
    """Assignable staff work; a parent task may contain any number of subtasks."""
    __tablename__ = 'staff_task'
    id = _app.db.Column(_app.db.Integer, primary_key=True)
    parent_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('staff_task.id'), nullable=True, index=True)
    family_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('family.id'), nullable=True, index=True)
    source_contact_id = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('contact.id', ondelete='CASCADE'),
        nullable=True, unique=True, index=True)
    assigned_to = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('staff_user.id'), nullable=False, index=True)
    created_by = _app.db.Column(
        _app.db.Integer, _app.db.ForeignKey('staff_user.id'), nullable=False, index=True)
    title = _app.db.Column(_app.db.String(240), nullable=False)
    description = _app.db.Column(_app.db.Text, nullable=False, default='')
    status = _app.db.Column(_app.db.String(20), nullable=False, default='To do', index=True)
    priority = _app.db.Column(_app.db.String(20), nullable=False, default='Normal', index=True)
    due_date = _app.db.Column(_app.db.Date, nullable=True, index=True)
    created_at = _app.db.Column(
        _app.db.DateTime, nullable=False,
        default=lambda: _app.datetime.now(_app.timezone.utc).replace(tzinfo=None))
    completed_at = _app.db.Column(_app.db.DateTime, nullable=True)
    parent = _app.db.relationship(
        'StaffTask', remote_side=[id], backref=_app.db.backref(
            'subtasks', cascade='all, delete-orphan', order_by='StaffTask.id'))
    family = _app.db.relationship('Family')
    source_contact = _app.db.relationship('Contact', backref=_app.db.backref(
        'automatic_followup_task', uselist=False, cascade='all, delete-orphan',
        single_parent=True))
    assignee = _app.db.relationship('StaffUser', foreign_keys=[assigned_to])
    creator = _app.db.relationship('StaffUser', foreign_keys=[created_by])


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


def _canonical_helper(name, phones=()):
    name = ' '.join((name or '').split())[:160]
    if not name:
        return None
    normalized = _normalize_rabbi_name(name)
    person = _app.db.session.scalar(select(HelperPerson).where(
        HelperPerson.normalized_name == normalized))
    if person is None:
        person = HelperPerson(name=name, normalized_name=normalized)
        _app.db.session.add(person)
        _app.db.session.flush()
    else:
        person.name = name
    saved = {row.phone.casefold() for row in _app.db.session.scalars(
        select(HelperPhone).where(HelperPhone.helper_person_id == person.id)).all()}
    for phone in _clean_phones(phones):
        if phone.casefold() not in saved:
            _app.db.session.add(HelperPhone(helper_person_id=person.id, phone=phone))
            saved.add(phone.casefold())
    return person


def _attach_helper(institution, person, role):
    association = _app.db.session.scalar(select(ShulHelperAssociation).where(
        ShulHelperAssociation.institution_id == institution.id,
        ShulHelperAssociation.helper_person_id == person.id,
        ShulHelperAssociation.role == role))
    if association is None:
        association = ShulHelperAssociation(
            institution_id=institution.id, helper_person_id=person.id, role=role)
        _app.db.session.add(association)
        _app.db.session.flush()
    return association


def _sync_helper_associations(institution, role, people):
    current = _app.db.session.scalars(select(ShulHelperAssociation).where(
        ShulHelperAssociation.institution_id == institution.id,
        ShulHelperAssociation.role == role)).all()
    desired_ids = {person.id for person in people}
    for association in current:
        if association.helper_person_id not in desired_ids:
            _app.db.session.delete(association)
    for person in people:
        _attach_helper(institution, person, role)


def _helper_phones(person):
    return [row.phone for row in _app.db.session.scalars(select(HelperPhone).where(
        HelperPhone.helper_person_id == person.id).order_by(HelperPhone.id)).all()]


def _sync_legacy_helper_phones(person):
    """Keep compatibility rows aligned while helper phones are globally owned."""
    phones = _helper_phones(person)
    normalized = person.normalized_name
    for row in _app.db.session.scalars(select(ShulGabbaiDirectory)).all():
        if _normalize_rabbi_name(row.name) == normalized:
            row.phone = phones[0] if phones else ''
            _replace_gabbai_phones(row, phones)
    for assistant in _app.db.session.scalars(select(ShulRabbiAssistant)).all():
        if _normalize_rabbi_name(assistant.name) != normalized:
            continue
        existing = _app.db.session.scalars(select(ShulRabbiAssistantPhone).where(
            ShulRabbiAssistantPhone.assistant_id == assistant.id)).all()
        for row in existing:
            _app.db.session.delete(row)
        _app.db.session.flush()
        for phone in phones:
            _app.db.session.add(ShulRabbiAssistantPhone(
                assistant_id=assistant.id, phone=phone))


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


def _migrate_canonical_helpers():
    marker_key = 'canonical_helpers_v1'
    if _app.db.session.get(_app.OrganizationSetting, marker_key) is not None:
        return
    for row in _app.db.session.scalars(select(ShulGabbaiDirectory).order_by(
            ShulGabbaiDirectory.id)).all():
        person = _canonical_helper(row.name, _gabbai_phones(row))
        if person is not None:
            _attach_helper(row.institution, person, 'shul_gabbai')
    for row in _app.db.session.scalars(select(ShulRabbiAssistant).order_by(
            ShulRabbiAssistant.id)).all():
        phones = [phone.phone for phone in _app.db.session.scalars(
            select(ShulRabbiAssistantPhone).where(
                ShulRabbiAssistantPhone.assistant_id == row.id
            ).order_by(ShulRabbiAssistantPhone.id)).all()]
        person = _canonical_helper(row.name, phones)
        if person is not None:
            _attach_helper(row.institution, person, 'rabbi_assistant')
    for person in _app.db.session.scalars(select(HelperPerson).order_by(
            HelperPerson.id)).all():
        _sync_legacy_helper_phones(person)
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
    helper_people = []
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
        helper = _canonical_helper(name, phones)
        if helper is not None:
            helper_people.append(helper)
        old_phones = _app.db.session.scalars(select(ShulRabbiAssistantPhone).where(
            ShulRabbiAssistantPhone.assistant_id == assistant.id)).all()
        for row in old_phones:
            _app.db.session.delete(row)
        for phone in phones:
            _app.db.session.add(ShulRabbiAssistantPhone(
                assistant_id=assistant.id, phone=phone))
        if helper is not None:
            _sync_legacy_helper_phones(helper)
    for assistant in current:
        if assistant.id not in keep_ids:
            for phone in _app.db.session.scalars(select(ShulRabbiAssistantPhone).where(
                    ShulRabbiAssistantPhone.assistant_id == assistant.id)).all():
                _app.db.session.delete(phone)
            _app.db.session.delete(assistant)
    _sync_helper_associations(institution, 'rabbi_assistant', helper_people)


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
    helper_people = []
    for name, phones in submitted_rows:
        helper = _canonical_helper(name, phones)
        if helper is not None:
            helper_people.append(helper)
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
        if helper is not None:
            _sync_legacy_helper_phones(helper)
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
    _sync_helper_associations(institution, 'shul_gabbai', helper_people)
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
        if not phones:
            helper = _app.db.session.scalar(select(HelperPerson).where(
                HelperPerson.normalized_name == _normalize_rabbi_name(assistant.name)))
            if helper is not None:
                phones = _helper_phones(helper)
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
        task_columns = {
            column['name'] for column in _app.inspect(_app.db.engine).get_columns('staff_task')
        }
        if 'source_contact_id' not in task_columns:
            _app.db.session.execute(text(
                'ALTER TABLE staff_task ADD COLUMN source_contact_id INTEGER REFERENCES contact(id)'
            ))
        _app.db.session.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_task_source_contact '
            'ON staff_task (source_contact_id)'
        ))
        _app.db.session.commit()
        _migrate_canonical_rabbis()
        _migrate_canonical_helpers()

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
        # This directory data is only rendered on the family and community
        # directory screens. Loading it globally caused an N+1 query storm on
        # every page (dashboard, lists, payouts, etc.): each shul triggered
        # separate phone, assistant, gabbai and gabbai-phone queries.
        #
        # Keep harmless defaults available to every template, but do no
        # directory work unless the current screen can actually use it.
        empty_context = {
            'rabbi_people': [],
            'family_rabbi_preference': lambda family_id: None,
            'family_gabbai_contacts': lambda family_id: [],
            'family_rabbi_assistant_contacts': lambda family: [],
            'family_yeshivah_history': lambda family_id: [],
            'shul_rabbi_map': {},
            'family_phone_values': lambda family: (
                _clean_phones(_app.request.form.getlist('phone'))
                if _app.request.method == 'POST' else _family_phones(family)),
        }
        if _app.request.endpoint not in {
                'new_family', 'edit_family', 'family_detail', 'directories'}:
            return empty_context

        # A family profile can display contacts for only its weekday and
        # Shabbos shuls.  Do not build the entire organization-wide directory
        # for that page: doing so used to issue several queries per shul and
        # made profiles progressively slower as the directory grew.
        institution_filter = [_app.Institution.kind == 'Shul']
        profile_institution_ids = []
        if _app.request.endpoint == 'family_detail':
            family_id = (_app.request.view_args or {}).get('family_id')
            # family_detail already loaded this object into the request's
            # identity map, so this does not require another database query.
            context_family = _app.db.session.get(_app.Family, family_id)
            profile_institution_ids = list(_app.db.session.scalars(select(
                _app.PersonAffiliation.institution_id
            ).join(_app.Institution).where(
                _app.PersonAffiliation.person_type == 'family',
                _app.PersonAffiliation.person_id == family_id,
                _app.Institution.kind == 'Shul',
                _app.PersonAffiliation.note.contains('Family profile'),
            )).all())
            relevant_names = {name for name in (
                context_family.weekday_shul if context_family else '',
                context_family.shabbos_shul if context_family else '') if name}
            if profile_institution_ids:
                institution_filter.append(_app.Institution.id.in_(profile_institution_ids))
                rows = _app.db.session.execute(select(_app.Institution, ShulRabbi).join(
                    ShulRabbi, ShulRabbi.institution_id == _app.Institution.id,
                    isouter=True).where(*institution_filter)).all()
            elif not relevant_names:
                rows = []
            else:
                institution_filter.append(_app.Institution.name.in_(relevant_names))
                rows = _app.db.session.execute(select(_app.Institution, ShulRabbi).join(
                    ShulRabbi, ShulRabbi.institution_id == _app.Institution.id,
                    isouter=True).where(*institution_filter)).all()
        else:
            # The intake form gets its shul names separately and the directory
            # screen renders its own selected records; neither consumes this
            # contact map.
            rows = []
        mapping = {}
        institution_contacts = {}
        for institution, assignment in rows:
            phones = _rabbi_phones(institution) if assignment else []
            gabbais = _app.db.session.scalars(select(ShulGabbaiDirectory).where(
                ShulGabbaiDirectory.institution_id == institution.id
            ).order_by(ShulGabbaiDirectory.id)).all()
            payload = {
                'name': assignment.rabbi_name if assignment else '',
                'phone': phones[0] if phones else '',
                'phones': phones,
                'assistants': _assistant_payload(institution),
                'gabbais': [
                        {'name': row.name, 'phones': _gabbai_phones(row)}
                        for row in gabbais
                ],
            }
            institution_contacts[institution.id] = payload
            mapping[institution.name] = payload
        people = (_app.db.session.scalars(select(RabbiPerson).order_by(RabbiPerson.name)).all()
                  if _app.request.endpoint in {'new_family', 'edit_family', 'directories'}
                  else [])
        def family_rabbi_preference(family_id):
            return _app.db.session.get(FamilyRabbiPreference, family_id) if family_id else None
        def family_gabbai_contacts(family_id):
            if not family_id:
                return []
            family = _app.db.session.get(_app.Family, family_id)
            connections = _app.db.session.scalars(select(FamilyGabbaiConnection).where(
                FamilyGabbaiConnection.family_id == family_id
            ).order_by(FamilyGabbaiConnection.role, FamilyGabbaiConnection.id)).all()
            result = []
            seen = set()

            # Gabbaim belong to the shared shul, not to an individual family.
            # Read the current shul directory first so applicants who selected
            # the same shul also see gabbaim added after their profile was saved.
            linked_ids = profile_institution_ids if family_id == (
                (_app.request.view_args or {}).get('family_id')) else list(
                    _app.db.session.scalars(select(
                        _app.PersonAffiliation.institution_id
                    ).join(_app.Institution).where(
                        _app.PersonAffiliation.person_type == 'family',
                        _app.PersonAffiliation.person_id == family_id,
                        _app.Institution.kind == 'Shul',
                        _app.PersonAffiliation.note.contains('Family profile'),
                    )).all())
            contact_groups = [institution_contacts.get(row_id, {}) for row_id in linked_ids]
            if not contact_groups:
                contact_groups = [mapping.get(name, {}) for name in (
                    (family.weekday_shul, family.shabbos_shul) if family is not None else ())]
            for contacts in contact_groups:
                for gabbai in contacts.get('gabbais', []):
                    identity = (gabbai['name'].casefold(), tuple(gabbai['phones']))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    result.append(gabbai)

            # Preserve old applicant-specific connections for legacy records
            # whose shul directory entry may no longer exist.
            for connection in connections:
                gabbai = connection.gabbai
                payload = {
                    'name': gabbai.name,
                    'phones': _gabbai_phones(gabbai),
                }
                identity = (payload['name'].casefold(), tuple(payload['phones']))
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(payload)
            return result
        def family_rabbi_assistant_contacts(family):
            if family is None:
                return []
            result = []
            seen = set()
            for shul_name in (family.weekday_shul, family.shabbos_shul):
                contacts = mapping.get(shul_name, {})
                if (_normalize_rabbi_name(contacts.get('name')) !=
                        _normalize_rabbi_name(family.rabbi)):
                    continue
                for assistant in contacts.get('assistants', []):
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
        return _app.redirect(_app.url_for('community_directories', kind='Shul',
                                          network_id=institution.id))

    @app.post('/community-directories/shul-rabbis/<int:association_id>/primary')
    def make_shul_rabbi_primary(association_id):
        require_org_admin()
        association = _app.db.get_or_404(ShulRabbiAssociation, association_id)
        _attach_rabbi(association.institution, association.rabbi_person, make_primary=True)
        _sync_automatic_family_rabbis()
        add_audit(f'Changed primary rabbi: {association.institution.name}')
        _app.db.session.commit()
        return _app.redirect(_app.url_for('community_directories', kind='Shul',
                                          network_id=association.institution_id))

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
        return _app.redirect(_app.url_for('community_directories', kind='Shul',
                                          network_id=institution.id))

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

    TASK_STATUSES = ('To do', 'In progress', 'Waiting', 'Completed', 'Cancelled')
    TASK_PRIORITIES = ('Low', 'Normal', 'High', 'Urgent')

    def task_user():
        user_id = _app.session.get('user_id')
        return _app.db.session.get(_app.StaffUser, user_id) if user_id else None

    def task_is_admin(user):
        return bool(user and user.role == 'organization_admin')

    def visible_task_or_403(task_id):
        task = _app.db.get_or_404(StaffTask, task_id)
        user = task_user()
        if not task_is_admin(user) and (user is None or task.assigned_to != user.id):
            _app.abort(403, 'You do not have permission to view this task.')
        return task

    def automatic_task_assignee(contact):
        """Choose the person already responsible for this supporter or case."""
        if app.extensions['workflows']['enforced']():
            link_model = app.extensions['workflows']['models']['SupporterLink']
            link = _app.db.session.get(link_model, contact.id)
            if link and link.assigned_to:
                assignee = _app.db.session.get(_app.StaffUser, link.assigned_to)
                if assignee and assignee.status == 'active':
                    return assignee
        assignee = _app.db.session.scalar(select(_app.StaffUser).join(
            _app.FamilyAssignment,
            _app.FamilyAssignment.staff_user_id == _app.StaffUser.id
        ).where(
            _app.FamilyAssignment.family_id == contact.family_id,
            _app.StaffUser.status == 'active',
            _app.StaffUser.role.in_(('fundraiser', 'family_admin')),
        ).order_by(
            (_app.StaffUser.role == 'fundraiser').desc(), _app.StaffUser.id
        ))
        if assignee:
            return assignee
        actor = task_user() if has_request_context() else None
        if actor and actor.status == 'active':
            return actor
        return _app.db.session.scalar(select(_app.StaffUser).where(
            _app.StaffUser.status == 'active',
            _app.StaffUser.role == 'organization_admin').order_by(_app.StaffUser.id))

    def sync_supporter_followup_task(contact):
        task = _app.db.session.scalar(select(StaffTask).where(
            StaffTask.source_contact_id == contact.id))
        if contact.status == 'To contact':
            assignee = automatic_task_assignee(contact)
            if assignee is None:
                return
            if task is None:
                task = StaffTask(
                    family_id=contact.family_id,
                    source_contact_id=contact.id,
                    assigned_to=assignee.id,
                    created_by=assignee.id,
                    title=f'Contact supporter: {contact.name}',
                    description='',
                    priority='Normal')
                _app.db.session.add(task)
                add_audit(f'Created automatic supporter follow-up: {contact.name}')
            else:
                task.assigned_to = assignee.id
                task.status = 'To do'
                task.completed_at = None
        elif task and task.status not in ('Completed', 'Cancelled'):
            task.status = ('Cancelled' if contact.status in ('Paused', 'Declined')
                           else 'Completed')
            task.completed_at = (_app.datetime.now(_app.timezone.utc).replace(tzinfo=None)
                                 if task.status == 'Completed' else None)

    def sync_contact_ids(contact_ids):
        for contact_id in contact_ids:
            contact = _app.db.session.get(_app.Contact, contact_id)
            if contact is not None:
                sync_supporter_followup_task(contact)
        _app.db.session.commit()

    # Keep supporter outreach and the team task list in lockstep. The original
    # handlers remain authoritative for validation and permissions.
    for endpoint in ('add_contact', 'update_contact', 'edit_contact'):
        original = app.view_functions.get(endpoint)
        if original is None:
            continue

        def contact_task_wrapper(*args, __original=original, __endpoint=endpoint, **kwargs):
            before_ids = set()
            if __endpoint == 'add_contact':
                family_id = kwargs.get('family_id') or _app.request.form.get('family_id', type=int)
                if family_id:
                    before_ids = set(_app.db.session.scalars(select(_app.Contact.id).where(
                        _app.Contact.family_id == family_id)).all())
            response = app.make_response(__original(*args, **kwargs))
            if _app.request.method == 'POST' and response.status_code < 400:
                if __endpoint == 'add_contact':
                    family_id = kwargs.get('family_id') or _app.request.form.get('family_id', type=int)
                    after_ids = set(_app.db.session.scalars(select(_app.Contact.id).where(
                        _app.Contact.family_id == family_id)).all()) if family_id else set()
                    contact_ids = after_ids - before_ids
                else:
                    contact = _app.db.session.get(_app.Contact, kwargs.get('contact_id'))
                    if contact and contact.supporter_key:
                        contact_ids = set(_app.db.session.scalars(select(_app.Contact.id).where(
                            _app.Contact.supporter_key == contact.supporter_key)).all())
                    else:
                        contact_ids = {contact.id} if contact else set()
                sync_contact_ids(contact_ids)
            return response

        app.view_functions[endpoint] = contact_task_wrapper

    def parsed_due_date():
        raw = _app.request.form.get('due_date', '').strip()
        if not raw:
            return None
        try:
            return _app.date.fromisoformat(raw)
        except ValueError:
            _app.abort(400, 'Enter a valid due date.')

    def active_assignee():
        assignee = _app.db.session.get(
            _app.StaffUser, _app.request.form.get('assigned_to', type=int))
        if assignee is None or assignee.status != 'active':
            _app.abort(400, 'Choose an active staff member or collector.')
        return assignee

    @app.route('/tasks', methods=['GET', 'POST'])
    def tasks():
        user = task_user()
        if user is None and not app.config['DEMO']:
            _app.abort(403)
        if _app.request.method == 'POST':
            if not task_is_admin(user):
                _app.abort(403, 'Only an organization administrator can assign a task.')
            title = _app.request.form.get('title', '').strip()[:240]
            if not title:
                _app.abort(400, 'Task title is required.')
            assignee = active_assignee()
            family_id = _app.request.form.get('family_id', type=int)
            if family_id and _app.db.session.get(_app.Family, family_id) is None:
                _app.abort(400, 'Choose a valid family case.')
            priority = _app.request.form.get('priority', 'Normal')
            if priority not in TASK_PRIORITIES:
                _app.abort(400, 'Choose a valid priority.')
            task = StaffTask(
                title=title,
                description=_app.request.form.get('description', '').strip()[:5000],
                assigned_to=assignee.id,
                created_by=user.id,
                family_id=family_id,
                priority=priority,
                due_date=parsed_due_date())
            _app.db.session.add(task)
            add_audit(f'Created task: {title} / assigned to {assignee.email}')
            _app.db.session.commit()
            _app.flash('Task created and assigned.')
            return _app.redirect(_app.url_for('task_detail', task_id=task.id))

        statement = select(StaffTask).where(StaffTask.parent_id.is_(None))
        if not task_is_admin(user):
            statement = statement.where(StaffTask.assigned_to == (user.id if user else -1))
        selected_status = _app.request.args.get('status', '')
        if selected_status:
            if selected_status not in TASK_STATUSES:
                _app.abort(400)
            statement = statement.where(StaffTask.status == selected_status)
        rows = _app.db.session.scalars(statement.order_by(
            StaffTask.due_date.is_(None), StaffTask.due_date, StaffTask.id.desc())).all()
        staff = _app.db.session.scalars(select(_app.StaffUser).where(
            _app.StaffUser.status == 'active').order_by(_app.StaffUser.name, _app.StaffUser.email)).all()
        families = (_app.db.session.scalars(select(_app.Family).order_by(_app.Family.name)).all()
                    if task_is_admin(user) else [])
        return _app.render_template(
            'tasks.html', title='Tasks', tasks=rows, staff=staff, families=families,
            task_statuses=TASK_STATUSES, task_priorities=TASK_PRIORITIES,
            selected_status=selected_status, may_assign=task_is_admin(user), today=_app.date.today())

    @app.get('/tasks/<int:task_id>')
    def task_detail(task_id):
        task = visible_task_or_403(task_id)
        staff = _app.db.session.scalars(select(_app.StaffUser).where(
            _app.StaffUser.status == 'active').order_by(
                _app.StaffUser.name, _app.StaffUser.email)).all()
        return _app.render_template(
            'task_detail.html', title='Task details', task=task,
            task_statuses=TASK_STATUSES, task_priorities=TASK_PRIORITIES,
            staff=staff, may_assign=task_is_admin(task_user()), today=_app.date.today())

    @app.post('/tasks/<int:task_id>/status')
    def update_task_status(task_id):
        task = visible_task_or_403(task_id)
        status = _app.request.form.get('status', '')
        if status not in TASK_STATUSES:
            _app.abort(400, 'Choose a valid task status.')
        task.status = status
        task.completed_at = (_app.datetime.now(_app.timezone.utc).replace(tzinfo=None)
                             if status == 'Completed' else None)
        if task.source_contact:
            linked = [task.source_contact]
            if task.source_contact.supporter_key:
                linked = _app.db.session.scalars(select(_app.Contact).where(
                    _app.Contact.supporter_key == task.source_contact.supporter_key)).all()
            if status == 'Completed':
                for contact in linked:
                    if contact.status == 'To contact':
                        contact.status = 'Contacted'
            elif status == 'Cancelled':
                for contact in linked:
                    if contact.status == 'To contact':
                        contact.status = 'Paused'
        add_audit(f'Changed task #{task.id} status to {status}')
        _app.db.session.commit()
        _app.flash('Task status updated.')
        return _app.redirect(_app.url_for('task_detail', task_id=task.id))

    @app.post('/tasks/<int:task_id>/subtasks')
    def add_subtask(task_id):
        parent = visible_task_or_403(task_id)
        if parent.parent_id is not None:
            _app.abort(400, 'Subtasks cannot contain another level of subtasks.')
        user = task_user()
        title = _app.request.form.get('title', '').strip()[:240]
        if not title:
            _app.abort(400, 'Subtask title is required.')
        assignee = active_assignee() if task_is_admin(user) else user
        priority = _app.request.form.get('priority', parent.priority)
        if priority not in TASK_PRIORITIES:
            _app.abort(400, 'Choose a valid priority.')
        subtask = StaffTask(
            parent_id=parent.id, family_id=parent.family_id,
            assigned_to=assignee.id, created_by=user.id, title=title,
            description=_app.request.form.get('description', '').strip()[:5000],
            priority=priority, due_date=parsed_due_date())
        _app.db.session.add(subtask)
        add_audit(f'Added subtask to task #{parent.id}: {title}')
        _app.db.session.commit()
        _app.flash('Subtask added.')
        return _app.redirect(_app.url_for('task_detail', task_id=parent.id))

    return register_native_payments(app)


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
