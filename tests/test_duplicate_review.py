import pytest
from werkzeug.datastructures import MultiDict
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
        from person_names import save_names
        save_names('person', one.id, 'One', 'איינער', legacy='One')
        a,b=one.id,two.id
        db.session.commit()
    client=app.test_client()
    for lang in ('en','he','yi'):
        with client.session_transaction() as session:
            session['language']=lang
        assert client.get('/people/matching?tab=duplicates').status_code == 200
        response = client.get(f'/people/duplicates/{a}/{b}')
        assert response.status_code == 200
        assert f'<html lang="{lang}" dir="{"ltr" if lang == "en" else "rtl"}">' in response.text
        assert 'class="person-merge-table"' in response.text
        assert '<bdi dir="ltr">(845) 555-1111</bdi>' in response.text
        assert 'scope="row"' in response.text
        assert f'Yazory record <bdi dir="ltr">#{a}</bdi>' in response.text
        assert f'name="name_english_{a}"' in response.text
        assert f'name="name_yiddish_{a}"' in response.text


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
    data = dict(csrf=token, keep_id=a, confirm='yes', version=version)
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
    response=client.post(url,data=dict(csrf=token,keep_id=a,confirm='yes',version=version))
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(SupporterPerson,a).email == ''
        assert db.session.get(SupporterPerson,b).email == 'must-not-copy@example.test'
        assert db.session.scalar(db.select(db.func.count(PersonMerge.id))) == 0


def test_review_has_one_explicit_required_decision(app):
    with app.app_context():
        one, two = person('One','test:choice-one'), person('Two','test:choice-two')
        profile(one,'rid:choice-one'); profile(two,'rid:choice-two')
        db.session.commit()
        a,b=one.id,two.id
    page=app.test_client().get(f'/people/duplicates/{a}/{b}')
    assert page.status_code == 200
    assert 'name="decision" value="both" required' in page.text
    assert f'name="decision" value="{a}"' in page.text
    assert f'name="decision" value="{b}"' in page.text
    assert 'name="confirm"' not in page.text
    assert 'name="keep_id"' not in page.text


def test_explicit_keep_both_decision_marks_people_distinct(app):
    import re
    with app.app_context():
        one, two = person('One','test:explicit-one','8455553111'), person('Two','test:explicit-two','8455553111')
        profile(one,'rid:explicit-one'); profile(two,'rid:explicit-two')
        db.session.commit()
        a,b=one.id,two.id
    client=app.test_client()
    url=f'/people/duplicates/{a}/{b}'
    page=client.get(url)
    version=re.search(rb'name="version" value="([a-f0-9]+)"',page.data).group(1).decode()
    with client.session_transaction() as session:
        token=session['csrf']
    response=client.post(url,data=dict(csrf=token,version=version,decision='both'))
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(SupporterPerson,a) is not None
        assert db.session.get(SupporterPerson,b) is not None
        decision=db.session.scalar(db.select(PersonMatchDecision).where(
            PersonMatchDecision.person_one_id == min(a,b),
            PersonMatchDecision.person_two_id == max(a,b),
            PersonMatchDecision.kind == 'duplicate'))
        assert decision.decision == 'not_duplicate'


def test_review_can_keep_both_people_as_distinct(app):
    import re
    with app.app_context():
        one, two = person('One','test:one','8455551111'), person('Two','test:two','8455551111')
        profile(one,'rid:one'); profile(two,'rid:two')
        db.session.commit()
        a,b=one.id,two.id
    client=app.test_client()
    url=f'/people/duplicates/{a}/{b}'
    page=client.get(url)
    version=re.search(rb'name="version" value="([a-f0-9]+)"',page.data).group(1).decode()
    with client.session_transaction() as session:
        token=session['csrf']
    response=client.post(url,data=MultiDict([
        ('csrf',token),('keep_id',str(a)),('keep_id',str(b)),
        ('confirm','yes'),('version',version)]))
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(SupporterPerson,a) is not None
        assert db.session.get(SupporterPerson,b) is not None
        decision=db.session.scalar(db.select(PersonMatchDecision).where(
            PersonMatchDecision.person_one_id == min(a,b),
            PersonMatchDecision.person_two_id == max(a,b),
            PersonMatchDecision.kind == 'duplicate'))
        assert decision.decision == 'not_duplicate'
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


