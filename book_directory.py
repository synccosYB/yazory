"""Directory-book references on canonical people, independent of case membership.

Names are evidence, not relationship keys. Parent references resolve only by
the exact source and printed ID, including targets imported on later pages.
"""
import hashlib

from flask import abort, flash, redirect, request, url_for
from flask import g, has_request_context
from sqlalchemy import UniqueConstraint, event, select, tuple_
import app_original as core
from person_names import detected_names, save_names
from person_addresses import save_new_supporter_addresses
from duplicate_watch import (duplicate_address_message, existing_name_address_map,
                             row_name_address_key)

db = core.db
FIELDS = {
    'first_name': 160, 'last_name': 160, 'father_name': 240,
    'father_inlaw_name': 240, 'father_book_id': 80,
    'father_inlaw_book_id': 80, 'relationship_text': 1000,
    'source_ref': 500, 'notes': 5000, 'review': 1000,
}


class PersonBookRecord(db.Model):
    __tablename__ = 'person_book_record'
    __table_args__ = (
        UniqueConstraint('source', 'book_id', name='uq_person_book_reference'),
        UniqueConstraint('source', 'person_id', name='uq_person_book_owner'),
    )
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'), nullable=False, index=True)
    source = db.Column(db.String(120), nullable=False)
    book_id = db.Column(db.String(80), nullable=False)
    first_name = db.Column(db.String(160), nullable=False, default='')
    last_name = db.Column(db.String(160), nullable=False, default='')
    father_name = db.Column(db.String(240), nullable=False, default='')
    father_inlaw_name = db.Column(db.String(240), nullable=False, default='')
    father_book_id = db.Column(db.String(80), nullable=False, default='')
    father_inlaw_book_id = db.Column(db.String(80), nullable=False, default='')
    relationship_text = db.Column(db.String(1000), nullable=False, default='')
    source_ref = db.Column(db.String(500), nullable=False, default='')
    notes = db.Column(db.Text, nullable=False, default='')
    review = db.Column(db.String(1000), nullable=False, default='')


class PersonFamilyConnection(db.Model):
    """One family record on the person, regardless of books or case roles."""
    __tablename__ = 'person_family_connection'
    person_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'), primary_key=True)
    father_name = db.Column(db.String(240), nullable=False, default='')
    father_inlaw_name = db.Column(db.String(240), nullable=False, default='')
    father_person_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'), nullable=True)
    father_inlaw_person_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'), nullable=True)
    father_manually_set = db.Column(db.Boolean, nullable=False, default=False)
    father_inlaw_manually_set = db.Column(db.Boolean, nullable=False, default=False)


def resolve_family_references(sources):
    """Explicit external references may fill canonical links, never override them."""
    records = db.session.scalars(select(PersonBookRecord).where(
        PersonBookRecord.source.in_(sources))).all()
    _apply_family_references(records)


def _apply_family_references(records):
    by_key = {(r.source, r.book_id): r for r in records}
    person_ids = {r.person_id for r in records}
    families = preload_family_connections(person_ids)
    for record in records:
        family = families.get(record.person_id)
        if family is None:
            family = PersonFamilyConnection(person_id=record.person_id)
            db.session.add(family)
            families[record.person_id] = family
            cache = _request_family_cache()
            if cache is not None:
                cache[record.person_id] = family
        for kind in ('father', 'father_inlaw'):
            if getattr(family, kind + '_manually_set'):
                continue
            name_field = kind + '_name'
            if not getattr(family, name_field):
                setattr(family, name_field, getattr(record, name_field))
            target = by_key.get((record.source, getattr(record, kind + '_book_id')))
            if target and target.person_id != record.person_id and not getattr(family, kind + '_person_id'):
                setattr(family, kind + '_person_id', target.person_id)


