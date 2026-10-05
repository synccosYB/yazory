from sqlalchemy import event
from tests.test_unified_people import app, person
from tests.test_person_addresses import post
from app import db, SupporterPerson, StaffUser, SupporterProfile
from person_verification import PersonVerification, statuses
from person_names import save_names
from person_addresses import PersonAddressDetails


def setup_person(app):
    with app.app_context():
        row = person('One', 'verify:one', phone='8455551111', address='12 Main St')
        db.session.commit()
        return row.id


def verify(client, ident, field='home_address', status='verified', reason='Confirmed by person'):
    state = client.get(f'/people/{ident}/verification').json['fields'][field]
    return post(client, f'/people/{ident}/verification/{field}',
                dict(status=status, reason=reason, fingerprint=state['fingerprint']))


def test_verification_preserves_data_and_records_reviewer(app):
    ident = setup_person(app)
    client = app.test_client()
    assert verify(client, ident).status_code == 200
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        assert row.home_address == '12 Main St'
        assert statuses(row)['home_address']['status'] == 'verified'
        assert statuses(row)['phone']['status'] == 'unverified'
        audit = db.session.scalar(db.select(PersonVerification))
        assert audit.reason == 'Confirmed by person'
        assert audit.reviewer == 'Demo'
        assert audit.created_at
    assert verify(client, ident, status='incorrect', reason='Person denied address').status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(PersonVerification.id))) == 2
        assert db.session.get(SupporterPerson, ident).home_address == '12 Main St'


def test_change_revert_and_identity_independence(app):
    ident = setup_person(app)
    client = app.test_client()
    assert verify(client, ident).status_code == 200
    assert verify(client, ident, 'identity').status_code == 200
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        row.city = 'Brooklyn'
        db.session.commit()
        assert statuses(row)['home_address']['status'] == 'unverified'
        assert statuses(row)['identity']['status'] == 'verified'
        row.city = 'Monroe'
        db.session.commit()
        assert statuses(row)['home_address']['status'] == 'unverified'
        assert db.session.scalar(db.select(PersonVerification).where(PersonVerification.field == 'home_address')).expired


def test_name_and_address_components_invalidate(app):
    ident = setup_person(app)
    client = app.test_client()
    assert verify(client, ident, 'name').status_code == 200
    assert verify(client, ident).status_code == 200
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        save_names('person', ident, 'One', 'איינער', legacy='One')
        db.session.add(PersonAddressDetails(person_kind='person', person_id=ident,
                                           home={'unit': '2'}, work={}))
        db.session.commit()
        assert statuses(row)['name']['status'] == 'unverified'
        assert statuses(row)['home_address']['status'] == 'unverified'


def test_stale_verification_and_validation(app):
    ident = setup_person(app)
    client = app.test_client()
    digest = client.get(f'/people/{ident}/verification').json['fields']['phone']['fingerprint']
    with app.app_context():
        db.session.get(SupporterPerson, ident).phone = '8455552222'
        db.session.commit()
    assert post(client, f'/people/{ident}/verification/phone', dict(
        status='verified', reason='Checked', fingerprint=digest)).status_code == 409
    assert verify(client, ident, 'phone', reason='').status_code == 200
    assert verify(client, ident, 'email').status_code == 400
    assert client.post(f'/people/{ident}/verification/phone', data={'status':'verified'}).status_code == 400
    assert client.get('/people/999999/verification').status_code == 404


def test_permission_isolation(app):
    ident = setup_person(app)
    with app.app_context():
        staff = StaffUser(name='Restricted', email='restricted@example.test',
                          password_hash='unused', role='office_employee')
        db.session.add(staff)
        db.session.commit()
        staff_id = staff.id
    app.config['DEMO'] = False
    client = app.test_client()
    assert client.get(f'/people/{ident}/verification').status_code in (302,403)
    with client.session_transaction() as session:
        session['user_id'] = staff_id
    assert client.get(f'/people/{ident}/verification').status_code == 403
    with app.app_context():
        db.session.get(StaffUser, staff_id).role = 'fundraiser'
        db.session.commit()
    assert client.get(f'/people/{ident}/verification').status_code == 200
    assert verify(client, ident).status_code == 403


def test_one_batch_read_all_fields_and_locales(app):
    ident = setup_person(app)
    client = app.test_client()
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        statements = []
        def count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(db.engine, 'before_cursor_execute', count)
        try:
            assert len(statuses(row)) == 11
        finally:
            event.remove(db.engine, 'before_cursor_execute', count)
        assert len(statements) == 3
        profile = SupporterProfile(person_id=ident, name=row.name, phone=row.phone,
                                   normalized_phone='verify-profile')
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
    for lang, label in [('en', 'Field verification'), ('he', 'אימות פרטים'), ('yi', 'באשטעטיגן פרטים')]:
        with client.session_transaction() as session:
            session['language'] = lang
        response = client.get(f'/supporter-directory/{profile_id}/edit')
        assert response.status_code == 200
        assert label in response.text


