from app import db, SupporterPerson
from unified_people import PersonFamilyLink, PersonMatchDecision, _candidates


def person(name, key, phone='', address=''):
    row = SupporterPerson(identity_key=key, name=name, phone=phone,
                          home_phone='', cell_phone='', email='',
                          home_address=address, city='Monroe', state='NY',
                          zip_code='10950', workplace='', work_phone='', notes='')
    db.session.add(row)
    db.session.flush()
    return row


def test_name_alone_never_builds_family_candidate(app):
    with app.app_context():
        one = person('Moshe Friedman', 'test:one')
        two = person('Moshe Friedman', 'test:two')
        db.session.commit()
        assert _candidates([one, two], [], 'connection') == []


def test_shared_household_can_be_reviewed_but_does_not_create_tree(app):
    with app.app_context():
        one = person('Moshe Friedman', 'test:one', address='12 Main St')
        two = person('Chaim Friedman', 'test:two', address='12 Main St')
        db.session.commit()
        rows = _candidates([one, two], [], 'connection')
        assert len(rows) == 1
        assert rows[0][2] == ['same home address']
        assert db.session.scalar(db.select(db.func.count(PersonFamilyLink.id))) == 0


def test_exact_name_without_second_signal_is_not_duplicate(app):
    with app.app_context():
        one = person('Yoel Weiss', 'test:one')
        two = person('Yoel Weiss', 'test:two')
        db.session.commit()
        assert _candidates([one, two], [], 'duplicate') == []


def test_phone_and_name_can_enter_duplicate_review(app):
    with app.app_context():
        one = person('Yoel Weiss', 'test:one', phone='845-555-1111')
        two = person('Yoel Weiss', 'test:two', phone='(845) 555-1111')
        db.session.commit()
        rows = _candidates([one, two], [], 'duplicate')
        assert len(rows) == 1
        assert set(rows[0][2]) == {'same full name', 'same phone'}


def test_rejected_pair_stays_out_of_queue(app):
    with app.app_context():
        one = person('A One', 'test:one', address='5 Forest Rd')
        two = person('B One', 'test:two', address='5 Forest Rd')
        db.session.add(PersonMatchDecision(person_one_id=one.id, person_two_id=two.id,
                                           kind='connection', decision='not_related'))
        db.session.commit()
        decisions = db.session.scalars(db.select(PersonMatchDecision)).all()
        assert _candidates([one, two], decisions, 'connection') == []