def resolve_import_family_references(reference_keys):
    """Resolve this import's rows and rows which explicitly point to them."""
    reference_keys = set(reference_keys)
    if not reference_keys:
        return
    own = db.session.scalars(select(PersonBookRecord).where(tuple_(
        PersonBookRecord.source, PersonBookRecord.book_id
    ).in_(reference_keys))).all()
    dependents = db.session.scalars(select(PersonBookRecord).where(
        tuple_(PersonBookRecord.source, PersonBookRecord.father_book_id).in_(reference_keys) |
        tuple_(PersonBookRecord.source, PersonBookRecord.father_inlaw_book_id).in_(reference_keys)
    )).all()
    records = list({record.id: record for record in (*own, *dependents)}.values())
    target_keys = {(r.source, ref) for r in records for ref in
                   (r.father_book_id, r.father_inlaw_book_id) if ref}
    targets = db.session.scalars(select(PersonBookRecord).where(tuple_(
            PersonBookRecord.source, PersonBookRecord.book_id
        ).in_(target_keys))).all() if target_keys else []
    by_key = {(r.source, r.book_id): r for r in targets}
    family_rows = preload_family_connections({r.person_id for r in records})
    for record in records:
        family = family_rows.get(record.person_id)
        if family is None:
            family = PersonFamilyConnection(person_id=record.person_id)
            db.session.add(family)
            family_rows[record.person_id] = family
            cache = _request_family_cache()
            if cache is not None:
                cache[record.person_id] = family
        for kind in ('father', 'father_inlaw'):
            if getattr(family, kind + '_manually_set'):
                continue
            name_field = kind + '_name'
            if not getattr(family, name_field):
                setattr(family, name_field, getattr(record, name_field))
            target = by_key.get((record.source, getattr(record, kind + '_book_id')))
            if target and target.person_id != record.person_id and not getattr(
                    family, kind + '_person_id'):
                setattr(family, kind + '_person_id', target.person_id)


def _request_family_cache():
    if (not has_request_context() or not (
            getattr(g, '_batch_person_import', False) or
            getattr(g, '_person_family_preload_enabled', False))):
        return None
    transaction = db.session().get_transaction()
    if transaction is None:
        db.session().begin()
        transaction = db.session().get_transaction()
    cache = getattr(g, '_person_family_connection_cache', None)
    if cache is None or cache[0] is not transaction:
        cache = (transaction, {})
        g._person_family_connection_cache = cache
    return cache[1]


def _remember_family_connection(mapper, connection, row):
    cache = _request_family_cache()
    if cache is not None:
        cache[row.person_id] = row


for _event_name in ('after_insert', 'after_update'):
    if not event.contains(PersonFamilyConnection, _event_name,
                          _remember_family_connection):
        event.listen(PersonFamilyConnection, _event_name,
                     _remember_family_connection)


def preload_family_connections(person_ids):
    """Batch and cache requested family rows, including missing rows."""
    person_ids = set(person_ids)
    if not person_ids:
        return {}
    if has_request_context():
        g._person_family_preload_enabled = True
    cache = _request_family_cache()
    if cache is None:
        cache = {}
    cached = cache
    missing = person_ids - cached.keys()
    if missing:
        rows = db.session.scalars(select(PersonFamilyConnection).where(
            PersonFamilyConnection.person_id.in_(missing))).all()
        by_id = {row.person_id: row for row in rows}
        cache.update({person_id: by_id.get(person_id) for person_id in missing})
    return {person_id: cache.get(person_id) for person_id in person_ids}


def family_context(person_id, profile_model):
    family = db.session.get(PersonFamilyConnection, person_id)
    refs = [getattr(family, f) for f in ('father_person_id', 'father_inlaw_person_id')] if family else []
    relatives = {}
    if any(refs):
        for person, profile in db.session.execute(select(core.SupporterPerson, profile_model).outerjoin(
                profile_model, profile_model.person_id == core.SupporterPerson.id).where(
                core.SupporterPerson.id.in_([p for p in refs if p]))).all():
            relatives[person.id] = dict(person=person, profile=profile)
    dependents = []
    for connection, person, profile in db.session.execute(select(
            PersonFamilyConnection, core.SupporterPerson, profile_model).join(
            core.SupporterPerson, core.SupporterPerson.id == PersonFamilyConnection.person_id).outerjoin(
            profile_model, profile_model.person_id == PersonFamilyConnection.person_id).where(core.or_(
            PersonFamilyConnection.father_person_id == person_id,
            PersonFamilyConnection.father_inlaw_person_id == person_id))).all():
        dependents.append(dict(person=person, profile=profile,
            child=connection.father_person_id == person_id,
            child_inlaw=connection.father_inlaw_person_id == person_id))
    return dict(family_connection=family, family_dependents=dependents,
                father_connection=relatives.get(family.father_person_id) if family else None,
                father_inlaw_connection=relatives.get(family.father_inlaw_person_id) if family else None)


