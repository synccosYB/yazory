"""Permanent public numbers on canonical people; issued numbers are retained."""
import hashlib
import secrets
import app_original as core
from flask import g, has_request_context
from sqlalchemy import event, inspect, select
from person_names import PersonNameOwner, PersonNames

db = core.db


class PersonNumber(db.Model):
    __tablename__ = 'person_number'
    __table_args__ = {'sqlite_autoincrement': True}
    id = db.Column(db.Integer, primary_key=True)
    # No cascading FK: deletion leaves a reserved number with no owner.
    person_id = db.Column(db.Integer, unique=True, nullable=True, index=True)


def issue(connection, person_id, new=False):
    table = PersonNumber.__table__
    number = None if new else connection.scalar(select(table.c.id).where(table.c.person_id == person_id))
    if number is None:
        number = connection.execute(table.insert().values(person_id=person_id)).inserted_primary_key[0]
    return number


def formatted(number):
    return f'{number:02d}' if number is not None else ''


def number_for(kind, obj, field='name'):
    if obj is None or not getattr(obj, 'id', None):
        return ''
    from person_names import resolve_name_owner
    if kind in ('profile', 'supporter') and obj.person_id:
        person_id = obj.person_id
    else:
        key = (kind, obj.id, field)
        resolved = getattr(g, '_person_number_owners', {}) if has_request_context() else {}
        owner_kind, person_id, _ = resolved[key] if key in resolved else resolve_name_owner(*key)
        if owner_kind != 'person':
            return ''
    cache = getattr(g, '_person_numbers', {}) if has_request_context() else {}
    if person_id in cache:
        return formatted(cache[person_id])
    return formatted(db.session.scalar(select(PersonNumber.id).where(
        PersonNumber.person_id == person_id)))


def preload_numbers(resolved):
    if not has_request_context():
        return
    owners = getattr(g, '_person_number_owners', {})
    owners.update(resolved)
    g._person_number_owners = owners
    cache = getattr(g, '_person_numbers', {})
    ids = {key[1] for key in resolved.values() if key[0] == 'person'} - cache.keys()
    if ids:
        cache.update({ident: None for ident in ids})
        cache.update(db.session.execute(select(PersonNumber.person_id, PersonNumber.id).where(
            PersonNumber.person_id.in_(ids))).all())
    g._person_numbers = cache


def ensure_role(connection, kind, obj, field, profile_model):
    """Link unrepresented individuals without guessing matches from names/phones."""
    if kind in ('person', 'profile', 'supporter'):
        return
    name = (getattr(obj, field, '') or '').strip()
    if not name and kind == 'staff' and field == 'name':
        name = (obj.email or '').strip()
    if not name:
        return
    aliases = PersonNameOwner.__table__
    condition = (aliases.c.owner_kind == kind) & (aliases.c.owner_id == obj.id) & (aliases.c.field == field)
    if connection.scalar(select(aliases.c.person_id).where(condition)):
        return
    person_id = getattr(obj, '_canonical_person_id', None) if field == 'name' else None
    if kind == 'child':
        contact_id = getattr(obj, 'supporter_contact_id' if field == 'name' else 'spouse_contact_id', None)
        if contact_id:
            person_id = connection.scalar(select(core.Contact.__table__.c.person_id).where(
                core.Contact.__table__.c.id == contact_id))
    suffixes = dict(name='applicant', spouse='spouse', father='father', inlaws='inlaws',
                    inlaws_maiden_name='maiden', inlaws_family='inlawfam')
    key = (f'family:{obj.id}:{suffixes[field]}' if kind == 'family' and field in suffixes
           else f'askan:{obj.id}' if kind == 'askan' else
           'rid:' + hashlib.sha256(f'{kind}:{obj.id}:{field}'.encode()).hexdigest()[:16])
    people = core.SupporterPerson.__table__
    if person_id is None:
        person_id = connection.scalar(select(people.c.id).where(people.c.identity_key == 'phone:' + key))
        # SQLite can reuse a deleted role row's internal ID. Its former person
        # stays in the directory, but a newly inserted role must not adopt it.
        if person_id is not None and inspect(obj).pending:
            key = 'rid:' + secrets.token_hex(8)
            person_id = None
    if person_id is None:
        person_id = connection.execute(people.insert().values(
            identity_key='phone:' + key, name=name,
            phone=getattr(obj, 'phone', '') or '' if field == 'name' else '',
            email=getattr(obj, 'email', '') or '' if field == 'name' else '')).inserted_primary_key[0]
        issue(connection, person_id, new=True)
    else:
        issue(connection, person_id)
    connection.execute(aliases.insert().values(owner_kind=kind, owner_id=obj.id,
                                              field=field, person_id=person_id))
    names = PersonNames.__table__
    existing = connection.execute(select(names).where(
        names.c.owner_kind == kind, names.c.owner_id == obj.id, names.c.field == field)).mappings().first()
    if existing and not connection.scalar(select(names.c.id).where(
            names.c.owner_kind == 'person', names.c.owner_id == person_id, names.c.field == 'name')):
        connection.execute(names.insert().values(owner_kind='person', owner_id=person_id,
            field='name', english_name=existing['english_name'], yiddish_name=existing['yiddish_name']))
    profiles = profile_model.__table__
    if not connection.scalar(select(profiles.c.id).where(profiles.c.person_id == person_id)):
        connection.execute(profiles.insert().values(person_id=person_id, name=name,
            normalized_phone=key, phone=getattr(obj, 'phone', '') or '' if field == 'name' else '',
            email=getattr(obj, 'email', '') or '' if field == 'name' else ''))


