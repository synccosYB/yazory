"""Transactional, administrator-reviewed canonical person merges."""
import json
import hashlib
from datetime import datetime, timezone
from flask import abort, flash, g, has_request_context, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import app_original as core
from person_names import PersonNames, names_row, save_names
from person_addresses import PersonAddressDetails
from book_directory import PersonBookRecord

db = core.db


class PersonMerge(db.Model):
    __tablename__ = 'person_merge'
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    source_profile_id = db.Column(db.Integer, nullable=True, index=True)
    target_profile_id = db.Column(db.Integer, nullable=True)
    snapshot = db.Column(db.JSON, nullable=False)
    reviewed_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PersonIdentityAlias(db.Model):
    __tablename__ = 'person_identity_alias'
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    value = db.Column(db.String(254), nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint('person_id', 'kind', 'value', name='uq_person_identity_alias'),)


def resolve_identity_alias(identity_key):
    return db.session.scalar(select(core.SupporterPerson).join(PersonIdentityAlias).where(
        PersonIdentityAlias.kind == 'identity_key', PersonIdentityAlias.value == identity_key))


def snapshot(person):
    result = {}
    for table in db.metadata.sorted_tables:
        if table.name == 'person_merge':
            continue
        conditions = [column == person.id for column in table.columns
                      if any(fk.target_fullname == 'supporter_person.id' for fk in column.foreign_keys)]
        if table.name == 'person_number':
            conditions = [table.c.person_id == person.id]
        if 'supporter_key' in table.c:
            conditions.append(table.c.supporter_key == person.identity_key)
        if table.name == 'supporter_person':
            conditions = [table.c.id == person.id]
        if table.name == 'person_names':
            conditions = [(table.c.owner_kind == 'person') & (table.c.owner_id == person.id)]
        if table.name == 'person_address_details':
            conditions = [(table.c.person_kind == 'person') & (table.c.person_id == person.id)]
        if conditions:
            result[table.name] = [dict(row) for row in db.session.execute(
                select(table).where(db.or_(*conditions))).mappings()]
    return json.loads(json.dumps(result, default=str))


