"""Directory-book references on canonical people, independent of case membership.

Names are evidence, not relationship keys. Parent references resolve only by
the exact source and printed ID, including targets imported on later pages.
"""
import hashlib

from flask import abort, flash, redirect, request, url_for
from sqlalchemy import UniqueConstraint, select, tuple_
import app_original as core
from person_names import detected_names, save_names
from person_addresses import save_new_supporter_addresses

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
    by_key = {(r.source, r.book_id): r for r in records}
    families = {r.person_id: r for r in db.session.scalars(select(PersonFamilyConnection).where(
        PersonFamilyConnection.person_id.in_([r.person_id for r in records]))).all()}
    for record in records:
        family = families.get(record.person_id)
        if family is None:
            family = PersonFamilyConnection(person_id=record.person_id)
            db.session.add(family)
            families[record.person_id] = family
        for kind in ('father', 'father_inlaw'):
            if getattr(family, kind + '_manually_set'):
                continue
            name_field = kind + '_name'
            if not getattr(family, name_field):
                setattr(family, name_field, getattr(record, name_field))
            target = by_key.get((record.source, getattr(record, kind + '_book_id')))
            if target and target.person_id != record.person_id and not getattr(family, kind + '_person_id'):
                setattr(family, kind + '_person_id', target.person_id)


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
    family = db.session.get(PersonFamilyConnection, person_id)
    if family is None:
        family = PersonFamilyConnection(person_id=person_id)
        db.session.add(family)
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
    records = db.session.scalars(select(PersonBookRecord).where(
        PersonBookRecord.source.in_(sources))).all()
    by_key = {(r.source, r.book_id): r for r in records}
    owner_ids = {(r.source, r.person_id): r.book_id for r in records}
    phones = {normalize(r['phone']) for r in rows if r['phone']}
    profiles = db.session.scalars(select(profile_model).where(core.or_(
        profile_model.normalized_phone.in_(phones),
        profile_model.person_id.in_([r.person_id for r in records if (r.source, r.book_id) in keys])))).all()
    by_phone = {p.normalized_phone: p for p in profiles}
    by_person = {p.person_id: p for p in profiles if p.person_id}
    changed_people = {}
    seen = set()
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
            digest = hashlib.sha256((source + '\0' + ident).encode()).hexdigest()[:15]
            profile = profile_model(name=row['name'][:160], phone=row['phone'][:80],
                normalized_phone=phone or 'book:' + digest, email=row['email'][:254])
            db.session.add(profile)
            # Flush identities before processing another row with a shared phone.
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
                   row['yiddish_name'] or yi, fill_only=True, legacy=person.name)
        # Same address owner as every other import and case profile.
        from person_addresses import address_details, home_values
        details = address_details('person', person.id)
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
        changed_people[person.id] = person
        if family_id is not None:
            result['linked'] += int(connect(profile, family_id, relationship) is not None)
        result['updated'] += int(changed and not is_new)
    app.extensions['supporter_identity']['sync_many'](changed_people.values())
    db.session.flush()
    resolve_family_references(sources)
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
