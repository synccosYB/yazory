"""Unified canonical person hub and human-reviewed family matching."""
import re
from collections import defaultdict
from datetime import datetime, timezone

import app_original as core
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import UniqueConstraint, select
from person_names import PersonNameOwner, names_row, preload_names, resolve_name_owner, save_names

db = core.db

FAMILY_RELATIONSHIPS = (
    'Parent', 'Child', 'Spouse', 'Brother', 'Sister',
    'Father-in-law', 'Mother-in-law', 'Son-in-law', 'Daughter-in-law',
    'Brother-in-law', 'Sister-in-law', 'Uncle', 'Aunt', 'Nephew', 'Niece',
    'First cousin', 'Second cousin', 'Mechutan', 'Other family',
)
REVERSE = {
    'Parent': 'Child', 'Child': 'Parent', 'Spouse': 'Spouse',
    'Brother': 'Sibling', 'Sister': 'Sibling', 'Uncle': 'Niece/nephew',
    'Aunt': 'Niece/nephew', 'Nephew': 'Aunt/uncle', 'Niece': 'Aunt/uncle',
    'Father-in-law': 'Child-in-law', 'Mother-in-law': 'Child-in-law',
    'Son-in-law': 'Parent-in-law', 'Daughter-in-law': 'Parent-in-law',
    'Brother-in-law': 'Sibling-in-law', 'Sister-in-law': 'Sibling-in-law',
    'First cousin': 'First cousin', 'Second cousin': 'Second cousin',
    'Mechutan': 'Mechutan', 'Other family': 'Other family',
}


