"""Batch address-only spreadsheet imports into canonical people and case links."""
import hashlib
import json

from sqlalchemy import select
import app_original as core
from person_names import PersonNames, detected_names
from person_addresses import PersonAddressDetails, FIELDS


def row_identity(row):
    # Match only an exact source record. Never merge people just by their name.
    payload = {k: v for k, v in row.items() if k != 'row'}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return 'sheet:' + digest[:14]  # Fits the existing normalized_phone column.


def import_without_phones(app, profile_model, task_model, rows, family_id,
                          relationship, actor, assignee):
    db = core.db
    unique = {}
    duplicates = 0
    for row in rows:
        key = row_identity(row)
        if key in unique:
            duplicates += 1
        else:
            unique[key] = row
    if not unique:
        return 0, duplicates, 0
    profiles = {p.normalized_phone: p for p in db.session.scalars(select(profile_model).where(
        profile_model.normalized_phone.in_(unique))).all()}
    duplicates += len(profiles)
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
        person_ids = [p.person_id for p in profiles.values()]
        existing = set(db.session.scalars(select(core.Contact.person_id).where(
            core.Contact.family_id == family_id, core.Contact.person_id.in_(person_ids))).all())
        targets = db.session.scalars(select(core.SupporterPerson).where(
            core.SupporterPerson.id.in_(set(person_ids) - existing))).all()
        if targets:
            snapshot = ('name', 'phone', 'email', 'home_phone', 'cell_phone',
                        'home_address', 'city', 'state', 'zip_code', 'workplace', 'work_phone', 'notes')
            db.session.execute(core.Contact.__table__.insert(), [dict(
                **{f: getattr(p, f) for f in snapshot}, person_id=p.id,
                family_id=family_id, relationship=relationship, supporter_key=p.identity_key,
                monthly_cents=0, pledge_frequency='Monthly', status='To contact') for p in targets])
            contacts = db.session.scalars(select(core.Contact).where(
                core.Contact.family_id == family_id,
                core.Contact.person_id.in_([p.id for p in targets]))).all()
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
    return len(new), duplicates, linked
