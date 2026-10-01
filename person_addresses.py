"""Optional address details, keyed to existing canonical person identities.

Existing home-address columns remain authoritative. JSON stores only the
additional home components and work address; it never copies legacy fields.
"""
import app_original as core
from flask import abort, flash, g, has_request_context, render_template, request
from sqlalchemy import UniqueConstraint, event, select, tuple_

db = core.db
FIELDS = {'street': 300, 'unit': 80, 'city': 120, 'state': 80,
          'zip_code': 20, 'country': 80, 'company': 160}


class PersonAddressDetails(db.Model):
    __tablename__ = 'person_address_details'
    __table_args__ = (UniqueConstraint('person_kind', 'person_id',
                                      name='uq_person_address_owner'),)
    id = db.Column(db.Integer, primary_key=True)
    person_kind = db.Column(db.String(40), nullable=False)
    person_id = db.Column(db.Integer, nullable=False)
    home = db.Column(db.JSON, nullable=False, default=dict)
    work = db.Column(db.JSON, nullable=False, default=dict)
    mailing_preference = db.Column(db.String(10), nullable=False, default='')


def address_details(kind, person_id):
    key = kind, person_id
    cache = _request_address_cache()
    if cache is not None and key in cache:
        return cache[key]
    row = db.session.scalar(select(PersonAddressDetails).where(
        PersonAddressDetails.person_kind == kind,
        PersonAddressDetails.person_id == person_id))
    if cache is not None:
        cache[key] = row
    return row


def _request_address_cache():
    if (not has_request_context() or not (
            getattr(g, '_batch_person_import', False) or
            getattr(g, '_person_address_preload_enabled', False))):
        return None
    transaction = db.session().get_transaction()
    if transaction is None:
        db.session().begin()
        transaction = db.session().get_transaction()
    cache = getattr(g, '_person_address_cache', None)
    if cache is None or cache[0] is not transaction:
        cache = (transaction, {})
        g._person_address_cache = cache
    return cache[1]


def _invalidate_address_cache(kind, person_id):
    cache = _request_address_cache()
    if cache is not None:
        cache.pop((kind, person_id), None)


def _remember_address_row(mapper, connection, row):
    cache = _request_address_cache()
    if cache is not None:
        cache[(row.person_kind, row.person_id)] = row


for _event_name in ('after_insert', 'after_update'):
    if not event.contains(PersonAddressDetails, _event_name, _remember_address_row):
        event.listen(PersonAddressDetails, _event_name, _remember_address_row)


def preload_addresses(keys):
    """Load only requested address owners, caching both rows and missing rows."""
    keys = set(keys)
    if not keys:
        return
    if has_request_context():
        g._person_address_preload_enabled = True
    cache = _request_address_cache()
    if cache is None:
        cache = {}
    cached = cache
    missing = keys - cached.keys()
    if not missing:
        return
    rows = db.session.scalars(select(PersonAddressDetails).where(tuple_(
        PersonAddressDetails.person_kind, PersonAddressDetails.person_id
    ).in_(missing))).all()
    by_key = {(row.person_kind, row.person_id): row for row in rows}
    cache.update({key: by_key.get(key) for key in missing})


def delete_owned_addresses(mapper, connection, person):
    kinds = {
        'supporter_person': ('person',), 'family': ('family', 'spouse'),
        'child': ('child', 'child_spouse'), 'contact': ('supporter',),
        'contact_child': ('supporter_child', 'supporter_child_spouse'),
        'askan': ('askan',), 'staff_user': ('staff',),
        'rabbi_person': ('rabbi',), 'helper_person': ('helper',),
        'shul_gabbai_directory': ('gabbai',), 'partner_contact': ('partner_contact',),
    }.get(mapper.local_table.name, ())
    if kinds:
        connection.execute(PersonAddressDetails.__table__.delete().where(
            PersonAddressDetails.person_kind.in_(kinds),
            PersonAddressDetails.person_id == person.id))
        for kind in kinds:
            _invalidate_address_cache(kind, person.id)


def home_values(person, details=None):
    values = dict(details.home or {}) if details else {}
    street_field = ('home_address' if hasattr(person, 'home_address') else
                    'address' if hasattr(person, 'address') else None)
    if street_field:
        values['street'] = getattr(person, street_field) or ''
        for field in ('city', 'state', 'zip_code'):
            if hasattr(person, field):
                values[field] = getattr(person, field) or ''
    return values