class PersonMatchDecision(db.Model):
    """A human decision about a proposed duplicate or family connection."""
    __tablename__ = 'person_match_decision'
    __table_args__ = (
        UniqueConstraint('person_one_id', 'person_two_id', 'kind',
                         name='uq_person_match_decision_pair_kind'),
    )
    id = db.Column(db.Integer, primary_key=True)
    person_one_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'),
                              nullable=False, index=True)
    person_two_id = db.Column(db.Integer, db.ForeignKey('supporter_person.id'),
                              nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    decision = db.Column(db.String(30), nullable=False, index=True)
    evidence = db.Column(db.Text, nullable=False, default='')
    reviewed_by = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=False,
                            default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


def _pair(a, b):
    return (a, b) if a < b else (b, a)


def _phone(value):
    digits = re.sub(r'\D', '', value or '')
    return digits[1:] if len(digits) == 11 and digits.startswith('1') else digits


def _name(value):
    return ' '.join((value or '').casefold().split())


def _person_names(person):
    row = names_row('person', person.id)
    return {
        _name(person.name),
        _name(row.english_name if row else ''),
        _name(row.yiddish_name if row else ''),
    } - {''}


def _evidence(people):
    """Generate review candidates from concrete shared evidence, never surname alone."""
    by_phone, by_email, by_address, by_name = (defaultdict(list) for _ in range(4))
    for person in people:
        for raw in (person.phone, person.home_phone, person.cell_phone):
            key = _phone(raw)
            if key:
                by_phone[key].append(person.id)
        if person.email:
            by_email[person.email.strip().casefold()].append(person.id)
        address = '|'.join(_name(getattr(person, field, '')) for field in
                           ('home_address', 'city', 'state', 'zip_code'))
        if address.strip('|') and _name(person.home_address):
            by_address[address].append(person.id)
        for key in _person_names(person):
            by_name[key].append(person.id)

    evidence = defaultdict(set)
    for label, buckets in (('same phone', by_phone), ('same email', by_email),
                           ('same home address', by_address), ('same full name', by_name)):
        for ids in buckets.values():
            unique = sorted(set(ids))
            if len(unique) > 20:  # common data is not useful matching evidence
                continue
            for i, one in enumerate(unique):
                for two in unique[i + 1:]:
                    evidence[_pair(one, two)].add(label)
    return evidence


def _candidates(people, decisions, kind):
    by_id = {p.id: p for p in people}
    evidence = _evidence(people)
    decided = {_pair(row.person_one_id, row.person_two_id)
               for row in decisions if row.kind == kind and row.decision != 'review_later'}
    rows = []
    for pair, reasons in evidence.items():
        if pair in decided:
            continue
        one, two = by_id[pair[0]], by_id[pair[1]]
        if kind == 'duplicate':
            # Name alone never proposes a duplicate. Shared household address alone
            # can mean relatives. Require identity evidence or two independent signals.
            strong = {'same phone', 'same email'} & reasons
            if not strong and len(reasons) < 2:
                continue
        else:
            # A family suggestion needs household/contact evidence plus distinct people.
            # A surname or full-name resemblance by itself is deliberately ignored.
            if reasons == {'same full name'}:
                continue
            if {'same phone', 'same email'} & reasons and 'same full name' in reasons:
                continue  # more likely a duplicate; review there first
        rows.append((one, two, sorted(reasons)))
    rows.sort(key=lambda row: (-len(row[2]), row[0].name.casefold(), row[1].name.casefold()))
    return rows[:200]


def install(app, profile_model, relationship_model, access):
    PersonRelationship = relationship_model
    def current_user_id():
        return core.session.get('user_id')

    def canonical_profile(person_id):
        return db.session.scalar(select(profile_model).where(profile_model.person_id == person_id))

    def person_or_404(person_id):
        access()
        return db.get_or_404(core.SupporterPerson, person_id)

    @app.get('/people/<int:person_id>')
    def person_hub(person_id):
        person = person_or_404(person_id)
        profile = canonical_profile(person.id)
        contacts = db.session.scalars(select(core.Contact).where(
            core.Contact.person_id == person.id).order_by(core.Contact.family_id)).all()
        aliases = db.session.scalars(select(PersonNameOwner).where(
            PersonNameOwner.person_id == person.id).order_by(
            PersonNameOwner.owner_kind, PersonNameOwner.owner_id)).all()
        links = db.session.scalars(select(PersonRelationship).where(
            (PersonRelationship.person_one_id == person.id) |
            (PersonRelationship.person_two_id == person.id)).order_by(PersonRelationship.id)).all()
        related_ids = {link.person_two_id if link.person_one_id == person.id else link.person_one_id
                       for link in links}
        relatives = {p.id: p for p in db.session.scalars(select(core.SupporterPerson).where(
            core.SupporterPerson.id.in_(related_ids))).all()} if related_ids else {}
        return render_template('person_hub.html', title=person.name, person=person,
                               profile=profile, contacts=contacts, aliases=aliases,
                               links=links, relatives=relatives)

    @app.get('/people/from/<kind>/<int:role_id>')
    def person_role_hub(kind, role_id):
        access()
        owner_kind, owner_id, _ = resolve_name_owner(kind, role_id, 'name')
        if owner_kind != 'person':
            abort(404, 'This role has not been linked to a canonical person yet.')
        return redirect(url_for('person_hub', person_id=owner_id))

    @app.route('/people/<int:person_id>/edit', methods=['GET', 'POST'])
    def edit_person_hub(person_id):
        person = person_or_404(person_id)
        profile = canonical_profile(person.id)
        if request.method == 'POST':
            english = request.form.get('name_english', '').strip()[:160]
            yiddish = request.form.get('name_yiddish', '').strip()[:160]
            if not english and not yiddish:
                abort(400, 'Enter at least one name.')
            person.name = english or yiddish
            save_names('person', person.id, english, yiddish, legacy=person.name)
            for field, limit in (('phone', 80), ('home_phone', 80), ('cell_phone', 80),
                                 ('email', 254), ('home_address', 240), ('city', 120),
                                 ('state', 80), ('zip_code', 20), ('workplace', 160),
                                 ('work_phone', 80)):
                if hasattr(person, field):
                    setattr(person, field, request.form.get(field, '').strip()[:limit])
            if profile is not None:
                profile.name = person.name
                profile.phone = person.phone
                profile.email = person.email
                profile.home_phone = person.home_phone
                profile.cell_phone = person.cell_phone
                profile.home_address = person.home_address
                profile.city = person.city
                profile.state = person.state
                profile.zip_code = person.zip_code
                profile.workplace = person.workplace
                profile.work_phone = person.work_phone
            sync = app.extensions.get('supporter_identity', {}).get('sync')
            if sync:
                sync(person)
            db.session.commit()
            flash('Person updated.')
            return redirect(url_for('person_hub', person_id=person.id))
        row = names_row('person', person.id)
        return render_template('person_edit.html', title='Edit person', person=person,
                               english_name=row.english_name if row else person.name,
                               yiddish_name=row.yiddish_name if row else '')

    @app.get('/people/matching')
    def people_matching():
        access()
        people = db.session.scalars(select(core.SupporterPerson).order_by(
            core.SupporterPerson.name, core.SupporterPerson.id)).all()
        preload_names({('person', person.id, 'name') for person in people})
        decisions = db.session.scalars(select(PersonMatchDecision)).all()
        tab = request.args.get('tab', 'connections')
        if tab not in ('connections', 'duplicates'):
            abort(400)
        kind = 'duplicate' if tab == 'duplicates' else 'connection'
        return render_template('people_matching.html', title='People matching', tab=tab,
                               candidates=_candidates(people, decisions, kind),
                               relationship_types=FAMILY_RELATIONSHIPS)

    @app.post('/people/matching/<kind>/<int:one_id>/<int:two_id>')
    def decide_people_match(kind, one_id, two_id):
        access()
        if kind not in ('duplicate', 'connection') or one_id == two_id:
            abort(400)
        one = db.get_or_404(core.SupporterPerson, one_id)
        two = db.get_or_404(core.SupporterPerson, two_id)
        a, b = _pair(one.id, two.id)
        decision = request.form.get('decision', '')
        allowed = {'not_duplicate', 'review_later'} if kind == 'duplicate' else {
            'not_related', 'review_later', 'confirm'}
        if decision not in allowed:
            abort(400)
        row = db.session.scalar(select(PersonMatchDecision).where(
            PersonMatchDecision.person_one_id == a,
            PersonMatchDecision.person_two_id == b,
            PersonMatchDecision.kind == kind))
        if row is None:
            row = PersonMatchDecision(person_one_id=a, person_two_id=b, kind=kind,
                                      decision=decision, reviewed_by=current_user_id())
            db.session.add(row)
        else:
            row.decision = decision
            row.reviewed_by = current_user_id()
            row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if kind == 'connection' and decision == 'confirm':
            relationship = request.form.get('relationship', '')
            if relationship not in FAMILY_RELATIONSHIPS:
                abort(400, 'Choose the confirmed family relationship.')
            existing = db.session.scalar(select(PersonRelationship).where(
                PersonRelationship.person_one_id == a,
                PersonRelationship.person_two_id == b))
            if existing is None:
                db.session.add(PersonRelationship(
                    person_one_id=a, person_two_id=b, relationship=relationship,
                    notes=request.form.get('notes', '')[:500]))
        db.session.commit()
        flash('Review saved.')
        return redirect(url_for('people_matching',
                                tab='duplicates' if kind == 'duplicate' else 'connections'))

    @app.post('/people/<int:person_id>/family')
    def add_person_family_link(person_id):
        person = person_or_404(person_id)
        relative_id = request.form.get('relative_id', type=int)
        relative = db.get_or_404(core.SupporterPerson, relative_id)
        if relative.id == person.id:
            abort(400)
        relationship = request.form.get('relationship', '')
        if relationship not in FAMILY_RELATIONSHIPS:
            abort(400)
        a, b = _pair(person.id, relative.id)
        exists = db.session.scalar(select(PersonRelationship).where(
            PersonRelationship.person_one_id == a,
            PersonRelationship.person_two_id == b))
        if exists is None:
            db.session.add(PersonRelationship(
                person_one_id=a, person_two_id=b, relationship=relationship,
                    notes=request.form.get('notes', '')[:500]))
            db.session.commit()
        return redirect(url_for('person_hub', person_id=person.id))

    app.extensions['unified_people'] = {
        'family_relationships': FAMILY_RELATIONSHIPS,
        'reverse_relationships': REVERSE,
    }
