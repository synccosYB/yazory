"""Bilingual names on existing identities; legacy display names are preserved.

No transliteration is invented. Existing names populate their detected script.
Case contact and import profile names share the canonical person's name row.
"""
import re
from markupsafe import Markup
import app_original as core
from flask import abort, current_app, g, has_request_context, request
from sqlalchemy import UniqueConstraint, event, select, tuple_

DB = core.db


class PersonNames(DB.Model):
    __tablename__ = 'person_names'
    __table_args__ = (UniqueConstraint('owner_kind', 'owner_id', 'field', name='uq_person_names_owner'),)
    id = DB.Column(DB.Integer, primary_key=True)
    owner_kind = DB.Column(DB.String(40), nullable=False)
    owner_id = DB.Column(DB.Integer, nullable=False)
    field = DB.Column(DB.String(40), nullable=False, default='name')
    english_name = DB.Column(DB.String(160), nullable=False, default='')
    yiddish_name = DB.Column(DB.String(160), nullable=False, default='')


class PersonNameOwner(DB.Model):
    """Role records refer to the same canonical name, never copy its variants."""
    __tablename__ = 'person_name_owner'
    __table_args__ = (UniqueConstraint('owner_kind', 'owner_id', 'field', name='uq_person_name_alias'),)
    id = DB.Column(DB.Integer, primary_key=True)
    owner_kind = DB.Column(DB.String(40), nullable=False)
    owner_id = DB.Column(DB.Integer, nullable=False)
    field = DB.Column(DB.String(40), nullable=False)
    person_id = DB.Column(DB.Integer, DB.ForeignKey('supporter_person.id'), nullable=False, index=True)


def resolve_name_owner(kind, ident, field='name'):
    if kind != 'person':
        alias = DB.session.scalar(select(PersonNameOwner).where(
            PersonNameOwner.owner_kind == kind, PersonNameOwner.owner_id == ident, PersonNameOwner.field == field))
        if alias:
            return 'person', alias.person_id, 'name'
    return kind, ident, field


def _request_name_cache():
    if (not has_request_context() or not (
            getattr(g, '_batch_person_import', False) or
            getattr(g, '_person_name_preload_enabled', False))):
        return None
    transaction = DB.session().get_transaction()
    if transaction is None:
        DB.session().begin()
        transaction = DB.session().get_transaction()
    cache = getattr(g, '_bilingual_name_cache', None)
    if cache is None or cache[0] is not transaction:
        cache = (transaction, {})
        g._bilingual_name_cache = cache
    return cache[1]


def _invalidate_name_cache(*keys):
    cache = _request_name_cache()
    if cache is None:
        return
    if not keys:
        cache.clear()
    for key in keys:
        row = cache.pop(key, None)
        if row is not None:
            try:
                DB.session.expire(row)
            except Exception:
                # New/detached rows have no persistent state to expire.
                pass


def link_name_owner(kind, ident, field, person):
    alias = DB.session.scalar(select(PersonNameOwner).where(
        PersonNameOwner.owner_kind == kind, PersonNameOwner.owner_id == ident, PersonNameOwner.field == field))
    if alias:
        return
    old = DB.session.scalar(select(PersonNames).where(
        PersonNames.owner_kind == kind, PersonNames.owner_id == ident, PersonNames.field == field))
    target = names_row('person', person.id)
    if target is None:
        en, yi = detected_names(person.name)
        target = save_names('person', person.id, en, yi)
    if old:
        target.english_name = target.english_name or old.english_name
        target.yiddish_name = target.yiddish_name or old.yiddish_name
        DB.session.delete(old)
    DB.session.add(PersonNameOwner(owner_kind=kind, owner_id=ident, field=field, person_id=person.id))
    _invalidate_name_cache((kind, ident, field))


def detected_names(legacy):
    return ('', legacy or '') if re.search(r'[\u0590-\u05ff]', legacy or '') else (legacy or '', '')


def names_row(kind, ident, field='name'):
    cache = _request_name_cache()
    key = kind, ident, field
    if cache is not None and key in cache:
        return cache[key]
    kind, ident, field = resolve_name_owner(kind, ident, field)
    row = DB.session.scalar(select(PersonNames).where(
        PersonNames.owner_kind == kind, PersonNames.owner_id == ident,
        PersonNames.field == field).execution_options(populate_existing=True))
    if cache is not None:
        cache[key] = row
        cache[(kind, ident, field)] = row
    return row


