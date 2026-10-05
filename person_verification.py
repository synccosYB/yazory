"""Value-specific canonical person verification; legacy data stays authoritative."""
import hashlib
import json
from datetime import datetime, timezone

import app_original as core
from flask import abort, jsonify, request
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from person_names import PersonNames, save_names, detected_names
from person_addresses import PersonAddressDetails

db = core.db
FIELDS = {
    'identity': 'Person identity', 'name': 'Name', 'home_phone': 'Home phone',
    'cell_phone': 'Cell phone', 'phone': 'Phone', 'email': 'Email',
    'home_address': 'Home address', 'workplace': 'Workplace',
    'work_phone': 'Work phone', 'work_address': 'Work address', 'notes': 'Notes',
}


class PersonVerification(db.Model):
    __tablename__ = 'person_verification'
    __table_args__ = (db.Index('ix_person_verification_latest', 'person_id', 'field', 'id'),)
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'), nullable=False, index=True)
    field = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    checked_value = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.String(1000), nullable=False, default='')
    reviewed_by = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True)
    reviewer = db.Column(db.String(254), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    expired = db.Column(db.Boolean, nullable=False, default=False)


def values(person):
    name = db.session.scalar(select(PersonNames).where(
        PersonNames.owner_kind == 'person', PersonNames.owner_id == person.id,
        PersonNames.field == 'name'))
    address = db.session.scalar(select(PersonAddressDetails).where(
        PersonAddressDetails.person_kind == 'person', PersonAddressDetails.person_id == person.id))
    result = {field: getattr(person, field, '') or '' for field in FIELDS}
    # Identity confirmation is independent of the person's mutable contact details.
    result['identity'] = person.identity_key
    # The bilingual row is canonical for name variants. Do not render person.name
    # beside english_name when they are the same value.
    if name:
        result['name'] = [name.english_name or '', name.yiddish_name or '']
    else:
        result['name'] = list(detected_names(person.name or ''))
    result['home_address'] = [person.home_address or '', person.city or '',
                              person.state or '', person.zip_code or '', address.home if address else {}]
    result['work_address'] = address.work if address else {}
    return result



def update_value(person, field, form):
    """Apply an in-place verification edit to the existing canonical records."""
    if field == 'identity':
        return
    if field == 'name':
        english = form.get('english_name', '').strip()
        yiddish = form.get('yiddish_name', '').strip()
        save_names('person', person.id, english, yiddish, legacy=person.name or '')
        # Keep the legacy display column aligned without creating another source.
        person.name = english or yiddish
        return
    if field in ('home_address', 'work_address'):
        details = db.session.scalar(select(PersonAddressDetails).where(
            PersonAddressDetails.person_kind == 'person',
            PersonAddressDetails.person_id == person.id))
        if details is None:
            details = PersonAddressDetails(person_kind='person', person_id=person.id,
                                           home={}, work={})
            db.session.add(details)
        if field == 'home_address':
            person.home_address = form.get('street', '').strip()
            person.city = form.get('city', '').strip()
            person.state = form.get('state', '').strip()
            person.zip_code = form.get('zip_code', '').strip()
            details.home = {
                key: form.get(key, '').strip() for key in ('unit', 'country')
                if form.get(key, '').strip()
            }
        else:
            details.work = {
                key: form.get(key, '').strip()
                for key in ('street', 'unit', 'city', 'state', 'zip_code', 'country')
                if form.get(key, '').strip()
            }
        return
    value = form.get('value', '').strip()
    column = getattr(person.__table__.columns, field, None)
    if column is None:
        abort(400)
    limit = getattr(column.type, 'length', None)
    if limit and len(value) > limit:
        abort(400)
    setattr(person, field, value)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def statuses(person, current=None):
    current = values(person) if current is None else current
    latest_ids = select(db.func.max(PersonVerification.id)).where(
        PersonVerification.person_id == person.id).group_by(PersonVerification.field)
    rows = db.session.scalars(select(PersonVerification).where(
        PersonVerification.id.in_(latest_ids))).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.field, row)
    result = {}
    for field, value in current.items():
        row = latest.get(field)
        digest = fingerprint(value)
        valid = row and not row.expired and row.fingerprint == digest
        result[field] = dict(status=row.status if valid else 'unverified', fingerprint=digest,
                             reason=row.reason if valid else '', reviewer=row.reviewer if valid else '',
                             date=row.created_at.isoformat() + 'Z' if valid else '')
    return result