def merge_people(app, profile_model, target_id, source_id, actor=None):
    if source_id == target_id:
        raise ValueError('Choose two different people.')
    # Lock in stable order so concurrent reviews cannot merge a person twice.
    people = db.session.scalars(select(core.SupporterPerson).where(
        core.SupporterPerson.id.in_([source_id, target_id])).order_by(
        core.SupporterPerson.id).with_for_update()).all()
    by_id = {p.id: p for p in people}
    if len(by_id) != 2:
        raise ValueError('This pair has already changed. Reload the review.')
    target, source = by_id[target_id], by_id[source_id]
    books = db.session.scalars(select(PersonBookRecord).where(
        PersonBookRecord.person_id.in_([source_id, target_id]))).all()
    sources = {}
    for book in books:
        if book.source in sources and sources[book.source] != book.book_id:
            raise ValueError('Different IDs in the same source book cannot be merged.')
        sources[book.source] = book.book_id
    from book_directory import PersonFamilyConnection
    families = db.session.scalars(select(PersonFamilyConnection).where(
        PersonFamilyConnection.person_id.in_([source_id, target_id]))).all()
    if any(getattr(f, field) in (source_id, target_id) for f in families
           for field in ('father_person_id', 'father_inlaw_person_id')):
        raise ValueError('These people have a family relationship. Correct it before merging.')
    before = {'source': snapshot(source), 'target': snapshot(target)}
    profiles = {p.person_id: p for p in db.session.scalars(select(profile_model).where(
        profile_model.person_id.in_([source_id, target_id])))}
    source_profile, target_profile = profiles.get(source_id), profiles.get(target_id)
    if not target_profile:
        raise ValueError('The surviving person needs a directory profile.')
    # Keep populated survivor details. Archive every conflicting value for review.
    for column in core.SupporterPerson.__table__.columns:
        if column.name not in ('id', 'identity_key', 'created_at'):
            old = getattr(source, column.name)
            if not getattr(target, column.name) and old:
                setattr(target, column.name, old)
    if source.notes and source.notes != target.notes:
        target.notes = '\n'.join(filter(None, [target.notes, source.notes]))
    db.session.flush()
    # These optional owner tables have unique owner keys. Fill missing fields;
    # retain both original records in the immutable merge snapshot.
    for model, kind_field, id_field, kind in (
            (PersonNames, 'owner_kind', 'owner_id', 'person'),
            (PersonAddressDetails, 'person_kind', 'person_id', 'person')):
        src_rows = db.session.scalars(select(model).where(
            getattr(model, kind_field) == kind, getattr(model, id_field) == source_id)).all()
        for src in src_rows:
            criteria = [getattr(model, kind_field) == kind, getattr(model, id_field) == target_id]
            if model is PersonNames:
                criteria.append(model.field == src.field)
            dst = db.session.scalar(select(model).where(*criteria))
            if dst:
                for col in model.__table__.columns:
                    if col.name not in ('id', kind_field, id_field, 'field'):
                        value = getattr(src, col.name)
                        if isinstance(value, dict):
                            setattr(dst, col.name, {**value, **(getattr(dst, col.name) or {})})
                        elif not getattr(dst, col.name):
                            setattr(dst, col.name, value)
                db.session.delete(src)
            else:
                setattr(src, id_field, target_id)
    db.session.flush()
    from book_directory import PersonFamilyConnection
    from unified_people import PersonMatchDecision
    import app as extended
    # Resolve unique person-owned rows before the generic FK transfer.
    src_family = db.session.get(PersonFamilyConnection, source_id)
    dst_family = db.session.get(PersonFamilyConnection, target_id)
    if src_family and dst_family:
        for field in ('father', 'father_inlaw'):
            src_parent = getattr(src_family, field + '_person_id')
            dst_parent = getattr(dst_family, field + '_person_id')
            if src_parent and dst_parent and src_parent != dst_parent:
                raise ValueError('Family connections conflict. Correct them before merging.')
            for suffix in ('_name', '_person_id', '_manually_set'):
                attr = field + suffix
                if not getattr(dst_family, attr):
                    setattr(dst_family, attr, getattr(src_family, attr))
        db.session.delete(src_family)
    for model in (extended.PersonRelationship, PersonMatchDecision):
        rows = db.session.scalars(select(model).where(
            (model.person_one_id == source_id) | (model.person_two_id == source_id))).all()
        for row in rows:
            a, b = sorted(target_id if value == source_id else value
                          for value in (row.person_one_id, row.person_two_id))
            if a == b:
                if model is extended.PersonRelationship:
                    raise ValueError('These people have a family relationship. Correct it before merging.')
                db.session.delete(row)
                continue
            criteria = [model.person_one_id == a, model.person_two_id == b, model.id != row.id]
            if model is PersonMatchDecision:
                criteria.append(model.kind == row.kind)
            existing = db.session.scalar(select(model).where(*criteria))
            if existing:
                if model is extended.PersonRelationship:
                    if existing.relationship != row.relationship:
                        raise ValueError('Family relationships conflict. Correct them before merging.')
                    existing.notes = '\n'.join(filter(None, [existing.notes, row.notes]))[:500]
                elif existing.decision == 'review_later':
                    existing.decision = row.decision
                db.session.delete(row)
            else:
                row.person_one_id, row.person_two_id = a, b
    db.session.flush()
    source_aliases = db.session.scalars(select(PersonIdentityAlias).where(
        PersonIdentityAlias.person_id == source_id)).all()
    values = {(a.kind, a.value) for a in source_aliases}
    values.add(('identity_key', source.identity_key))
    from unified_people import _phone
    for raw in (source.phone, source.home_phone, source.cell_phone):
        key = _phone(raw)
        if 7 <= len(key) <= 15:
            values.add(('phone', key))
    if source.email:
        values.add(('email', source.email.strip().casefold()))
    existing_aliases = {(a.kind, a.value) for a in db.session.scalars(select(PersonIdentityAlias).where(
        PersonIdentityAlias.person_id == target_id))}
    for alias in source_aliases:
        db.session.delete(alias)
    db.session.flush()
    for kind, value in values - existing_aliases:
        db.session.add(PersonIdentityAlias(person_id=target_id, kind=kind, value=value))
    db.session.flush()
    connection = db.session.connection()
    # Move every declared canonical FK, including role aliases, contacts,
    # relationship endpoints, book references and future extension tables.
    # A unique collision aborts the complete transaction; never discard history.
    for table in db.metadata.sorted_tables:
        if table.name in ('supporter_profile', 'person_number'):
            continue
        for column in table.columns:
            if any(fk.target_fullname == 'supporter_person.id' for fk in column.foreign_keys):
                connection.execute(table.update().where(column == source_id).values({column.name: target_id}))
    if source_profile:
        # Polymorphic affiliation references do not declare foreign keys.
        affiliation = core.PersonAffiliation.__table__
        connection.execute(affiliation.update().where(
            affiliation.c.person_type == 'supporter_profile',
            affiliation.c.person_id == source_profile.id).values(person_id=target_profile.id))
        for table in db.metadata.sorted_tables:
            for column in table.columns:
                if any(fk.target_fullname == 'supporter_profile.id' for fk in column.foreign_keys):
                    connection.execute(table.update().where(column == source_profile.id).values(
                        {column.name: target_profile.id}))
        db.session.delete(source_profile)
    db.session.flush()
    db.session.add(PersonMerge(source_id=source_id, target_id=target_id,
        source_profile_id=source_profile.id if source_profile else None,
        target_profile_id=target_profile.id, snapshot=before, reviewed_by=actor))
    # Rewrite identity-based billing lookups while preserving case and receipt IDs.
    for table in db.metadata.sorted_tables:
        if 'supporter_key' in table.c:
            connection.execute(table.update().where(table.c.supporter_key == source.identity_key).values(
                supporter_key=target.identity_key))
    db.session.delete(source)
    db.session.flush()
    db.session.expire_all()
    contacts = db.session.scalars(select(core.Contact).where(core.Contact.person_id == target_id)).all()
    notes = {c.id: c.notes for c in contacts}
    app.extensions['supporter_identity']['sync'](db.session.get(core.SupporterPerson, target_id))
    for contact in contacts:
        contact.notes = notes[contact.id]
    db.session.commit()