def preload_names(keys):
    """Batch name lookups, including absent names and role aliases."""
    keys = set(keys)
    if not keys:
        return
    if has_request_context():
        g._person_name_preload_enabled = True
    cache = _request_name_cache()
    if cache is None:
        cache = {}
    cached = cache
    missing = keys - cached.keys()
    if not missing:
        return
    alias_keys = [key for key in missing if key[0] != 'person']
    aliases = DB.session.scalars(select(PersonNameOwner).where(tuple_(
        PersonNameOwner.owner_kind, PersonNameOwner.owner_id,
        PersonNameOwner.field).in_(alias_keys))).all() if alias_keys else []
    resolved = {key: key for key in missing}
    for alias in aliases:
        resolved[(alias.owner_kind, alias.owner_id, alias.field)] = ('person', alias.person_id, 'name')
    rows = DB.session.scalars(select(PersonNames).where(tuple_(
        PersonNames.owner_kind, PersonNames.owner_id, PersonNames.field
    ).in_(set(resolved.values())))).all()
    by_key = {(row.owner_kind, row.owner_id, row.field): row for row in rows}
    cache.update({key: by_key.get(target) for key, target in resolved.items()})
    if current_app.extensions.get('person_id_role'):
        from person_ids import preload_numbers
        preload_numbers(resolved)


def save_names(kind, ident, english, yiddish, field='name', fill_only=False,
               legacy='', known_missing=False):
    if max(len(english or ''), len(yiddish or '')) > 160:
        abort(400)
    kind, ident, field = resolve_name_owner(kind, ident, field)
    cache = _request_name_cache()
    key = kind, ident, field
    row = cache.get(key) if cache is not None and key in cache else (
        None if known_missing else names_row(kind, ident, field))
    if row is None:
        old_en, old_yi = detected_names(legacy)
        row = PersonNames(owner_kind=kind, owner_id=ident, field=field,
                          english_name=old_en, yiddish_name=old_yi)
        DB.session.add(row)
    if cache is not None:
        cache[key] = row
    if not fill_only or not row.english_name:
        row.english_name = english or ''
    if not fill_only or not row.yiddish_name:
        row.yiddish_name = yiddish or ''
    return row