def install(app, profile_model):
    app.jinja_env.globals['person_number'] = number_for
    app.extensions['person_id_role'] = lambda connection, kind, obj, field: ensure_role(
        connection, kind, obj, field, profile_model)

    def selected_person(kind, ident):
        if kind in ('supporter_profile', 'supporter'):
            model = profile_model if kind == 'supporter_profile' else core.Contact
            row = db.session.get(model, ident)
            return row.person_id if row else None
        fields = {'spouse': ('family', 'spouse'), 'child_spouse': ('child', 'spouse_name'),
                  'supporter_child_spouse': ('supporter_child', 'spouse_name')}
        owner_kind, field = fields.get(kind, (kind, 'name'))
        from person_names import resolve_name_owner
        resolved_kind, owner_id, _ = resolve_name_owner(owner_kind, ident, field)
        return owner_id if resolved_kind == 'person' else None

    app.extensions['selected_canonical_person'] = selected_person

    def inserted(mapper, connection, person):
        issue(connection, person.id, new=True)

    def deleted(mapper, connection, person):
        connection.execute(PersonNumber.__table__.update().where(
            PersonNumber.person_id == person.id).values(person_id=None))

    if not getattr(core.SupporterPerson, '_person_numbers_installed', False):
        event.listen(core.SupporterPerson, 'after_insert', inserted)
        event.listen(core.SupporterPerson, 'before_delete', deleted)
        core.SupporterPerson._person_numbers_installed = True

    def immutable(mapper, connection, row):
        raise ValueError('Issued person numbers cannot be edited or deleted.')

    if not getattr(PersonNumber, '_immutable_installed', False):
        event.listen(PersonNumber, 'before_update', immutable)
        event.listen(PersonNumber, 'before_delete', immutable)
        PersonNumber._immutable_installed = True

    def migrate():
        db.create_all()
        connection = db.session.connection()
        for person_id in connection.scalars(select(core.SupporterPerson.id).order_by(core.SupporterPerson.id)):
            issue(connection, person_id)
        models, attributes = app.extensions['person_name_models']
        for kind, model in models.items():
            if kind in ('person', 'profile', 'supporter'):
                continue
            for obj in db.session.scalars(select(model).order_by(model.id)).all():
                for field in attributes[kind]:
                    ensure_role(connection, kind, obj, field, profile_model)
        # Legacy supporters without phones may never have had an import profile.
        represented = select(profile_model.person_id).where(profile_model.person_id.is_not(None))
        for person in db.session.scalars(select(core.SupporterPerson).where(
                core.SupporterPerson.id.not_in(represented))).all():
            key = 'rid:' + hashlib.sha256(f'person:{person.id}'.encode()).hexdigest()[:16]
            connection.execute(profile_model.__table__.insert().values(
                person_id=person.id, normalized_phone=key, name=person.name,
                phone=person.phone or '', email=person.email or ''))
        db.session.commit()

    app.extensions.setdefault('init_db_hooks', []).append(migrate)
    app.extensions['migrate_person_ids'] = migrate
    if app.config['DEMO'] or app.config.get('TESTING'):
        with app.app_context():
            migrate()