def expire_changed_values(session, flush_context, instances):
    """Expire prior assertions on ORM edits/imports, including change-and-revert."""
    changed = {}
    for row in set(session.dirty) | set(session.new) | set(session.deleted):
        state = inspect(row)
        attrs = {attr.key for attr in state.attrs if attr.history.has_changes()}
        if row in session.deleted:
            attrs = set(state.attrs.keys())
        if isinstance(row, core.SupporterPerson):
            if not state.persistent:
                continue
            fields = attrs & (FIELDS.keys() - {'identity', 'name', 'home_address', 'work_address'})
            if 'name' in attrs:
                fields.add('name')
            if attrs & {'home_address', 'city', 'state', 'zip_code'}:
                fields.add('home_address')
            if 'identity_key' in attrs:
                fields.add('identity')
            owner = row.id
        elif isinstance(row, PersonNames) and row.owner_kind == 'person' and row.field == 'name':
            owner, fields = row.owner_id, {'name'} if attrs & {'english_name', 'yiddish_name'} else set()
        elif isinstance(row, PersonAddressDetails) and row.person_kind == 'person':
            owner, fields = row.person_id, set()
            if 'home' in attrs:
                fields.add('home_address')
            if 'work' in attrs:
                fields.add('work_address')
        else:
            continue
        if fields:
            changed.setdefault(owner, set()).update(fields)
    # One batched UPDATE for the transaction, never a query per field.
    if changed:
        conditions = [(PersonVerification.person_id == owner) & PersonVerification.field.in_(fields)
                      for owner, fields in changed.items()]
        session.execute(db.update(PersonVerification).where(
            db.or_(*conditions), PersonVerification.expired.is_(False)).values(expired=True))


if not event.contains(Session, 'before_flush', expire_changed_values):
    event.listen(Session, 'before_flush', expire_changed_values)


def install(app, access):
    @app.get('/people/<int:person_id>/verification')
    def get_person_verification(person_id):
        access()
        person = db.get_or_404(core.SupporterPerson, person_id)
        current = values(person)
        history = db.session.scalars(select(PersonVerification).where(
            PersonVerification.person_id == person.id).order_by(PersonVerification.id.desc()).limit(30)).all()
        return jsonify(fields=statuses(person, current), values=current, history=[dict(
            field=row.field, status=row.status, reason=row.reason, reviewer=row.reviewer,
            date=row.created_at.isoformat() + 'Z', expired=row.expired or row.fingerprint != fingerprint(current.get(row.field)),
            value=row.checked_value if row.field != 'identity' else '') for row in history])

    @app.post('/people/<int:person_id>/verification/<field>')
    def set_person_verification(person_id, field):
        user = access()
        if user is not None and user.role != 'organization_admin':
            abort(403)
        if field not in FIELDS:
            abort(400)
        person = db.session.scalar(select(core.SupporterPerson).where(
            core.SupporterPerson.id == person_id).with_for_update())
        if person is None:
            abort(404)
        status = request.form.get('status')
        reason = request.form.get('reason', '').strip()
        if status not in ('verified', 'unverified', 'incorrect') or len(reason) > 1000:
            abort(400)
        current = values(person)
        digest = fingerprint(current[field])
        if request.form.get('fingerprint') != digest:
            abort(409)
        update_value(person, field, request.form)
        db.session.flush()
        current = values(person)
        digest = fingerprint(current[field])
        check_values = current[field] if isinstance(current[field], list) else [current[field]]
        if status == 'verified' and field != 'identity' and not any(
                value for value in check_values if not isinstance(value, dict)):
            abort(400)
        db.session.add(PersonVerification(person_id=person.id, field=field, status=status,
            fingerprint=digest, checked_value=current[field], reason=reason, reviewed_by=user.id if user else None,
            reviewer=(user.name or user.email) if user else 'Demo'))
        db.session.commit()
        return jsonify(fields=statuses(person, current))

    app.jinja_env.globals['verification_fields'] = FIELDS
    app.extensions.setdefault('init_db_hooks', []).append(lambda: PersonVerification.__table__.create(db.engine, checkfirst=True))
    if app.config['DEMO'] or app.config.get('TESTING'):
        with app.app_context():
            PersonVerification.__table__.create(db.engine, checkfirst=True)