def test_same_value_save_does_not_expire_and_history_keeps_value(app):
    ident = setup_person(app)
    client = app.test_client()
    assert verify(client, ident, 'phone').status_code == 200
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        row.phone = '8455551111'
        row.notes = 'Unrelated edit'
        db.session.commit()
        assert statuses(row)['phone']['status'] == 'verified'
        row.phone = '8455559999'
        db.session.commit()
    data = client.get(f'/people/{ident}/verification').json
    phone = next(item for item in data['history'] if item['field'] == 'phone')
    assert phone['value'] == '8455551111'
    assert phone['expired']
    assert data['fields']['phone']['status'] == 'unverified'


def test_address_detail_creation_and_removal_does_not_revive_verification(app):
    ident = setup_person(app)
    client = app.test_client()
    assert verify(client, ident).status_code == 200
    with app.app_context():
        details = PersonAddressDetails(person_kind='person', person_id=ident, home={'unit':'2'}, work={})
        db.session.add(details)
        db.session.commit()
        db.session.delete(details)
        db.session.commit()
        assert statuses(db.session.get(SupporterPerson, ident))['home_address']['status'] == 'unverified'


def test_schema_migration_is_idempotent_preserves_verification(app):
    ident = setup_person(app)
    client = app.test_client()
    assert verify(client, ident, 'identity').status_code == 200
    with app.app_context():
        for hook in app.extensions['init_db_hooks']:
            hook()
        for hook in app.extensions['init_db_hooks']:
            hook()
        row = db.session.get(SupporterPerson, ident)
        assert row.name == 'One'
        assert row.home_address == '12 Main St'
        assert statuses(row)['identity']['status'] == 'verified'


def test_verification_can_edit_canonical_value_and_verify_new_value(app):
    ident = setup_person(app)
    client = app.test_client()
    state = client.get(f'/people/{ident}/verification').json['fields']['phone']
    response = post(client, f'/people/{ident}/verification/phone', dict(
        status='verified', reason='Corrected while checking',
        fingerprint=state['fingerprint'], value='8455553333'))
    assert response.status_code == 200
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        assert row.phone == '8455553333'
        assert statuses(row)['phone']['status'] == 'verified'
        audit = db.session.scalar(db.select(PersonVerification).where(
            PersonVerification.person_id == ident,
            PersonVerification.field == 'phone').order_by(PersonVerification.id.desc()))
        assert audit.checked_value == '8455553333'


def test_verification_name_has_no_duplicate_english_and_edits_bilingual_name(app):
    ident = setup_person(app)
    client = app.test_client()
    with app.app_context():
        save_names('person', ident, 'One', 'איינער', legacy='One')
        db.session.commit()
    data = client.get(f'/people/{ident}/verification').json
    assert data['values']['name'] == ['One', 'איינער']
    state = data['fields']['name']
    response = post(client, f'/people/{ident}/verification/name', dict(
        status='verified', reason='Checked name', fingerprint=state['fingerprint'],
        english_name='Abraham Falkowitz', yiddish_name='אברהם פאלקאוויטש'))
    assert response.status_code == 200
    data = client.get(f'/people/{ident}/verification').json
    assert data['values']['name'] == ['Abraham Falkowitz', 'אברהם פאלקאוויטש']
    assert data['fields']['name']['status'] == 'verified'


def test_verification_can_edit_home_address_components(app):
    ident = setup_person(app)
    client = app.test_client()
    state = client.get(f'/people/{ident}/verification').json['fields']['home_address']
    response = post(client, f'/people/{ident}/verification/home_address', dict(
        status='verified', reason='Checked address', fingerprint=state['fingerprint'],
        street='20 Main St', unit='4B', city='Monroe', state='NY',
        zip_code='10950', country='USA'))
    assert response.status_code == 200
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        assert (row.home_address, row.city, row.state, row.zip_code) == (
            '20 Main St', 'Monroe', 'NY', '10950')
        details = db.session.scalar(db.select(PersonAddressDetails).where(
            PersonAddressDetails.person_kind == 'person',
            PersonAddressDetails.person_id == ident))
        assert details.home == {'unit': '4B', 'country': 'USA'}
        assert statuses(row)['home_address']['status'] == 'verified'
