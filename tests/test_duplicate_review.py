import pytest
from tests.test_unified_people import app, person
from app import db, SupporterPerson, SupporterProfile, Contact, Receipt, SupporterCommunication, StaffUser
from person_ids import PersonNumber
from book_directory import PersonBookRecord
from duplicate_review import PersonMerge, merge_people
from unified_people import PersonMatchDecision, _candidates


def profile(p, key):
    row = SupporterProfile(person_id=p.id, name=p.name, phone=p.phone,
                           normalized_phone=key, email=p.email)
    db.session.add(row)
    db.session.flush()
    return row


def test_merge_preserves_case_ids_notes_and_public_number(app):
    with app.app_context():
        one = person('One', 'test:one', '8455551111')
        two = person('Two', 'test:two', '8455551111')
        two.email = 'two@example.com'
        two.home_phone = '8455557788'
        p1, p2 = profile(one, 'rid:one'), profile(two, 'rid:two')
        source, target, old_profile = two.id, one.id, p2.id
        number = db.session.scalar(db.select(PersonNumber.id).where(PersonNumber.person_id == one.id))
        family = db.session.scalar(db.select(__import__('app').Family))
        contact = Contact(family_id=family.id, person_id=source, name=two.name,
                          relationship='Other', supporter_key=two.identity_key, notes='Keep case note')
        db.session.add(contact)
        db.session.flush()
        receipt = Receipt(contact_id=contact.id, family_id=family.id, amount_cents=12345)
        message = SupporterCommunication(contact_id=contact.id, family_id=family.id,
                                         kind='sms', body='Keep conversation')
        db.session.add_all([receipt,message])
        db.session.commit()
        receipt_id, message_id = receipt.id, message.id
        contact_id = contact.id
        merge_people(app, SupporterProfile, target, source)
        moved = db.session.get(Contact, contact_id)
        assert moved.person_id == target
        assert moved.notes == 'Keep case note'
        assert db.session.get(Receipt, receipt_id).amount_cents == 12345
        assert db.session.get(Receipt, receipt_id).contact_id == contact_id
        assert db.session.get(SupporterCommunication, message_id).body == 'Keep conversation'
        assert moved.supporter_key == 'test:one'
        assert db.session.get(SupporterPerson, target).email == 'two@example.com'
        assert db.session.get(SupporterPerson, source) is None
        assert db.session.get(SupporterProfile, old_profile) is None
        assert db.session.get(PersonNumber, number).person_id == target
        audit = db.session.scalar(db.select(PersonMerge).where(PersonMerge.source_id == source))
        assert audit.snapshot['source']['supporter_person'][0]['name'] == 'Two'
        newest = person('New', 'test:new')
        assert newest.id != source
        from duplicate_watch import contact_identity_map
        assert contact_identity_map()[('phone','8455557788')].id == target
        db.session.commit()
    client = app.test_client()
    assert client.get(f'/people/{source}').location.endswith(f'/people/{target}')
    assert client.get(f'/supporter-directory/{old_profile}/edit').status_code == 303


def test_source_book_conflict_cannot_merge(app):
    with app.app_context():
        one, two = person('One', 'test:one'), person('Two', 'test:two')
        profile(one, 'rid:one'); profile(two, 'rid:two')
        for p, book_id in ((one, '001'), (two, '002')):
            db.session.add(PersonBookRecord(person_id=p.id, source='directory', book_id=book_id))
        db.session.commit()
        with pytest.raises(ValueError, match='source book'):
            merge_people(app, SupporterProfile, one.id, two.id)
        db.session.rollback()
        assert db.session.get(SupporterPerson, two.id)
        assert db.session.scalar(db.select(db.func.count(PersonMerge.id))) == 0


def test_review_pages_render_all_locales(app):
    with app.app_context():
        one = person('One', 'test:one', '8455551111')
        two = person('Two', 'test:two', '8455551111')
        profile(one, 'rid:one'); profile(two, 'rid:two')
        a,b=one.id,two.id
        db.session.commit()
    client=app.test_client()
    for lang in ('en','he','yi'):
        with client.session_transaction() as session:
            session['lang']=lang
        assert client.get('/people/matching?tab=duplicates').status_code == 200
        assert client.get(f'/people/duplicates/{a}/{b}').status_code == 200


def test_review_later_is_separate_queue(app):
    with app.app_context():
        one = person('One', 'test:one', '8455551111')
        two = person('Two', 'test:two', '8455551111')
        db.session.add(PersonMatchDecision(person_one_id=one.id, person_two_id=two.id,
            kind='duplicate', decision='review_later'))
        db.session.commit()
    client=app.test_client()
    assert b'Review merge' not in client.get('/people/matching?tab=duplicates').data
    assert b'Review merge' in client.get('/people/matching?tab=duplicates&queue=later').data


def test_old_duplicates_are_not_limited_to_newest_thousand(app):
    with app.app_context():
        one = person('Old One', 'test:one', '8455551199')
        two = person('Old Two', 'test:two', '8455551199')
        db.session.execute(SupporterPerson.__table__.insert(), [
            dict(identity_key=f'bulk:{n}', name=f'Unrelated {n}') for n in range(1100)])
        db.session.commit()
    response = app.test_client().get('/people/matching?tab=duplicates')
    assert b'Old One' in response.data and b'Old Two' in response.data