def save_family_names(person_id, row):
    if not row.get('father_name') and not row.get('father_inlaw_name'):
        return
    if (has_request_context() and (
            getattr(g, '_batch_person_import', False) or
            getattr(g, '_person_family_preload_enabled', False))):
        family = preload_family_connections({person_id}).get(person_id)
    else:
        family = db.session.get(PersonFamilyConnection, person_id)
    if family is None:
        family = PersonFamilyConnection(person_id=person_id)
        db.session.add(family)
        cache = _request_family_cache()
        if cache is not None:
            cache[person_id] = family
    for field in ('father_name', 'father_inlaw_name'):
        if row.get(field) and not getattr(family, field):
            setattr(family, field, row[field][:240])


def import_book_rows(app, profile_model, rows, default_source, family_id,
                     relationship, connect, normalize, canonical):
    result = dict(created=0, updated=0, duplicates=0, skipped=0, linked=0, errors=[])
    if not rows:
        return result
    keys = {(r['book_source'] or default_source, r['book_id']) for r in rows}
    sources = {key[0] for key in keys}
    records = db.session.scalars(select(PersonBookRecord).where(tuple_(
        PersonBookRecord.source, PersonBookRecord.book_id
    ).in_(keys))).all()
    by_key = {(r.source, r.book_id): r for r in records}
    phones = {normalize(r['phone']) for r in rows if r['phone']}
    profiles = db.session.scalars(select(profile_model).where(core.or_(
        profile_model.normalized_phone.in_(phones),
        profile_model.person_id.in_([r.person_id for r in records if (r.source, r.book_id) in keys])))).all()
    by_phone = {p.normalized_phone: p for p in profiles}
    by_person = {p.person_id: p for p in profiles if p.person_id}
    canonical_people = (app.extensions['supporter_identity']['preload_profiles'](profiles)
                        if profiles else {})
    case_keys = {person.identity_key for person in canonical_people.values()}
    case_keys.update('phone:' + normalize(row['phone']) for row in rows if row['phone'])
    for row in rows:
        if not row['phone']:
            digest = hashlib.sha256(
                ((row['book_source'] or default_source) + '\0' + row['book_id']).encode()
            ).hexdigest()[:15]
            case_keys.add('phone:book:' + digest)
    known_people = app.extensions['supporter_identity']['preload_people'](case_keys)
    person_ids = {p.person_id for p in profiles if p.person_id}
    person_ids.update(person.id for person in canonical_people.values())
    person_ids.update(person.id for person in known_people.values() if person is not None)
    profile_person_ids = set(person_ids)
    owner_records = db.session.scalars(select(PersonBookRecord).where(
        PersonBookRecord.source.in_(sources),
        PersonBookRecord.person_id.in_(profile_person_ids))).all() if profile_person_ids else []
    owner_ids = {(r.source, r.person_id): r.book_id for r in (*records, *owner_records)}
    from person_addresses import preload_addresses
    from person_names import preload_names
    preload_names({('person', person_id, 'name') for person_id in person_ids})
    preload_addresses({('person', person_id) for person_id in person_ids})
    existing_person_ids = set(person_ids)
    if family_id is not None:
        app.extensions['supporter_identity']['preload_case_links'](family_id, case_keys)
    resolved_keys = set()
    changed_people = {}
    seen = set()
    address_people = existing_name_address_map()
    for row in rows:
        source, ident = row['book_source'] or default_source, row['book_id']
        key = source, ident
        phone = normalize(row['phone'])
        error = ''
        if len(source) > 120 or len(ident) > 80 or not row['name']:
            error = 'Invalid book reference or missing name.'
        elif row['phone'] and not phone:
            error = 'Invalid phone number.'
        elif any(len(row.get(f, '')) > limit for f, limit in FIELDS.items()):
            error = 'Book details exceed the field length.'
        elif ident in (row['father_book_id'], row['father_inlaw_book_id']):
            error = 'A person cannot be their own father or father-in-law.'
        if key in seen:
            result['duplicates'] += 1
            result['errors'].append(f"Row {row['row']}: repeated book ID {ident}.")
            continue
        seen.add(key)
        record = by_key.get(key)
        profile = by_person.get(record.person_id) if record else by_phone.get(phone)
        phone_owner = by_phone.get(phone) if phone else None
        if record and phone_owner and phone_owner.person_id != record.person_id:
            error = 'Book ID and phone identify different people. Check the record before importing.'
        if not record and profile:
            person = canonical(profile)
            other_id = owner_ids.get((source, person.id))
            if other_id and other_id != ident:
                error = 'This phone already belongs to a different book ID in this book.'
        if record and not profile:
            error = 'Book person has no directory profile. Repair the record before importing.'
        if error:
            result['skipped'] += 1
            result['errors'].append(f"Row {row['row']}, book ID {ident}: {error}")
            continue
        is_new = profile is None
        if not profile:
            address_key = row_name_address_key(row)
            existing_person = address_people.get(address_key) if address_key else None
            if existing_person is not None:
                result['duplicates'] += 1
                result['skipped'] += 1
                result['errors'].append(
                    duplicate_address_message(row['row'], existing_person, book_id=ident)
                )
                continue
            digest = hashlib.sha256((source + '\0' + ident).encode()).hexdigest()[:15]
            profile = profile_model(name=row['name'][:160], phone=row['phone'][:80],
                normalized_phone=phone or 'book:' + digest, email=row['email'][:254])
            db.session.add(profile)
            # Allocate this profile's key without prematurely updating every
            # earlier import row still pending in the unit of work.
            if (has_request_context() and
                    getattr(g, '_batch_book_import', False)):
                db.session.flush([profile])
            else:
                db.session.flush()
            person = canonical(profile)
            by_phone[profile.normalized_phone] = profile
            by_person[person.id] = profile
            result['created'] += 1
        else:
            person = canonical(profile)
            result['duplicates'] += 1
        changed = False
        if record is None:
            record = PersonBookRecord(person_id=person.id, source=source, book_id=ident)
            db.session.add(record)
            by_key[key] = record
            owner_ids[(source, person.id)] = ident
            changed = True
        resolved_keys.add(key)
        for field, limit in FIELDS.items():
            value = row.get(field, '')
            if value and not getattr(record, field):
                setattr(record, field, value[:limit])
                changed = True
            elif value and getattr(record, field) != value:
                result['errors'].append(f"Row {row['row']}, book ID {ident}: existing {field} kept. Review the difference.")
        if not person.phone and phone:
            profile.phone = person.phone = row['phone'][:80]
            profile.normalized_phone = phone
            by_phone[phone] = profile
            changed = True
        if not person.email and row['email']:
            person.email = profile.email = row['email'][:254]
            changed = True
        if not person.notes and row.get('notes'):
            person.notes = row['notes'][:5000]
            changed = True
        en, yi = detected_names(row['name'])
        save_names('person', person.id, row['english_name'] or en,
                   row['yiddish_name'] or yi, fill_only=True, legacy=person.name,
                   known_missing=person.id not in existing_person_ids)
        # Same address owner as every other import and case profile.
        from person_addresses import address_details, home_values
        details = (None if person.id not in existing_person_ids else
                   address_details('person', person.id))
        home = home_values(person, details)
        work = dict(details.work or {}) if details else {}
        address_row = dict(row)
        for prefix, current in (('home', home), ('work', work)):
            for field in ('street', 'unit', 'city', 'state', 'zip_code', 'country', 'company'):
                if current.get(field) or (prefix == 'work' and field == 'company' and person.workplace):
                    address_row.pop(prefix + '_' + field, None)
        target = core.Contact(person_id=person.id)
        save_new_supporter_addresses(
            app, target, address_row, person=person, details=details, sync=False)
        # Another row in this upload may reference this same person from a
        # different book source. Its names/address now exist in the write-through
        # caches and must be read rather than treated as absent a second time.
        existing_person_ids.add(person.id)
        changed_people[person.id] = person
        if family_id is not None:
            result['linked'] += int(connect(profile, family_id, relationship) is not None)
        result['updated'] += int(changed and not is_new)
    app.extensions['supporter_identity']['sync_many'](changed_people.values())
    db.session.flush()
    resolve_import_family_references(resolved_keys)
    return result


