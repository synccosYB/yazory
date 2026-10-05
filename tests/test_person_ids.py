import pytest
from app_entry import create_app
from app import db, SupporterPerson, SupporterProfile, Family, Child, Askan, Contact
from person_ids import PersonNumber, formatted, number_for
from person_names import resolve_name_owner


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})


def test_numbers_format():
    assert [formatted(n) for n in (1, 2, 9, 10, 99, 100)] == ['01', '02', '09', '10', '99', '100']


def test_canonical_person_number_uses_person_id_directly(app):
    with app.app_context():
        person = db.session.scalar(db.select(SupporterPerson).order_by(SupporterPerson.id))
        issued = db.session.scalar(db.select(PersonNumber.id).where(PersonNumber.person_id == person.id))
        assert number_for('person', person) == formatted(issued)


def test_roles_and_edits_keep_one_number(app):
    with app.app_context():
        family = Family(name='ID applicant', spouse='ID spouse')
        askan = Askan(name='ID askan')
        db.session.add_all([family, askan]); db.session.flush()
        child = Child(family_id=family.id, name='ID child', age=20, school='', married=False)
        db.session.add(child); db.session.commit()
        values = [number_for('family', family), number_for('family', family, 'spouse'),
                  number_for('askan', askan), number_for('child', child)]
        assert all(values) and len(set(values)) == 4
        original = number_for('child', child)
        child.name = 'Renamed child'; child.cell_phone = '8455554321'; child.married = True
        db.session.flush()
        app.extensions['sync_married_child_supporters'](child)
        db.session.commit()
        contact = db.session.get(Contact, child.supporter_contact_id)
        assert number_for('supporter', contact) == original
        assert number_for('child', child) == original
        owner = resolve_name_owner('child', child.id)[1]
        assert contact.person_id == owner
        for kind, obj in [('family', family), ('askan', askan)]:
            person_id = resolve_name_owner(kind, obj.id)[1]
            assert db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.person_id == person_id))


def test_deleted_number_is_reserved_even_if_internal_key_reused(app):
    with app.app_context():
        one = SupporterPerson(identity_key='ids:delete', name='Delete me')
        db.session.add(one); db.session.commit()
        old_pk = one.id
        number = db.session.scalar(db.select(PersonNumber.id).where(PersonNumber.person_id == old_pk))
        db.session.delete(one); db.session.commit()
        assert db.session.get(PersonNumber, number).person_id is None
        two = SupporterPerson(id=old_pk, identity_key='ids:new', name='New person')
        db.session.add(two); db.session.commit()
        assert int(number_for('person', two)) > number


@pytest.mark.parametrize('lang,label', [('en','Person ID'), ('he','ID'), ('yi','ID')])
def test_directory_search_and_locales(app, lang, label):
    with app.app_context():
        row = db.session.scalar(db.select(SupporterProfile).order_by(SupporterProfile.id))
        number = number_for('profile', row)
        name = row.name
    client = app.test_client()
    with client.session_transaction() as session:
        session['language'] = lang
    response = client.get('/supporter-directory', query_string={'q': number})
    assert response.status_code == 200
    assert label in response.text and name in response.text
    assert f'>{number}</bdi>' in response.text


def test_migration_is_repeatable_without_changing_numbers(app):
    with app.app_context():
        before = db.session.execute(db.select(PersonNumber.id, PersonNumber.person_id)).all()
        app.extensions['migrate_person_ids']()
        after = db.session.execute(db.select(PersonNumber.id, PersonNumber.person_id)).all()
        assert before == after


def test_existing_person_selected_as_askan_keeps_number(app):
    with app.app_context():
        profile = db.session.scalar(db.select(SupporterProfile).order_by(SupporterProfile.id))
        original = number_for('profile', profile)
        canonical_id = app.extensions['selected_canonical_person']('supporter_profile', profile.id)
        askan = Askan(name=profile.name)
        askan._canonical_person_id = canonical_id
        db.session.add(askan); db.session.flush()
        for sync in app.extensions['askan_profile_person_sync']:
            sync(askan)
        db.session.commit()
        assert number_for('askan', askan) == original
        assert resolve_name_owner('askan', askan.id)[1] == canonical_id
        assert db.session.scalar(db.select(db.func.count(SupporterProfile.id)).where(
            SupporterProfile.person_id == canonical_id)) == 1


def test_issued_numbers_cannot_be_edited(app):
    with app.app_context():
        number = db.session.scalar(db.select(PersonNumber))
        number.id = 999999
        with pytest.raises(ValueError, match='cannot be edited'):
            db.session.commit()
        db.session.rollback()


def test_recreated_role_does_not_reuse_a_deleted_roles_identity(app):
    with app.app_context():
        askan = Askan(name='Former askan')
        db.session.add(askan); db.session.commit()
        row_id, original = askan.id, number_for('askan', askan)
        db.session.delete(askan); db.session.commit()
        replacement = Askan(id=row_id, name='Different askan')
        db.session.add(replacement); db.session.commit()
        for sync in app.extensions['askan_profile_person_sync']:
            sync(replacement)
        db.session.commit()
        assert number_for('askan', replacement) != original


def test_unrelated_update_does_not_rerun_person_identity_queries(app):
    """Changing a non-name field must not invoke canonical name/ID maintenance."""
    from sqlalchemy import event
    with app.app_context():
        child = Child(family_id=db.session.scalar(db.select(Family.id)), name='Perf child',
                      age=12, school='', married=False)
        db.session.add(child)
        db.session.commit()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            child.age = 13
            db.session.commit()
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        assert not any('person_name' in statement or 'person_number' in statement
                       or 'supporter_person' in statement or 'supporter_profile' in statement
                       for statement in statements)