def test_fundraiser_cannot_preview_merge_or_view_audit(app):
    with app.app_context():
        one, two = person('One','test:one'), person('Two','test:two')
        user = StaffUser(email='limited@example.test',password_hash='unused',role='fundraiser')
        db.session.add(user); db.session.commit()
        a,b,uid = one.id,two.id,user.id
    app.config['DEMO'] = False
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = uid
    assert client.get(f'/people/duplicates/{a}/{b}').status_code == 403
    assert client.get('/people/merge-history').status_code == 403


def test_add_person_checks_home_phone_and_allows_distinct_person(app):
    with app.app_context():
        old = person('Existing','test:existing')
        old.home_phone = '845-555-9911'
        db.session.commit()
    client = app.test_client()
    client.get('/people/new')
    with client.session_transaction() as session:
        token = session['csrf']
    data = dict(csrf=token, name='Different',phone='(845) 555-9911')
    assert client.post('/people/new',data=data).status_code == 409
    data['distinct_person'] = 'yes'
    assert client.post('/people/new',data=data).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(SupporterPerson.id)).where(
            SupporterPerson.name == 'Different')) == 1
        assert db.session.scalar(db.select(PersonMatchDecision).where(
            PersonMatchDecision.kind == 'duplicate')).decision == 'not_duplicate'


def test_changed_preview_is_rejected_and_confirmed_merge_persists(app):
    import re
    with app.app_context():
        one, two = person('One','test:one'), person('Two','test:two')
        profile(one,'rid:one'); profile(two,'rid:two')
        db.session.commit()
        a,b = one.id,two.id
    client = app.test_client()
    url = f'/people/duplicates/{a}/{b}'
    page = client.get(url)
    version = re.search(rb'name="version" value="([a-f0-9]+)"',page.data).group(1).decode()
    with client.session_transaction() as session:
        token = session['csrf']
    data = dict(csrf=token, target_id=a, confirm='yes', version=version)
    with app.app_context():
        db.session.get(SupporterPerson,b).email = 'changed@example.test'
        db.session.commit()
    assert client.post(url,data=data).status_code == 409
    page = client.get(url)
    data['version'] = re.search(rb'name="version" value="([a-f0-9]+)"',page.data).group(1).decode()
    assert client.post(url,data=data).status_code == 302
    with app.app_context():
        assert db.session.get(SupporterPerson,b) is None
        assert db.session.get(SupporterPerson,a).email == 'changed@example.test'
    assert client.get('/people/merge-history').status_code == 200


def test_conflict_rolls_back_partial_field_updates(app):
    from book_directory import PersonFamilyConnection
    import re
    with app.app_context():
        one, two = person('One','test:one'), person('Two','test:two')
        father1, father2 = person('Father 1','test:f1'), person('Father 2','test:f2')
        profile(one,'rid:one'); profile(two,'rid:two')
        two.email='must-not-copy@example.test'
        db.session.add_all([
            PersonFamilyConnection(person_id=one.id,father_person_id=father1.id),
            PersonFamilyConnection(person_id=two.id,father_person_id=father2.id)])
        db.session.commit()
        a,b=one.id,two.id
    client=app.test_client()
    url=f'/people/duplicates/{a}/{b}'
    page=client.get(url)
    version=re.search(rb'name="version" value="([a-f0-9]+)"',page.data).group(1).decode()
    with client.session_transaction() as session:
        token=session['csrf']
    response=client.post(url,data=dict(csrf=token,target_id=a,confirm='yes',version=version))
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(SupporterPerson,a).email == ''
        assert db.session.get(SupporterPerson,b).email == 'must-not-copy@example.test'
        assert db.session.scalar(db.select(db.func.count(PersonMerge.id))) == 0


def test_old_links_follow_multiple_merges(app):
    with app.app_context():
        one,two,three=(person('One','test:one'),person('Two','test:two'),person('Three','test:three'))
        profile(one,'rid:one'); profile(two,'rid:two'); profile(three,'rid:three')
        a,b,c=one.id,two.id,three.id
        db.session.commit()
        merge_people(app,SupporterProfile,a,b)
        merge_people(app,SupporterProfile,c,a)
    assert app.test_client().get(f'/people/{b}').location.endswith(f'/people/{c}')


def test_large_review_keeps_database_parameters_bounded(app):
    from sqlalchemy import event
    with app.app_context():
        one = person('Old One', 'test:old1', '8455551199')
        two = person('Old Two', 'test:old2', '8455551199')
        db.session.execute(SupporterPerson.__table__.insert(), [
            dict(identity_key=f'bounded:{n}', name=f'Unrelated {n}') for n in range(1500)])
        db.session.commit()
        def enforce_limit(conn,cursor,statement,parameters,context,many):
            if not many:
                assert len(parameters) <= 900, 'Matching query exceeds safe parameter budget'
        event.listen(db.engine,'before_cursor_execute',enforce_limit)
        try:
            for language in ('en','he','yi'):
                client=app.test_client()
                with client.session_transaction() as session:
                    session['lang']=language
                response=client.get('/people/matching?tab=duplicates')
                assert response.status_code == 200
                assert b'Old One' in response.data and b'Old Two' in response.data
        finally:
            event.remove(db.engine,'before_cursor_execute',enforce_limit)