def book_context(person_id, profile_model):
    records = db.session.scalars(select(PersonBookRecord).where(
        PersonBookRecord.person_id == person_id).order_by(PersonBookRecord.source)).all()
    keys = {(r.source, ref) for r in records for ref in
            (r.father_book_id, r.father_inlaw_book_id) if ref}
    relatives = {}
    if keys:
        for record, person, profile in db.session.execute(select(
                PersonBookRecord, core.SupporterPerson, profile_model).join(
                core.SupporterPerson, core.SupporterPerson.id == PersonBookRecord.person_id).outerjoin(
                profile_model, profile_model.person_id == PersonBookRecord.person_id).where(
                tuple_(PersonBookRecord.source, PersonBookRecord.book_id).in_(keys))).all():
            relatives[(record.source, record.book_id)] = dict(person=person, profile=profile)
    return [dict(record=r, father=relatives.get((r.source, r.father_book_id)),
                 father_inlaw=relatives.get((r.source, r.father_inlaw_book_id))) for r in records]


def install(app, profile_model, access):
    @app.post('/supporter-directory/<int:profile_id>/family-connections')
    def edit_person_family_connections(profile_id):
        access()
        profile = db.get_or_404(profile_model, profile_id)
        person = app.extensions['supporter_identity']['profile_person'](profile)
        values = {}
        for kind in ('father', 'father_inlaw'):
            ref = request.form.get(kind + '_person_id', '').strip()
            if ref:
                if not ref.isdigit() or int(ref) == person.id:
                    abort(400)
                db.get_or_404(core.SupporterPerson, int(ref))
            values[kind + '_person_id'] = int(ref) if ref else None
            values[kind + '_name'] = request.form.get(kind + '_name', '').strip()
            if len(values[kind + '_name']) > 240:
                abort(400)
        family = db.session.get(PersonFamilyConnection, person.id)
        if family is None:
            family = PersonFamilyConnection(person_id=person.id)
            db.session.add(family)
        for f, value in values.items():
            setattr(family, f, value)
        family.father_manually_set = family.father_inlaw_manually_set = True
        db.session.commit()
        flash('Family connections saved.')
        return redirect(url_for('edit_supporter_profile', profile_id=profile.id, _anchor='family-connections'))

    @app.post('/supporter-directory/<int:profile_id>/book/<int:record_id>')
    def edit_person_book(profile_id, record_id):
        access()
        profile = db.get_or_404(profile_model, profile_id)
        record = db.get_or_404(PersonBookRecord, record_id)
        if record.person_id != profile.person_id:
            abort(404)
        values = {f: request.form.get(f, '').strip() for f in FIELDS}
        if any(len(values[f]) > limit for f, limit in FIELDS.items()):
            abort(400)
        if record.book_id in (values['father_book_id'], values['father_inlaw_book_id']):
            abort(400)
        for f, value in values.items():
            setattr(record, f, value)
        db.session.flush()
        resolve_family_references({record.source})
        db.session.commit()
        flash('Book details saved.')
        return redirect(url_for('edit_supporter_profile', profile_id=profile.id, _anchor='book-details'))