def install(app, profile_model, access):
    from sqlalchemy import event, func
    # PostgreSQL sequences retain deleted IDs; reserve merged IDs on SQLite too.
    def reserve_ids(mapper, connection, person):
        if connection.dialect.name == 'sqlite' and person.id is None:
            # SQLite has no independent sequence to preserve IDs of people that
            # were merged and deleted. Read the two high-water marks once per
            # batch import instead of twice for every newly inserted person.
            batch = has_request_context() and getattr(g, '_batch_person_import', False)
            cache_key = 'person_merge_batch_highest' if batch else None
            highest = connection.info.get(cache_key) if cache_key else None
            if highest is None:
                highest = max(connection.scalar(select(func.max(core.SupporterPerson.id))) or 0,
                              connection.scalar(select(func.max(PersonMerge.source_id))) or 0,
                              connection.info.get('person_merge_last_id', 0))
            person.id = highest + 1
            connection.info['person_merge_last_id'] = person.id
            if cache_key:
                connection.info[cache_key] = person.id
    if not getattr(core.SupporterPerson, '_merge_ids_reserved', False):
        event.listen(core.SupporterPerson, 'before_insert', reserve_ids)
        core.SupporterPerson._merge_ids_reserved = True

    def admin():
        user = access()
        if user is not None and user.role != 'organization_admin':
            abort(403)
        return user

    @app.route('/people/duplicates/<int:one_id>/<int:two_id>', methods=['GET', 'POST'])
    def review_person_merge(one_id, two_id):
        user = admin()
        if one_id == two_id:
            abort(400)
        one = db.get_or_404(core.SupporterPerson, one_id)
        two = db.get_or_404(core.SupporterPerson, two_id)
        error = None
        snapshots = {one.id: snapshot(one), two.id: snapshot(two)}
        version = hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest()
        if request.method == 'POST':
            from translations import translate
            from unified_people import PersonMatchDecision, _candidates, _pair
            kept = set(request.form.getlist('keep_id', type=int))
            if request.form.get('version') != version:
                abort(409, 'The records changed. Reload the merge preview.')
            if not kept or not kept.issubset({one_id, two_id}) or request.form.get('confirm') != 'yes':
                abort(400)

            # Name corrections made during duplicate review update the same
            # canonical bilingual name record used everywhere else. Do not
            # create a review-only copy of the name.
            for person in (one, two):
                english = request.form.get(f'name_english_{person.id}', '').strip()[:160]
                yiddish = request.form.get(f'name_yiddish_{person.id}', '').strip()[:160]
                if not english and not yiddish:
                    abort(400, 'Enter at least one name for each person.')
                current = names_row('person', person.id)
                current_english = current.english_name if current else ''
                current_yiddish = current.yiddish_name if current else ''
                if (english, yiddish) != (current_english, current_yiddish):
                    person.name = english or yiddish
                    save_names('person', person.id, english, yiddish, legacy=person.name)
                    profile = db.session.scalar(select(profile_model).where(
                        profile_model.person_id == person.id))
                    if profile is not None:
                        profile.name = person.name
                    sync = app.extensions.get('supporter_identity', {}).get('sync')
                    if sync:
                        sync(person)

            if kept == {one_id, two_id}:
                # Human review confirmed that the matching signals belong to two
                # separate people. Preserve both canonical IDs and suppress this
                # pair from future duplicate suggestions; field verification is
                # deliberately untouched.
                a, b = _pair(one_id, two_id)
                decision = db.session.scalar(select(PersonMatchDecision).where(
                    PersonMatchDecision.person_one_id == a,
                    PersonMatchDecision.person_two_id == b,
                    PersonMatchDecision.kind == 'duplicate'))
                if decision is None:
                    decision = PersonMatchDecision(
                        person_one_id=a, person_two_id=b, kind='duplicate',
                        decision='not_duplicate', reviewed_by=user.id if user else None)
                    db.session.add(decision)
                else:
                    decision.decision = 'not_duplicate'
                    decision.reviewed_by = user.id if user else None
                    decision.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()
                flash(translate('Both people kept as separate people.'))
            else:
                target = next(iter(kept))
                try:
                    merge_people(app, profile_model, target,
                                 two_id if target == one_id else one_id,
                                 user.id if user else None)
                except (ValueError, IntegrityError) as exc:
                    db.session.rollback()
                    error = str(exc) if isinstance(exc, ValueError) else 'Linked records conflict. Merge was cancelled; all records remain intact.'
                else:
                    flash(translate('People merged.'))

            if error is None:
                # Keep duplicate review as a queue after either decision.
                people = db.session.scalars(select(core.SupporterPerson).order_by(
                    core.SupporterPerson.id.desc())).all()
                decisions = db.session.scalars(select(PersonMatchDecision)).all()
                later = {_pair(row.person_one_id, row.person_two_id)
                         for row in decisions
                         if row.kind == 'duplicate' and row.decision == 'review_later'}
                ready = [row for row in _candidates(people, decisions, 'duplicate')
                         if _pair(row[0].id, row[1].id) not in later]
                if ready:
                    next_one, next_two, _ = ready[0]
                    return redirect(url_for('review_person_merge',
                                            one_id=next_one.id, two_id=next_two.id))
                return redirect(url_for('people_matching',
                                        tab='duplicates', queue='ready'))
        return render_template('person_merge.html', title='Review merge',
                               one=one, two=two, error=error,
                               snapshots=snapshots, version=version), 409 if error else 200

    @app.get('/people/merge-history')
    def person_merge_history():
        admin()
        page = max(1, request.args.get('page', 1, type=int))
        rows = db.session.scalars(select(PersonMerge).order_by(
            PersonMerge.id.desc()).limit(20).offset((page-1)*20)).all()
        return render_template('person_merge_history.html', title='Merge history', rows=rows, page=page)

    @app.before_request
    def merged_links():
        if core.session.get('supporter_key'):
            survivor = resolve_identity_alias(core.session['supporter_key'])
            if survivor:
                core.session['supporter_key'] = survivor.identity_key

        if request.endpoint not in ('person_hub', 'edit_person_hub', 'edit_supporter_profile'):
            return
        args = request.view_args or {}
        field = 'source_profile_id' if request.endpoint == 'edit_supporter_profile' else 'source_id'
        ident = args.get('profile_id' if field == 'source_profile_id' else 'person_id')
        row = db.session.scalar(select(PersonMerge).where(getattr(PersonMerge, field) == ident))
        if row:
            access()
            target = row.target_id
            seen = set()
            while target not in seen:
                seen.add(target)
                next_row = db.session.scalar(select(PersonMerge).where(PersonMerge.source_id == target))
                if not next_row:
                    break
                target = next_row.target_id
            return redirect(url_for('person_hub', person_id=target), code=303)

    def migrate():
        db.create_all()
    app.extensions.setdefault('init_db_hooks', []).append(migrate)
    if app.config['DEMO'] or app.config.get('TESTING'):
        with app.app_context():
            migrate()