def mailing_lines(contact):
    """Resolve the selected mailing address for receipts without creating rows."""
    person = db.session.get(core.SupporterPerson, contact.person_id) if contact.person_id else contact
    kind, person_id = ('person', person.id) if contact.person_id else ('supporter', contact.id)
    details = address_details(kind, person_id)
    if details and details.mailing_preference == 'work':
        values = dict(details.work or {})
        if hasattr(person, 'workplace'):
            values['company'] = person.workplace or ''
    else:
        values = home_values(person, details)
    locality = ', '.join(v for v in (values.get('city'), values.get('state')) if v)
    locality = ' '.join(v for v in (locality, values.get('zip_code')) if v)
    return [v for v in (values.get('company'), values.get('street'),
                        values.get('unit'), locality, values.get('country')) if v]


_UNLOADED = object()


def save_new_supporter_addresses(app, contact, form, *, person=None,
                                 details=_UNLOADED, sync=True):
    """Save supplied optional addresses in the same creation transaction.

Blank fields on a new case connection never erase an existing person's address.
"""
    submitted = {}
    for prefix in ('home', 'work'):
        submitted[prefix] = {}
        for field, limit in FIELDS.items():
            value = form.get(f'{prefix}_{field}', '').strip()
            if len(value) > (240 if prefix == 'home' and field == 'street' else limit):
                abort(400)
            if value:
                submitted[prefix][field] = value
    preference = form.get('mailing_preference', '')
    if preference not in ('', 'home', 'work'):
        abort(400)
    if not any(submitted.values()) and not preference:
        return
    identity = app.extensions['supporter_identity']
    if person is None:
        person = identity['attach'](contact)
    if details is _UNLOADED:
        details = address_details('person', person.id)
    if details is None:
        details = PersonAddressDetails(person_kind='person', person_id=person.id,
                                       home={}, work={})
        db.session.add(details)
        cache = _request_address_cache()
        if cache is not None:
            cache[('person', person.id)] = details
    home = submitted['home']
    for field, column in (('street', 'home_address'), ('city', 'city'),
                          ('state', 'state'), ('zip_code', 'zip_code')):
        if field in home:
            setattr(person, column, home.pop(field))
    work = submitted['work']
    if 'company' in work:
        person.workplace = work.pop('company')
    details.home = {**(details.home or {}), **home}
    details.work = {**(details.work or {}), **work}
    if preference:
        details.mailing_preference = preference
    if sync:
        identity['sync'](person)