def test_review_shows_book_id_source_evidence_and_edits_canonical_names(app):
    import re
    from person_names import names_row, save_names
    with app.app_context():
        one = person('Gold', 'test:source-one', '8455557101')
        two = person('Gold', 'test:source-two', '8455557102')
        profile(one, 'rid:source-one'); profile(two, 'rid:source-two')
        save_names('person', one.id, '', 'גאלד', legacy=one.name)
        save_names('person', two.id, '', 'גאלד', legacy=two.name)
        db.session.add_all([
            PersonBookRecord(person_id=one.id, source='directory', book_id='4011',
                             last_name='גאלד', source_ref='scan.pdf, page 83, entry 19',
                             notes='First-name reading to verify: אברהם.',
                             review='Check first name'),
            PersonBookRecord(person_id=two.id, source='directory', book_id='4033',
                             last_name='גאלד', source_ref='scan.pdf, page 83, entry 40',
                             notes='First-name reading to verify: חיים הערש.',
                             review='Check first name'),
        ])
        a, b = one.id, two.id
        db.session.commit()

    client = app.test_client()
    url = f'/people/duplicates/{a}/{b}'
    page = client.get(url)
    assert page.status_code == 200
    assert f'#{a}' in page.text and f'#{b}' in page.text
    assert '4011' in page.text and '4033' in page.text
    assert 'scan.pdf, page 83, entry 19' in page.text
    assert 'First-name reading to verify: אברהם.' in page.text
    assert 'person-source-grid' in page.text
    assert 'data-person-verification' not in page.text
    version = re.search(rb'name="version" value="([a-f0-9]+)"', page.data).group(1).decode()
    with client.session_transaction() as session:
        token = session['csrf']

    response = client.post(url, data=MultiDict([
        ('csrf', token),
        ('version', version),
        ('keep_id', str(a)), ('keep_id', str(b)),
        (f'name_english_{a}', ''), (f'name_yiddish_{a}', 'אברהם גאלד'),
        (f'name_english_{b}', ''), (f'name_yiddish_{b}', 'חיים הערש גאלד'),
        ('confirm', 'yes'),
    ]))
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(SupporterPerson, a) is not None
        assert db.session.get(SupporterPerson, b) is not None
        assert names_row('person', a).yiddish_name == 'אברהם גאלד'
        assert names_row('person', b).yiddish_name == 'חיים הערש גאלד'
        assert db.session.get(SupporterPerson, a).name == 'אברהם גאלד'
        assert db.session.get(SupporterPerson, b).name == 'חיים הערש גאלד'


def test_review_can_fix_duplicate_phone_fields_without_deciding_merge(app):
    import re
    with app.app_context():
        one = person('One','test:phone-fix-one','7183029595')
        two = person('Two','test:phone-fix-two','7184868929')
        one.cell_phone = one.phone = '7183029595'
        two.cell_phone = two.phone = '7184868929'
        profile(one,'rid:phone-fix-one'); profile(two,'rid:phone-fix-two')
        db.session.commit()
        a,b = one.id,two.id

    client = app.test_client()
    url = f'/people/duplicates/{a}/{b}'
    page = client.get(url)
    assert page.status_code == 200
    assert f'name="cell_phone_{a}"' in page.text
    assert f'name="phone_{a}"' in page.text
    assert f'data-clear-phone="phone_{a}"' in page.text
    assert 'Same number is already in another phone field.' in page.text
    version = re.search(rb'name="version" value="([a-f0-9]+)"', page.data).group(1).decode()
    with client.session_transaction() as session:
        token = session['csrf']

    response = client.post(url, data=MultiDict([
        ('csrf', token), ('version', version), ('action', 'save_fields'),
        (f'home_phone_{a}', ''), (f'cell_phone_{a}', '7183029595'), (f'phone_{a}', ''),
        (f'home_phone_{b}', ''), (f'cell_phone_{b}', '7184868929'), (f'phone_{b}', ''),
    ]))
    assert response.status_code == 302
    assert response.location.endswith(url)
    with app.app_context():
        assert db.session.get(SupporterPerson, a).cell_phone == '7183029595'
        assert db.session.get(SupporterPerson, a).phone == ''
        assert db.session.get(SupporterPerson, b).cell_phone == '7184868929'
        assert db.session.get(SupporterPerson, b).phone == ''
        assert db.session.scalar(db.select(db.func.count(PersonMerge.id))) == 0
