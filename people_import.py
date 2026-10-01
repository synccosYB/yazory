"""Batch address-only spreadsheet imports into canonical people and case links."""
import hashlib
import json

from sqlalchemy import select
import app_original as core
from person_names import PersonNames, detected_names
from person_addresses import PersonAddressDetails, FIELDS
from duplicate_watch import (duplicate_address_message, existing_name_address_map,
                             row_name_address_key)


def row_identity(row):
    # Address-only imports need a durable synthetic key because there is no
    # phone number to anchor identity. Use stable person/contact fields only;
    # source row numbers, notes, and relationship metadata must not create a
    # second person on a later upload. Name alone is intentionally insufficient.
    stable_fields = (
        'name', 'english_name', 'yiddish_name', 'email',
        'home_street', 'home_unit', 'home_city', 'home_state',
        'home_zip_code', 'home_country', 'work_company', 'work_street',
        'work_unit', 'work_city', 'work_state', 'work_zip_code',
        'work_country',
    )
    payload = {key: (row.get(key) or '').strip() for key in stable_fields}
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return 'sheet:' + digest[:14]  # Fits the existing normalized_phone column.


def import_without_phones(app, profile_model, task_model, rows, family_id,
                          relationship, actor, assignee):
    db = core.db
    unique = {}
    duplicates = 0
    warnings = []
    address_people = existing_name_address_map()
    seen_addresses = {}
    for row in rows:
        key = row_identity(row)
        address_key = row_name_address_key(row)
        existing_person = address_people.get(address_key) if address_key else None
        # Protect an existing canonical identity from an ambiguous address-only
        # import. Within the same new spreadsheet, however, keep separate rows
        # separate: household members and repeated names are not auto-merged.
        if existing_person is not None and family_id is None:
            duplicates += 1
            warnings.append(duplicate_address_message(row['row'], existing_person))
            continue
        if address_key and address_key in seen_addresses:
            pass
        if key in unique:
            duplicates += 1
        else:
            unique[key] = row
            if address_key:
                seen_addresses[address_key] = row['row']
    if not unique:
        return 0, duplicates, 0, warnings
    profiles = {p.normalized_phone: p for p in db.session.scalars(select(profile_model).where(
        profile_model.normalized_phone.in_(unique))).all()}
    if family_id is None:
        duplicates += len(profiles)
        # Global directory imports do not silently reuse an existing identity.
        unique = {key: row for key, row in unique.items() if key not in profiles}
    new = {key: row for key, row in unique.items() if key not in profiles}
    people = core.SupporterPerson.__table__
    if new:
        db.session.execute(people.insert(), [dict(
            identity_key='phone:' + key, name=row['name'][:160], phone='', cell_phone='',
            email=row['email'][:254], home_address=row['home_street'][:240],
            city=row['home_city'][:120], state=row['home_state'][:80],
            zip_code=row['home_zip_code'][:20], workplace=row['work_company'][:160],
            notes=row.get('notes', '')[:5000]) for key, row in new.items()])
        inserted = {p.identity_key: p for p in db.session.scalars(select(core.SupporterPerson).where(
            core.SupporterPerson.identity_key.in_(['phone:' + k for k in new]))).all()}
        db.session.execute(profile_model.__table__.insert(), [dict(
            person_id=inserted['phone:' + key].id, normalized_phone=key,
            name=row['name'][:160], phone='', email=row['email'][:254]) for key, row in new.items()])
        names, addresses = [], []
        for key, row in new.items():
            person_id = inserted['phone:' + key].id
            en, yi = detected_names(row['name'][:160])
            names.append(dict(owner_kind='person', owner_id=person_id, field='name',
                              english_name=row['english_name'][:160] or en,
                              yiddish_name=row['yiddish_name'][:160] or yi))
            home = {f: row.get('home_' + f, '')[:limit] for f, limit in FIELDS.items()
                    if f not in ('street', 'city', 'state', 'zip_code') and row.get('home_' + f)}
            work = {f: row.get('work_' + f, '')[:limit] for f, limit in FIELDS.items()
                    if f != 'company' and row.get('work_' + f)}
            if home or work:
                addresses.append(dict(person_kind='person', person_id=person_id,
                                      home=home, work=work, mailing_preference=''))
        db.session.execute(PersonNames.__table__.insert(), names)
        if addresses:
            db.session.execute(PersonAddressDetails.__table__.insert(), addresses)
        profiles = {p.normalized_phone: p for p in db.session.scalars(select(profile_model).where(
            profile_model.normalized_phone.in_(unique))).all()}
    linked = 0
    from book_directory import preload_family_connections, save_family_names
    preload_family_connections(p.person_id for p in profiles.values())
    for key, row in unique.items():
        save_family_names(profiles[key].person_id, row)
    if family_id is not None:
        # Preserve every imported profile/person independently. Do not reduce
        # this through a set before deciding which case-specific rows are
        # missing; the canonical profile key is the import identity.
        person_ids = [profile.person_id for profile in profiles.values()]
        existing = set(db.session.scalars(select(core.Contact.person_id).where(
            core.Contact.family_id == family_id,
            core.Contact.person_id.in_(person_ids))).all())
        missing_person_ids = [person_id for person_id in person_ids
                              if person_id not in existing]
        targets_by_id = {p.id: p for p in db.session.scalars(
            select(core.SupporterPerson).where(
                core.SupporterPerson.id.in_(missing_person_ids))).all()}
        targets = [targets_by_id[person_id] for person_id in missing_person_ids
                   if person_id in targets_by_id]
        if targets:
            snapshot = ('name', 'phone', 'email', 'home_phone', 'cell_phone',
                        'home_address', 'city', 'state', 'zip_code', 'workplace', 'work_phone', 'notes')
            db.session.execute(core.Contact.__table__.insert(), [dict(
                **{f: getattr(p, f) for f in snapshot}, person_id=p.id,
                family_id=family_id, relationship=relationship, supporter_key=p.identity_key,
                monthly_cents=0, pledge_frequency='Monthly', status='To contact') for p in targets])
            target_ids = {p.id for p in targets}
            contacts = db.session.scalars(select(core.Contact).where(
                core.Contact.family_id == family_id,
                core.Contact.person_id.in_(target_ids))).all()
            # Bulk inserts bypass the ORM identity map; explicitly verify every
            # intended canonical person received its case row before creating
            # workflow links.
            contact_by_person = {c.person_id: c for c in contacts}
            missing_ids = target_ids - set(contact_by_person)
            if missing_ids:
                raise RuntimeError(
                    f'Case link insert incomplete for family {family_id}: '
                    f'missing person ids {sorted(missing_ids)}')
            contacts = [contact_by_person[person_id] for person_id in target_ids]
            link_model = app.extensions['workflows']['models']['SupporterLink']
            db.session.execute(link_model.__table__.insert(), [dict(
                contact_id=c.id, side='Community', relationship=relationship,
                assigned_to=actor.id if actor and actor.role == 'fundraiser' else None,
                permission='Not requested', preference='', verified=False) for c in contacts])
            if assignee:
                db.session.execute(task_model.__table__.insert(), [dict(
                    family_id=family_id, source_contact_id=c.id,
                    assigned_to=assignee.id, created_by=assignee.id,
                    title=f'Contact supporter: {c.name}', description='', priority='Normal') for c in contacts])
            linked = len(contacts)
    return len(new), duplicates, linked, warnings