def install(app, extras):
    models = dict(family=core.Family, child=core.Child, supporter=core.Contact,
                  person=core.SupporterPerson, askan=core.Askan, staff=core.StaffUser,
                  supporter_child=core.ContactChild, **extras)
    attributes = {kind: ['name'] for kind in models}
    attributes['family'] += ['spouse', 'father', 'inlaws', 'inlaws_maiden_name', 'inlaws_family', 'rabbi']
    attributes['child'] += ['spouse_name']
    attributes['supporter_child'] += ['spouse_name']
    app.extensions['person_name_models'] = models, attributes

    def owner(kind, obj, field='name'):
        if kind in ('supporter', 'profile') and obj.person_id:
            return 'person', obj.person_id, 'name'
        return kind, obj.id, field

    def values(kind, obj=None, field='name', legacy=''):
        if obj is not None and getattr(obj, 'id', None):
            key = owner(kind, obj, field)
            row = names_row(*key)
            if row:
                return dict(english_name=row.english_name, yiddish_name=row.yiddish_name)
            legacy = getattr(obj, field, '') or ''
        en, yi = detected_names(legacy)
        return dict(english_name=en, yiddish_name=yi)

    def input_fields(kind, obj=None, field='name', legacy=''):
        vals = values(kind, obj, field, legacy)
        label = {'name': {'family': 'Applicant', 'askan': 'Askan', 'child': 'Child', 'staff': 'Staff member', 'partner_contact': 'Contact', 'profile': 'Name', 'supporter': 'Name'}.get(kind, 'Name'), 'spouse': 'Spouse', 'spouse_name': 'Spouse', 'father': 'Father', 'inlaws': 'Father-in-law', 'rabbi': 'Rabbi'}.get(field, field.replace('_', ' ').capitalize())
        # A field fragment must not rerun all page context processors. They
        # query navigation badges, sponsors and settings on every invocation.
        return Markup(current_app.jinja_env.get_template(
            '_bilingual_name_fields.html').render(
                name_field=field, name_values=vals, name_label=label, request=request,
                public_number=current_app.jinja_env.globals.get('person_number', lambda *a: '')(kind, obj, field)))

    app.jinja_env.globals['bilingual_name_fields'] = input_fields
    app.jinja_env.globals['person_name_values'] = values

    @app.before_request
    def prepare_bilingual_submission():
        if request.method != 'POST':
            return
        form = request.form.copy()
        changed = False
        for key in list(form):
            if not key.endswith('_english'):
                continue
            field = key[:-8]
            english = form.get(key, '').strip()
            yiddish = form.get(field + '_yiddish', '').strip()
            if max(len(english), len(yiddish)) > 160:
                abort(400)
            legacy = form.get(field, '').strip()
            form[field] = legacy if legacy and legacy in (english, yiddish) else english or yiddish
            changed = True
        if changed:
            request.form = form

    def record_names(mapper, connection, obj):
        # Directory imports write canonical names explicitly in batches. The
        # normal mapper path performs a raw SELECT for each inserted profile,
        # canonical person and case contact, defeating that batching.
        if (has_request_context() and request.method == 'POST' and
                getattr(g, '_batch_person_import', False)):
            return
        # Mapper hooks run in the original transaction, including manual creates.
        kind = next((k for k, model in models.items() if isinstance(obj, model)), None)
        if kind is None:
            return
        for field in attributes[kind]:
            if not hasattr(obj, field):
                continue
            legacy = getattr(obj, field, '') or ''
            if not legacy:
                role_link = current_app.extensions.get('person_id_role')
                if role_link:
                    role_link(connection, kind, obj, field)
                continue
            requested_key = owner(kind, obj, field)
            key = requested_key
            if key[0] != 'person':
                aliases = PersonNameOwner.__table__
                alias = connection.execute(select(aliases.c.person_id).where(aliases.c.owner_kind == key[0], aliases.c.owner_id == key[1], aliases.c.field == key[2])).scalar()
                if alias:
                    key = ('person', alias, 'name')
            table = PersonNames.__table__
            condition = (table.c.owner_kind == key[0]) & (table.c.owner_id == key[1]) & (table.c.field == key[2])
            existing = connection.execute(select(table).where(condition)).mappings().first()
            en, yi = detected_names(legacy)
            submitted = False
            if has_request_context() and request.method == 'POST':
                # Match the source field, avoiding unrelated objects changed by sync.
                candidates = [field]
                if field == 'name':
                    candidates += ['askan_name', 'rabbi_name', 'helper_name', 'gabbai_name', 'applicant_name']
                form_field = next((f for f in candidates if f + '_english' in request.form and request.form.get(f, '').strip() == legacy), None)
                submitted = form_field is not None
                if submitted:
                    en = request.form.get(form_field + '_english', '').strip()
                    yi = request.form.get(form_field + '_yiddish', '').strip()
                    if max(len(en), len(yi)) > 160:
                        abort(400)
            if existing:
                if submitted:
                    connection.execute(table.update().where(condition).values(english_name=en, yiddish_name=yi))
                    _invalidate_name_cache(requested_key, key)
            else:
                connection.execute(table.insert().values(owner_kind=key[0], owner_id=key[1], field=key[2], english_name=en, yiddish_name=yi))
                _invalidate_name_cache(requested_key, key)

            role_link = current_app.extensions.get('person_id_role')
            if role_link:
                role_link(connection, kind, obj, field)

    # Register one handler per model, dispatching to the current app's closure.
    app.extensions['record_person_names'] = record_names
    def dispatch(mapper, connection, obj):
        handler = current_app.extensions.get('record_person_names')
        if handler:
            handler(mapper, connection, obj)
    def delete_names(mapper, connection, obj):
        kind = next((k for k, model in models.items() if isinstance(obj, model)), None)
        if kind is None:
            return
        connection.execute(PersonNames.__table__.delete().where(
            PersonNames.owner_kind == kind, PersonNames.owner_id == obj.id))
        _invalidate_name_cache()
        alias_table = PersonNameOwner.__table__
        condition = (alias_table.c.owner_kind == kind) & (alias_table.c.owner_id == obj.id)
        if kind == 'person':
            condition = condition | (alias_table.c.person_id == obj.id)
        connection.execute(alias_table.delete().where(condition))
    app.extensions['delete_person_names'] = delete_names
    def delete_dispatch(mapper, connection, obj):
        handler = current_app.extensions.get('delete_person_names')
        if handler:
            handler(mapper, connection, obj)
    for model in models.values():
        if not getattr(model, '_bilingual_names_installed', False):
            event.listen(model, 'after_insert', dispatch)
            event.listen(model, 'after_update', dispatch)
            event.listen(model, 'before_delete', delete_dispatch)
            model._bilingual_names_installed = True

    def migrate():
        DB.create_all()
        for child in DB.session.scalars(select(core.Child)).all():
            for field, contact_id in (('name', child.supporter_contact_id), ('spouse_name', child.spouse_contact_id)):
                contact = DB.session.get(core.Contact, contact_id) if contact_id else None
                if contact and contact.person_id:
                    link_name_owner('child', child.id, field, DB.session.get(core.SupporterPerson, contact.person_id))
        # Backfill every existing individual without overwriting either language.
        for kind, model in models.items():
            for obj in DB.session.scalars(select(model)).all():
                for field in attributes[kind]:
                    if not hasattr(obj, field):
                        continue
                    key = owner(kind, obj, field)
                    if names_row(*key) is None:
                        en, yi = detected_names(getattr(obj, field, '') or '')
                        save_names(key[0], key[1], en, yi, key[2])
        DB.session.commit()
    app.extensions.setdefault('init_db_hooks', []).append(migrate)
    if app.config['DEMO'] or app.config.get('TESTING'):
        with app.app_context():
            migrate()
    app.extensions['person_names'] = dict(values=values, save=save_names)