def install(app, extra_models, directory_access):
    access = app.extensions['person_address_access']
    models = dict(family=core.Family, spouse=core.Family, child=core.Child,
                  child_spouse=core.Child, supporter=core.Contact,
                  profile=extra_models['profile'], askan=core.Askan,
                  staff=core.StaffUser, supporter_child=core.ContactChild,
                  supporter_child_spouse=core.ContactChild,
                  **{k: v for k, v in extra_models.items() if k != 'profile'})
    for model in set(models.values()) | {core.SupporterPerson}:
        if not event.contains(model, 'after_delete', delete_owned_addresses):
            event.listen(model, 'after_delete', delete_owned_addresses)

    def resolve(kind, person_id):
        if kind == 'supporter_profile':
            kind = 'profile'
        model = models.get(kind)
        if model is None:
            abort(404)
        person = db.get_or_404(model, person_id)
        admin = access['organization_admin']()
        user = access['current_user']()
        if kind in ('family', 'spouse', 'child', 'child_spouse'):
            family_id = person.id if kind in ('family', 'spouse') else person.family_id
            if not (access['can_manage_household']() and access['can_access_family'](family_id)):
                abort(403)
        elif kind in ('supporter', 'supporter_child', 'supporter_child_spouse'):
            contact = person if kind == 'supporter' else person.contact
            if not (access['can_manage_supporters']() and access['can_access_family'](contact.family_id)):
                abort(403)
            if app.extensions['workflows']['enforced']():
                app.extensions['workflows']['contact_allowed'](contact, edit=True)
        elif kind == 'profile':
            directory_access()
        elif kind == 'staff':
            if not admin:
                abort(403)
        elif not (admin or user and user.role in ('family_admin', 'office_employee')):
            abort(403)

        # Case contacts and imported directory profiles share one address owner.
        identity = app.extensions['supporter_identity']
        if kind == 'supporter':
            person = identity['attach'](person)
            return 'person', person, contact
        if kind == 'profile':
            person = identity['profile_person'](person)
            return 'person', person, None
        if kind in ('child', 'child_spouse'):
            contact_id = getattr(person, 'supporter_contact_id' if kind == 'child' else 'spouse_contact_id', None)
            if contact_id:
                contact = db.session.get(core.Contact, contact_id)
                if contact:
                    return 'person', identity['attach'](contact), contact
        return kind, person, None

    @app.route('/people/<kind>/<int:person_id>/addresses', methods=['GET', 'POST'])
    def person_addresses(kind, person_id):
        owner_kind, person, contact = resolve(kind, person_id)
        details = address_details(owner_kind, person.id)
        home = (dict(details.home or {}) if details else {}) if kind == 'spouse' else home_values(person, details)
        work = dict(details.work or {}) if details else {}
        if hasattr(person, 'workplace'):
            work['company'] = person.workplace or ''
        preference = details.mailing_preference if details else ''
        if kind == 'supporter':
            back_url = core.url_for('supporter_detail', contact_id=person_id)
        elif kind in ('family', 'spouse'):
            back_url = core.url_for('family_detail', family_id=person_id)
        elif kind in ('child', 'child_spouse'):
            child = db.session.get(core.Child, person_id)
            back_url = core.url_for('family_detail', family_id=child.family_id)
        elif kind in ('profile', 'supporter_profile'):
            back_url = core.url_for('edit_supporter_profile', profile_id=person_id)
        elif kind == 'askan' and 'network_askan_detail' in app.view_functions:
            back_url = core.url_for('network_askan_detail', askan_id=person_id)
        elif kind == 'staff':
            back_url = core.url_for('staff', panel=2, staff_id=person_id)
        elif kind == 'partner_contact':
            back_url = core.url_for('partner_organization_detail', organization_id=person.organization_id)
        else:
            back_url = core.url_for('community_directories', kind='Shul')
        name_kind = ({'spouse': 'family', 'child_spouse': 'child', 'supporter_child_spouse': 'supporter_child'}.get(owner_kind, owner_kind))
        name_field = ('spouse' if kind == 'spouse' else 'spouse_name' if kind in ('child_spouse', 'supporter_child_spouse') and owner_kind != 'person' else 'name')
        if request.method == 'POST':
            if name_field + '_english' in request.form or name_field + '_yiddish' in request.form:
                from person_names import save_names
                save_names(name_kind, person.id, request.form.get(name_field + '_english', '').strip(), request.form.get(name_field + '_yiddish', '').strip(), name_field)
            preference = request.form.get('mailing_preference', '')
            if preference not in ('', 'home', 'work'):
                abort(400)
            values = {}
            for prefix in ('home', 'work'):
                values[prefix] = {}
                for field, limit in FIELDS.items():
                    value = request.form.get(f'{prefix}_{field}', '').strip()
                    if len(value) > limit:
                        abort(400)
                    values[prefix][field] = value
            if details is None:
                details = PersonAddressDetails(person_kind=owner_kind, person_id=person.id)
                db.session.add(details)
            home = values['home']
            work = values['work']
            legacy = {}
            street_field = (None if kind == 'spouse' else
                            'home_address' if hasattr(person, 'home_address') else
                            'address' if hasattr(person, 'address') else None)
            if street_field:
                limit = person.__table__.columns[street_field].type.length
                if len(home['street']) > limit:
                    abort(400)
                legacy[street_field] = home.pop('street')
                for field in ('city', 'state', 'zip_code'):
                    if hasattr(person, field):
                        legacy[field] = home.pop(field)
            if hasattr(person, 'workplace'):
                legacy['workplace'] = work.pop('company')
            for field, value in legacy.items():
                setattr(person, field, value)
            if owner_kind == 'person':
                app.extensions['supporter_identity']['sync'](person)
            details.home = home
            details.work = work
            details.mailing_preference = preference
            user = access['current_user']()
            db.session.add(core.Audit(actor=user.email if user else 'Demo',
                                     action=f'Updated optional addresses: {owner_kind} {person.id}'))
            db.session.commit()
            flash('Addresses saved.')
            return core.redirect(core.url_for('person_addresses', kind=kind, person_id=person_id))
        display_name = (person.spouse if kind == 'spouse' else
                        person.spouse_name if kind in ('child_spouse', 'supporter_child_spouse') and owner_kind != 'person'
                        else person.name or getattr(person, 'email', ''))
        return render_template('person_addresses.html', title='Home & work addresses',
                               person=person, home=home, work=work,
                               preference=preference, kind=kind, display_name=display_name,
                               back_url=back_url, name_kind=name_kind, name_field=name_field)

    app.extensions['person_addresses'] = dict(mailing_lines=mailing_lines)
