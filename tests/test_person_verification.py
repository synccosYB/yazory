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
    assert batch(client, ident, {'phone': {'edits': {'value': '8455552222'}}}).status_code == 403


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


def test_verification_without_edit_inputs_preserves_existing_canonical_values(app):
    ident = setup_person(app)
    client = app.test_client()
    before = client.get(f'/people/{ident}/verification').json['values']
    for field in ('name', 'phone', 'home_address'):
        state = client.get(f'/people/{ident}/verification').json['fields'][field]
        response = post(client, f'/people/{ident}/verification/{field}', dict(
            status='verified', reason='Verified without editing',
            fingerprint=state['fingerprint']))
        assert response.status_code == 200
    after = client.get(f'/people/{ident}/verification').json['values']
    assert after['name'] == before['name']
    assert after['phone'] == before['phone']
    assert after['home_address'] == before['home_address']


def batch(client, ident, edits):
    import json
    state = client.get(f'/people/{ident}/verification').json['fields']
    changes = {field: dict(fingerprint=state[field]['fingerprint'],
        status=item.get('status', 'unverified'), reason=item.get('reason', ''),
        edits=item.get('edits', {})) for field, item in edits.items()}
    return post(client, f'/people/{ident}/verification', {'changes': json.dumps(changes)})


def test_profile_batch_saves_edits_verification_and_role_snapshots(app):
    ident = setup_person(app)
    client = app.test_client()
    with app.app_context():
        db.session.add(SupporterProfile(person_id=ident, name='One', phone='8455551111',
                                       normalized_phone='batch-profile'))
        db.session.commit()
    response = batch(client, ident, {
        'name': {'status': 'verified', 'edits': {'english_name': 'New name', 'yiddish_name': 'נייער נאמען'}},
        'cell_phone': {'status': 'verified', 'edits': {'value': '8455553333'}},
        'home_address': {'edits': {'street': '20 Main', 'unit': '2', 'city': 'Monroe', 'state': 'NY', 'zip_code': '10950', 'country': 'USA'}}})
    assert response.status_code == 200
    assert response.json['fields']['name']['status'] == 'verified'
    assert response.json['fields']['cell_phone']['status'] == 'verified'
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        profile = db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.person_id == ident))
        assert row.name == profile.name == 'New name'
        assert row.cell_phone == '8455553333'
        assert row.home_address == '20 Main'


def test_profile_batch_failure_rolls_back_every_edit(app):
    ident = setup_person(app)
    client = app.test_client()
    response = batch(client, ident, {'name': {'edits': {'english_name': 'Changed', 'yiddish_name': ''}},
                                    'email': {'status': 'verified', 'edits': {'value': ''}}})
    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(SupporterPerson, ident).name == 'One'
        assert db.session.scalar(db.select(db.func.count(PersonVerification.id))) == 0


def test_profile_batch_rejects_stale_value_and_requires_csrf(app):
    import json
    ident = setup_person(app)
    client = app.test_client()
    state = client.get(f'/people/{ident}/verification').json['fields']['phone']
    with app.app_context():
        db.session.get(SupporterPerson, ident).phone = '8455559999'
        db.session.commit()
    changes = json.dumps({'phone': dict(fingerprint=state['fingerprint'], status='unverified', edits={'value': '8455553333'})})
    assert post(client, f'/people/{ident}/verification', {'changes': changes}).status_code == 409
    assert client.post(f'/people/{ident}/verification', data={'changes': changes}).status_code == 400
    with app.app_context():
        assert db.session.get(SupporterPerson, ident).phone == '8455559999'


def test_profile_has_one_save_and_collapsed_verification_controls(app):
    ident = setup_person(app)
    client = app.test_client()
    for lang in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = lang
        response = client.get(f'/people/{ident}/edit')
        assert response.status_code == 200
        assert response.text.count('data-profile-form') == 1
        assert response.text.count('type="submit" data-save') == 1
        assert '<details data-verification-controls>' in response.text
        assert 'name="name_english"' not in response.text


def test_batch_phone_alias_and_address_metadata_preserved(app):
    ident = setup_person(app)
    client = app.test_client()
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        row.cell_phone = row.phone
        db.session.add(PersonAddressDetails(person_kind='person', person_id=ident,
            home={'mailing_name': 'Recipient'}, work={'company': 'Business'}))
        db.session.commit()
    response = batch(client, ident, {
        'cell_phone': {'edits': {'value': '8455553333'}},
        'work_address': {'edits': {'street': '10 Work', 'unit': '', 'city': 'Monroe', 'state': 'NY', 'zip_code': '10950', 'country': 'USA'}}})
    assert response.status_code == 200
    assert response.json['values']['phone'] == '8455553333'
    assert response.json['values']['work_address']['company'] == 'Business'
    assert response.json['values']['home_address'][4]['mailing_name'] == 'Recipient'


def test_duplicate_phone_editor_save_rolls_back_all_changes(app):
    import json
    ident = setup_person(app)
    with app.app_context():
        other = person('Other', 'phone:8455559999', phone='8455559999')
        db.session.add(SupporterProfile(person_id=other.id, name=other.name,
            phone=other.phone, normalized_phone='8455559999'))
        db.session.commit()
    client = app.test_client()
    state = client.get(f'/people/{ident}/verification').json
    changes = {field: dict(fingerprint=state['fields'][field]['fingerprint'],
        status='unverified', reason='', edits={'value': value})
        for field, value in [('phone', '8455559999'), ('notes', 'Must roll back')]}
    response = post(client, f'/people/{ident}/verification', {'changes': json.dumps(changes)})
    assert response.status_code == 409
    assert response.json['error'] == 'That phone number already belongs to another person.'
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        assert row.phone == state['values']['phone']
        assert row.notes == state['values']['notes']
        assert db.session.scalar(db.select(db.func.count(PersonVerification.id))) == 0


def test_invalid_phone_editor_save_returns_specific_error(app):
    import json
    ident = setup_person(app)
    client = app.test_client()
    state = client.get(f'/people/{ident}/verification').json
    response = post(client, f'/people/{ident}/verification', {'changes': json.dumps({
        'phone': dict(fingerprint=state['fields']['phone']['fingerprint'],
            status='unverified', reason='', edits={'value': '12'})})})
    assert response.status_code == 409
    assert response.json['error'] == 'Enter a valid phone number.'
    assert client.get(f'/people/{ident}/verification').json['values']['phone'] == state['values']['phone']


def test_person_workspace_starts_in_read_mode_with_related_work_tabs(app):
    ident = setup_person(app)
    with app.app_context():
        row = db.session.get(SupporterPerson, ident)
        profile = SupporterProfile(person_id=ident, name=row.name, phone=row.phone,
                                   normalized_phone='workspace-read-mode')
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
    client = app.test_client()
    for lang in ('en', 'he', 'yi'):
        with client.session_transaction() as session:
            session['language'] = lang
        response = client.get(f'/supporter-directory/{profile_id}/edit')
        assert response.status_code == 200
        assert 'data-profile-mode="view"' in response.text
        assert 'data-person-mode="edit"' in response.text
        assert 'data-person-mode="verify"' in response.text
        for tab in ('identity', 'case-connections', 'family-connections',
                    'people-relationships', 'person-activity', 'person-tasks',
                    'person-tickets', 'person-institutions'):
            assert f'data-person-tab="{tab}"' in response.text
            assert f'id="{tab}"' in response.text
